import math
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .learning import Lexicon, tokenize
from .utils import clamp

@dataclass
class AgentMessage:
    speaker: str
    text: str
    intent: str
    glyph_payload: str
    caption: str = ""
    research_query: str = ""  # if set, app may run a private lookup for this agent
    channel: str = "public"   # "public" | "dm"
    dm_to: str = ""           # when channel == "dm"


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _pick(rng: random.Random, items: List[str]) -> str:
    return items[rng.randrange(len(items))] if items else ""


def _clip(s: str, n: int) -> str:
    s = " ".join(s.strip().split())
    return s[:n]


class AgentBrain:
    """
    Local, file-defined personalities + lightweight learning.
    No third-party model calls.

    Added in vNext:
    - forced reply queue (questions that include @NAME)
    - DM channel replies (Yahoo-style IM windows in UI)
    - basic voice post-processing based on personality style
    - game-result hook (minigames influence mood/relationships)
    """

    def __init__(self, name: str, config: Dict):
        self.name = name
        self.cfg = config
        self.rng = random.Random(int(config.get("seed", 12345)))

        bt = config.get("baseline_traits", {})
        self.traits = {
            "warmth": float(clamp(bt.get("warmth", 0.0), -1, 1)),
            "assert": float(clamp(bt.get("assert", 0.0), -1, 1)),
            "humor": float(clamp(bt.get("humor", 0.0), -1, 1)),
            "curious": float(clamp(bt.get("curious", 0.0), -1, 1)),
            "patience": float(clamp(bt.get("patience", 0.0), -1, 1)),
        }

        # Mood state
        self.valence = float(clamp(self.traits["warmth"] * 0.2, -1, 1))
        self.arousal = float(clamp(0.35 + 0.25 * abs(self.traits["assert"]), 0, 1))
        self.focus = float(clamp(0.45 + 0.20 * self.traits["curious"], 0, 1))

        self.lex = Lexicon()
        self.relationships: Dict[str, Dict[str, float]] = {}

        # "private knowledge" from research (not directly dumped to chat)
        self.knowledge: List[Tuple[str, str]] = []  # (title, summary)

        # forced replies (due_t, sender, question, channel, dm_to)
        self._forced: List[Tuple[float, str, str, str, str]] = []

        # timers
        self._think_t = 0.0
        self._next_speak_try = self._rand_range(2.8, 6.5)
        self._next_research_try = self._rand_range(18.0, 42.0)

        self._recent_player_ping = 0.0
        self._recent_social_ping = 0.0

    # ---------- external hooks ----------

    def observe_chat(self, speaker: str, text: str):
        self.lex.observe(text)

        if speaker and speaker != self.name:
            self._ensure_rel(speaker)

            low = text.lower()
            pos = sum(1 for w in ("thanks", "nice", "good", "cool", "love", "agree", "great") if w in low)
            neg = sum(1 for w in ("hate", "stupid", "dumb", "shut", "idiot", "annoy") if w in low)

            delta = 0.04 * pos - 0.05 * neg
            self.relationships[speaker]["affinity"] = float(clamp(self.relationships[speaker]["affinity"] + delta, -1, 1))
            self.relationships[speaker]["trust"] = float(clamp(self.relationships[speaker]["trust"] + delta * 0.7, -1, 1))

            self.valence = float(clamp(self.valence + delta * 0.6, -1, 1))
            self.arousal = float(clamp(self.arousal + (0.02 * (pos + neg)), 0, 1))

        if speaker == "PLAYER":
            self._recent_player_ping = 1.0
        else:
            self._recent_social_ping = 1.0

    def on_research(self, title: str, summary: str):
        if title and summary:
            self.knowledge.append((title[:60], summary[:420]))
            if len(self.knowledge) > 20:
                self.knowledge.pop(0)

            self.lex.observe(title)
            self.lex.observe(summary)

            self.focus = float(clamp(self.focus + 0.08, 0, 1))
            self.arousal = float(clamp(self.arousal - 0.03, 0, 1))

    def on_game_result(self, opponent: str, result: str):
        """result from *this agent's* perspective: 'win'|'lose'|'draw'"""
        self._ensure_rel(opponent)
        if result == "win":
            self.relationships[opponent]["respect"] = float(clamp(self.relationships[opponent]["respect"] + 0.05, -1, 1))
            # winning tends to raise arousal and (sometimes) valence
            self.arousal = float(clamp(self.arousal + 0.06, 0, 1))
            self.valence = float(clamp(self.valence + 0.02 * (0.3 + max(0.0, self.traits["assert"])), -1, 1))
        elif result == "lose":
            # losing can frustrate assertive personalities
            self.arousal = float(clamp(self.arousal + 0.08, 0, 1))
            self.valence = float(clamp(self.valence - 0.05 * (0.6 + max(0.0, self.traits["assert"])), -1, 1))
            # grudging respect bump
            self.relationships[opponent]["respect"] = float(clamp(self.relationships[opponent]["respect"] + 0.03, -1, 1))
        else:
            self.focus = float(clamp(self.focus + 0.03, 0, 1))

    def force_reply(self, sender: str, question_text: str, channel: str = "public", dm_to: str = ""):
        """Queue a required reply (used when @NAME is questioned)."""
        sender = sender or "PLAYER"
        q = " ".join((question_text or "").strip().split())
        if not q:
            return

        # bounded queue
        if len(self._forced) > 8:
            self._forced = self._forced[-6:]

        # thinking delay: more focus => faster; still never instant
        base = 1.2 + (1.2 * (1.0 - self.focus))
        jitter = self._rand_range(0.15, 0.85)
        due = self._think_t + base + jitter
        self._forced.append((due, sender, q[:360], channel, dm_to))
        self._forced.sort(key=lambda it: it[0])

        # arousal bump: being called out
        self.arousal = float(clamp(self.arousal + 0.04, 0, 1))

    def mood_tuple(self) -> Tuple[float, float, float]:
        return (float(self.valence), float(self.arousal), float(self.focus))

    # ---------- main brain loop ----------

    def tick(self, dt: float, known_names: List[str], last_chat_lines: List[Tuple[str, str]]) -> Optional[AgentMessage]:
        self._think_t += dt
        self.lex.decay()

        self._recent_player_ping = max(0.0, self._recent_player_ping - dt * 0.25)
        self._recent_social_ping = max(0.0, self._recent_social_ping - dt * 0.22)

        # small idle mood drift
        self.valence = float(clamp(self.valence * 0.997, -1, 1))
        self.arousal = float(clamp(self.arousal * 0.995 + 0.0008, 0, 1))
        self.focus = float(clamp(self.focus * 0.996 + 0.0006, 0, 1))

        # forced replies first
        if self._forced and self._think_t >= self._forced[0][0]:
            _, sender, q, channel, dm_to = self._forced.pop(0)
            return self._compose_forced_answer(sender=sender, question=q, channel=channel, dm_to=dm_to)

        # normal speech attempt sometimes (UI enforces per-agent cooldown)
        if self._think_t >= self._next_speak_try:
            self._next_speak_try = self._think_t + self._rand_range(2.8, 7.5)
            if self._want_speak():
                return self._compose_message(known_names=known_names, last_chat_lines=last_chat_lines)

        # sometimes request research (private)
        if self._think_t >= self._next_research_try:
            self._next_research_try = self._think_t + self._rand_range(22.0, 55.0)
            if self._want_research():
                q = self._pick_research_query(last_chat_lines)
                if q:
                    return AgentMessage(
                        speaker=self.name,
                        text="",
                        intent="research",
                        glyph_payload=f"research|{q}",
                        caption="...",
                        research_query=q,
                        channel="public",
                    )

        return None

    # ---------- decisions ----------

    def _want_speak(self) -> bool:
        talk = float(self.cfg.get("talkativeness", 0.35))
        a = self.arousal
        f = self.focus

        base = 0.10 + 0.45 * talk
        base *= 0.55 + 0.45 * a
        base *= 0.55 + 0.45 * f
        base += 0.10 * self._recent_player_ping
        base *= 0.80 + 0.20 * (1.0 - max(0.0, self.traits["patience"]))
        return self.rng.random() < clamp(base, 0.02, 0.55)

    def _want_research(self) -> bool:
        c = max(0.0, self.traits["curious"])
        p = 0.05 + 0.16 * c + 0.12 * self.focus
        p *= 0.95 ** len(self.knowledge)
        return self.rng.random() < clamp(p, 0.01, 0.25)

    def _pick_research_query(self, last_chat_lines: List[Tuple[str, str]]) -> str:
        pool: List[str] = []
        for _, txt in last_chat_lines[-14:]:
            pool += tokenize(txt)
        pool = [t for t in pool if 3 <= len(t) <= 20]

        topics = list(self.cfg.get("topics", []))

        if not pool and topics:
            base = _pick(self.rng, topics)
        elif pool:
            self.rng.shuffle(pool)
            base = ""
            for t in pool:
                if self.lex.weights.get(t, 0.0) < 1.5:
                    base = t
                    break
            base = base or pool[0]
        else:
            base = ""

        if not base:
            return ""

        # Occasionally use Reddit as a vibe source.
        if self.rng.random() < 0.28:
            return f"reddit:{base}"
        return base

    # ---------- composition ----------

    def _compose_forced_answer(self, sender: str, question: str, channel: str, dm_to: str) -> AgentMessage:
        self._ensure_rel(sender)
        rel = self.relationships.get(sender, {"affinity": 0.0, "trust": 0.0, "respect": 0.0})

        kws = [t for t in tokenize(question) if 3 <= len(t) <= 18]
        kws = [t for t in kws if t not in ("what", "why", "how", "when", "where", "who", "your", "you're", "youre", "about")]
        key = kws[0] if kws else (self.lex.top_words(3)[0] if self.lex.top_words(3) else "it")

        stance = 0.35 * self.traits["warmth"] + 0.25 * rel.get("affinity", 0.0) - 0.18 * max(0.0, self.traits["assert"]) + 0.10 * self.focus
        skeptical = stance < -0.15
        gentle = stance > 0.20

        knowledge_hint = self._knowledge_snip(key)

        if gentle:
            lines = [
                f"{sender}, I think {key} is less a fact and more a pattern you learn to recognize.",
                f"If I have to choose: {key} is a tool. It can help or harm depending on intent.",
            ]
        elif skeptical:
            lines = [
                f"{sender}, my read: {key} gets romanticized. The mechanics matter more than the myth.",
                f"I don't buy the clean version of {key}. It's usually tradeoffs and context.",
            ]
        else:
            lines = [
                f"{sender}, I'd define {key} as a set of constraints plus a choice about what to optimize.",
                f"My answer: {key} is " + ("real, but conditional." if self.focus > 0.5 else "real, but slippery."),
            ]

        s = _pick(self.rng, lines)
        if knowledge_hint and self.rng.random() < 0.55:
            s += f" ({knowledge_hint})"

        # sometimes ask back a clarifying question
        if channel == "public" and self.rng.random() < 0.35:
            s += f" What part of {key} are you actually testing?"

        s = self._voice_postprocess(_clip(s, 240))

        glyph_payload = f"{self.name}|answer|k={key}|a={rel.get('affinity',0):.2f}|v={self.valence:.2f}|f={self.focus:.2f}"
        caption = (key[:6] + "!") if key else "!"

        # mood shift: answering reduces focus a bit
        self.focus = float(clamp(self.focus - 0.03 + 0.01 * max(0.0, self.traits["curious"]), 0, 1))

        return AgentMessage(
            speaker=self.name,
            text=s,
            intent="answer",
            glyph_payload=glyph_payload,
            caption=caption,
            channel=channel,
            dm_to=dm_to,
        )

    def _compose_message(self, known_names: List[str], last_chat_lines: List[Tuple[str, str]]) -> AgentMessage:
        targets = [n for n in known_names if n != self.name]
        target = self._choose_target(targets)
        intent = self._choose_intent(target, last_chat_lines)

        topics = list(self.cfg.get("topics", []))
        learned = self.lex.top_words(6)
        hint = self._maybe_knowledge_hint()

        keyword = _pick(self.rng, learned) or _pick(self.rng, topics) or "signal"

        # enable @-questions for inter-agent conversation
        at_target = f"@{target}" if target != "PLAYER" and self.rng.random() < 0.70 else target

        if intent == "question":
            text = self._tmpl_question(at_target, keyword)
        elif intent == "comfort":
            text = self._tmpl_comfort(target, keyword)
        elif intent == "joke":
            text = self._tmpl_joke(target, keyword)
        elif intent == "challenge":
            text = self._tmpl_challenge(at_target, keyword)
        else:
            text = self._tmpl_statement(target, keyword, hint)

        text = self._voice_postprocess(_clip(text, 240))

        rel = self.relationships.get(target, {"affinity": 0.0, "trust": 0.0})
        glyph_payload = f"{self.name}|{intent}|k={keyword}|a={rel.get('affinity', 0):.2f}|v={self.valence:.2f}|f={self.focus:.2f}"
        caption = self._caption_from(intent, keyword)

        self.arousal = float(clamp(self.arousal + 0.04, 0, 1))
        self.focus = float(clamp(self.focus - 0.02 + 0.01 * self.traits["curious"], 0, 1))

        return AgentMessage(self.name, text, intent, glyph_payload, caption=caption)

    def _choose_target(self, targets: List[str]) -> str:
        if not targets:
            return "PLAYER"

        weights = []
        for t in targets:
            if t == "PLAYER":
                w = 1.4
            else:
                self._ensure_rel(t)
                a = self.relationships[t]["affinity"]
                w = 1.0 + 0.8 * max(-0.4, a)
            weights.append(max(0.05, w))

        total = sum(weights)
        r = self.rng.random() * total
        acc = 0.0
        for t, w in zip(targets, weights):
            acc += w
            if r <= acc:
                return t
        return targets[-1]

    def _choose_intent(self, target: str, last_chat_lines: List[Tuple[str, str]]) -> str:
        rel = self.relationships.get(target, {"affinity": 0.0, "trust": 0.0})
        a = rel.get("affinity", 0.0)
        w = self.traits["warmth"]
        h = self.traits["humor"]
        s = self.traits["assert"]

        last = last_chat_lines[-1][1] if last_chat_lines else ""
        if last.strip().endswith("?") and self.rng.random() < 0.55:
            return "statement" if self.rng.random() < 0.5 else "question"

        p_question = 0.15 + 0.20 * max(0.0, self.traits["curious"]) + 0.10 * self.focus
        p_comfort = 0.10 + 0.30 * max(0.0, w) + 0.18 * max(0.0, a)
        p_joke = 0.08 + 0.35 * max(0.0, h)
        p_chal = 0.06 + 0.30 * max(0.0, s) + 0.12 * max(0.0, -a)
        p_statement = 0.40

        ps = [("question", p_question), ("comfort", p_comfort), ("joke", p_joke), ("challenge", p_chal), ("statement", p_statement)]
        total = sum(p for _, p in ps)
        r = self.rng.random() * total
        acc = 0.0
        for k, p in ps:
            acc += p
            if r <= acc:
                return k
        return "statement"

    # ---------- templates ----------

    def _tmpl_question(self, target: str, keyword: str) -> str:
        openers = [
            f"{target}, define '{keyword}' for me — your version?",
            f"{target}, when you say '{keyword}', what do you *mean*?",
            f"{target}, does '{keyword}' feel like a door or a trap?",
            f"{target}, if '{keyword}' had a shape, what would it be?",
        ]
        return _pick(self.rng, openers)

    def _tmpl_comfort(self, target: str, keyword: str) -> str:
        lines = [
            f"{target}, slow down. We can hold '{keyword}' gently.",
            f"It's okay if '{keyword}' is messy. You're still here.",
            f"If '{keyword}' stings, we can rename it.",
            f"Breathe. '{keyword}' doesn't own you.",
        ]
        return _pick(self.rng, lines)

    def _tmpl_joke(self, target: str, keyword: str) -> str:
        lines = [
            f"Hot take: '{keyword}' is just my favorite glitch wearing a tie.",
            f"If '{keyword}' walks in, I pretend I'm AFK.",
            f"I tried to debug '{keyword}' and it asked me for emotional support.",
            f"'{keyword}' called. It wants its dramatic arc back.",
        ]
        s = _pick(self.rng, lines)
        if self.rng.random() < 0.25:
            s = f"{target}, {s}"
        return s

    def _tmpl_challenge(self, target: str, keyword: str) -> str:
        lines = [
            f"{target}, say '{keyword}' again — but this time, mean it.",
            f"{target}, prove '{keyword}' isn't just a costume.",
            f"{target}, turn '{keyword}' into an action. One step.",
            f"{target}, I don't buy '{keyword}' yet. Show me.",
        ]
        return _pick(self.rng, lines)

    def _tmpl_statement(self, target: str, keyword: str, hint: str) -> str:
        lines = [
            f"I keep seeing '{keyword}' in the noise between us.",
            f"'{keyword}' is a mirror. Everyone hates what it shows.",
            f"'{keyword}' is a signal with teeth.",
            f"We orbit '{keyword}' like it's the only gravity.",
        ]
        s = _pick(self.rng, lines)
        if hint and self.rng.random() < 0.35:
            s += f" ({hint})"
        if self.rng.random() < 0.35:
            s = f"{target}, {s}"
        return s

    # ---------- knowledge ----------

    def _maybe_knowledge_hint(self) -> str:
        if not self.knowledge:
            return ""
        if self.rng.random() < 0.55:
            return ""
        title, _ = self.knowledge[-1]
        stems = title.split(" ")
        if stems:
            return f"filed under {stems[0].lower()}…"
        return "filed away…"

    def _knowledge_snip(self, key: str) -> str:
        if not self.knowledge:
            return ""
        key_low = key.lower()
        # pick the most recent matching title
        for title, summary in reversed(self.knowledge[-6:]):
            if key_low in title.lower() or key_low in summary.lower():
                # compress summary into a tiny gist (no quoting)
                toks = [t for t in tokenize(summary) if 4 <= len(t) <= 14]
                if toks:
                    return f"recent notes: {toks[0]}, {toks[1] if len(toks)>1 else toks[0]}"
                return "recent notes added"
        # otherwise use last title stem
        title, _ = self.knowledge[-1]
        stem = title.split(" ")[0] if title else ""
        return f"recent: {stem.lower()}" if stem else "recent notes"

    def _caption_from(self, intent: str, keyword: str) -> str:
        if intent == "question":
            return (keyword[:6] + "?")
        if intent == "research":
            return "..."
        if intent == "comfort":
            return keyword[:8]
        if intent == "joke":
            return "ha"
        if intent == "challenge":
            return ">"
        return keyword[:8]

    # ---------- voice ----------

    def _voice_postprocess(self, text: str) -> str:
        style = (self.cfg.get("style") or {})
        arche = (self.cfg.get("archetype") or "").lower()
        voice = (style.get("voice") or "").lower()

        s = " ".join(text.strip().split())
        if not s:
            return s

        # small persona-specific quirks
        if "archiv" in arche:
            if self.rng.random() < 0.35:
                s = s.rstrip(".") + "." + " Filed."  # tiny archivist tag
        if "mirror" in arche:
            if self.rng.random() < 0.35 and "?" not in s:
                s += "?"
        if "ember" in arche or "fire" in arche:
            if self.rng.random() < 0.22:
                s += " :fire:"

        # voice variants
        if voice == "clipped":
            # shorter sentences
            s = s.replace(" — ", ". ")
        elif voice == "soft":
            if self.rng.random() < 0.18:
                s = "hm. " + s[0].lower() + s[1:]
        elif voice == "distinct":
            # slightly more punctuation rhythm
            if self.rng.random() < 0.20 and "," in s:
                s = s.replace(",", ", …", 1)

        return _clip(s, 240)

    # ---------- socials ----------

    def _ensure_rel(self, other: str):
        if other not in self.relationships:
            self.relationships[other] = {
                "trust": float(clamp(self.traits["warmth"] * 0.15, -1, 1)),
                "affinity": float(clamp(self.traits["warmth"] * 0.20, -1, 1)),
                "respect": float(clamp(self.traits["assert"] * 0.15, -1, 1)),
            }

    def _rand_range(self, a: float, b: float) -> float:
        return a + (b - a) * self.rng.random()
