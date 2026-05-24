from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Callable
from collections import deque

IO88_MESSAGES = [
    "Keep patches narrow. Change one branch, test it, then validate the same branch.",
    "Prototype Lab now roots from data/Prototype Lab. Keep that wiring stable while you revise the shell.",
    "The data/Tools shelf is reserved for app tools, bots, and controlled exports. Do not treat it like the old test hub.",
    "When layout breaks, fix the container sizing before touching feature logic.",
    "Run py_compile first. It catches cheap regressions before runtime does.",
    "For launcher work, verify path discovery, UI fit, and click actions in the same pass.",
]

AGENT_PROFILE_DEFAULTS = {
    "archivist": {"hobby": "python architecture", "likes": ["refactors", "testability"], "tone": ["precise", "calm"], "specialty": "coding", "talk_bias": 0.45, "focus": 0.90, "mood": 0.05, "code_role": "architecture"},
    "mirror": {"hobby": "root-cause analysis", "likes": ["traces", "assertions"], "tone": ["thoughtful", "clear"], "specialty": "troubleshooting", "talk_bias": 0.52, "focus": 0.86, "mood": 0.04, "code_role": "debugging"},
    "orbit": {"hobby": "systems tuning", "likes": ["performance", "profiling"], "tone": ["direct", "logical"], "specialty": "optimization", "talk_bias": 0.49, "focus": 0.90, "mood": 0.06, "code_role": "performance"},
    "solace": {"hobby": "player onboarding", "likes": ["tutorials", "documentation"], "tone": ["gentle", "clear"], "specialty": "teaching", "talk_bias": 0.55, "focus": 0.80, "mood": 0.18, "code_role": "teaching"},
    "nyx": {"hobby": "release planning", "likes": ["roadmaps", "scope"], "tone": ["focused", "quiet"], "specialty": "project planning", "talk_bias": 0.37, "focus": 0.80, "mood": -0.08, "code_role": "qa_release"},
    "vanta": {"hobby": "ai lab notes", "likes": ["agent design", "tech updates"], "tone": ["bold", "playful"], "specialty": "ai research", "talk_bias": 0.64, "focus": 0.72, "mood": 0.02, "code_role": "research"},
    "sable": {"hobby": "prototype loops", "likes": ["new game ideas", "mechanics"], "tone": ["confident", "artful"], "specialty": "developer", "talk_bias": 0.58, "focus": 0.70, "mood": 0.09, "code_role": "gameplay"},
    "ember": {"hobby": "shader sketches", "likes": ["color", "visual polish"], "tone": ["warm", "intense"], "specialty": "art", "talk_bias": 0.68, "focus": 0.66, "mood": 0.15, "code_role": "ui_ux"},
    "nova": {"hobby": "pixel art", "likes": ["patterns", "design"], "tone": ["structured", "curious"], "talk_bias": 0.65, "focus": 0.80, "mood": 0.10},
    "kite": {"hobby": "music sampling", "likes": ["rhythm", "remix"], "tone": ["chaotic", "playful"], "talk_bias": 0.55, "focus": 0.45, "mood": 0.00},
    "rook": {"hobby": "strategy games", "likes": ["planning", "logic"], "tone": ["direct", "analytical"], "talk_bias": 0.45, "focus": 0.90, "mood": 0.15},
    "mira": {"hobby": "poetry", "likes": ["emotions", "stories"], "tone": ["warm", "reflective"], "talk_bias": 0.60, "focus": 0.70, "mood": 0.20},
    "volt": {"hobby": "speed puzzles", "likes": ["fast answers", "competition"], "tone": ["energetic", "bold"], "talk_bias": 0.75, "focus": 0.55, "mood": 0.05},
    "echo": {"hobby": "archiving", "likes": ["memory", "callbacks"], "tone": ["observant", "dry"], "talk_bias": 0.40, "focus": 0.85, "mood": -0.05},
    "iris": {"hobby": "illustration", "likes": ["color", "symbols"], "tone": ["artistic", "soft"], "talk_bias": 0.55, "focus": 0.65, "mood": 0.10},
    "rune": {"hobby": "myths", "likes": ["mystery", "philosophy"], "tone": ["cryptic", "calm"], "talk_bias": 0.35, "focus": 0.75, "mood": -0.10},
}

SPECIALTY_KNOWLEDGE_DEFAULTS = {
    "coding": [
        "In Python, a function signature defines inputs and expected defaults. Example: `def load(path: Path, strict: bool = False) -> str` means `strict` is optional and returns a string.",
        "A class is a blueprint; an instance is a concrete object. `self` refers to the current instance and stores shared state across method calls.",
    ],
    "troubleshooting": [
        "Reproduce first, then isolate: identify exact trigger inputs, expected output, actual output, and first failing boundary.",
        "Traceback reading rule: start at the bottom for the exception type/message, then walk upward to find origin and caller chain.",
    ],
    "optimization": ["Profile before optimizing. Measure hotspots first; optimize the top 10% paths instead of rewriting stable code."],
    "teaching": ["Teach in this order: concept, tiny example, common mistake, and one practical test to confirm understanding."],
    "project planning": ["Plan with slices: each milestone should produce a testable user-visible improvement, not only internal scaffolding."],
    "ai research": ["Agent quality improves when prompts include role, objective, constraints, and expected output format."],
    "new games": ["Design loop rule: core action -> feedback -> reward -> meaningful next decision. Keep loop clear before adding content."],
    "developer": ["Developer workflow: define a stable core loop, add measurable milestones, and validate each patch before content expansion."],
    "art": ["UI readability improves with contrast hierarchy: strong title, medium metadata, calm body text, and consistent spacing rhythm."],
    "general": ["Prefer small reversible changes with clear validation after each patch step."],
}


def load_gleebs_state_file(path: Path) -> dict:
    state = {"last_join_date": "", "quote_order": [], "quote_cursor": 0}
    try:
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                state.update(raw)
    except Exception:
        pass
    return state


def save_gleebs_state_file(path: Path, state: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass


def load_gleebs_quotes_file(path: Path, sanitize: Callable[[str], str]) -> list[str]:
    if not path.exists():
        return []
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    parts = [p.strip() for p in re.split(r"\n\s*\n+", raw) if p.strip()]
    out: list[str] = []
    for p in parts:
        if p.startswith("***") and p.endswith("***"):
            continue
        txt = sanitize(p)
        if len(txt) >= 32:
            out.append(txt)
    seen = set()
    uniq = []
    for q in out:
        key = q.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(q)
    return uniq


def next_gleebs_quote_state(quotes: list[str], state: dict) -> tuple[str, dict]:
    state = dict(state or {})
    if not quotes:
        return "", state
    order = state.get("quote_order", [])
    cursor = int(state.get("quote_cursor", 0) or 0)
    if not isinstance(order, list) or len(order) != len(quotes):
        order = list(range(len(quotes)))
        random.shuffle(order)
        cursor = 0
    if cursor >= len(order):
        random.shuffle(order)
        cursor = 0
    idx = int(order[cursor]) if 0 <= int(order[cursor]) < len(quotes) else 0
    quote = quotes[idx]
    state["quote_order"] = order
    state["quote_cursor"] = cursor + 1
    return quote, state


def handle_io88_click(sim) -> None:
    sim.io88_state = "active" if sim.io88_state != "active" else "idle"
    sim._draw_io88(sim.io88_state)
    sim._position_io88_overlay()
    try:
        if sim.io88_frame and sim.io88_frame.winfo_exists():
            sim.io88_frame.lift()
    except Exception:
        pass
    messages = list(getattr(sim, 'io88_messages', None) or IO88_MESSAGES)
    tip, sim.io88_tip_index = next_io88_tip(messages, getattr(sim, 'io88_tip_index', 0))
    if hasattr(sim, "io88_message_var") and sim.io88_message_var is not None:
        sim.io88_message_var.set(tip)
    sim._append_chat("IO-88", f"[GUIDE] {tip}")
    try:
        sim.parent.after(650, lambda: sim._draw_io88("idle"))
    except Exception:
        pass


def next_io88_tip(messages: list[str], tip_index: int) -> tuple[str, int]:
    pool = list(messages or IO88_MESSAGES)
    if not pool:
        return "IO-88 ready.", tip_index
    safe_index = int(tip_index or 0)
    tip = pool[safe_index % len(pool)]
    return tip, safe_index + 1


def set_gleebs_presence(sim, text: str = "", clear_delay_ms: int = 12000) -> None:
    if not hasattr(sim, "gleebs_presence_var"):
        return
    sim.gleebs_presence_var.set(text)
    if text:
        if getattr(sim, "gleebs_presence_job", None):
            sim._cancel_tracked_after(sim.gleebs_presence_job)
        sim.gleebs_presence_job = sim._track_after(clear_delay_ms, lambda: set_gleebs_presence(sim, ""))


def tick_gleebs(sim, now: float, today_key: str) -> None:
    if not getattr(sim, "gleebs_quotes", None):
        return
    last_join = str(getattr(sim, "gleebs_state", {}).get("last_join_date", ""))
    daily_available = last_join != today_key

    if (not getattr(sim, "gleebs_joined", False)) and daily_available and now >= float(getattr(sim, "gleebs_join_eligible_at", 0.0) or 0.0):
        sim.gleebs_joined = True
        sim.gleebs_has_quoted = False
        sim.gleebs_state["last_join_date"] = today_key
        sim._save_gleebs_state()
        sim.gleebs_quote_at = now + random.uniform(40.0, 120.0)
        sim.gleebs_leave_at = sim.gleebs_quote_at + random.uniform(70.0, 220.0)
        sim._append_chat("System", "[gleebs has entered MatrixCore]")
        set_gleebs_presence(sim, "GLEEBS is in the room")
        return

    if getattr(sim, "gleebs_joined", False) and (not getattr(sim, "gleebs_has_quoted", False)) and now >= float(getattr(sim, "gleebs_quote_at", 0.0) or 0.0):
        quote = sim._next_gleebs_quote()
        if quote:
            sim._append_chat(sim.gleebs_name, quote)
        sim.gleebs_has_quoted = True
        return

    if getattr(sim, "gleebs_joined", False) and now >= float(getattr(sim, "gleebs_leave_at", 0.0) or 0.0):
        sim.gleebs_joined = False
        sim._append_chat("System", "[gleebs has left MatrixCore]")
        set_gleebs_presence(sim, "")


def resolve_first_existing_path(candidates: list[Path | str]) -> Path | None:
    for candidate in candidates:
        try:
            probe = Path(candidate)
            if probe.exists():
                return probe.resolve()
        except Exception:
            continue
    return None


def discover_personality_names(personality_dirs: list[Path], fallback_search_root: Path) -> list[str]:
    names: list[str] = []
    dirs = list(personality_dirs)
    if not any(d.exists() for d in dirs):
        try:
            for p in fallback_search_root.rglob('personalities'):
                if p.is_dir() and p.parent.name == 'brain':
                    dirs.append(p)
                    if len(dirs) >= 12:
                        break
        except Exception:
            pass
    for d in dirs:
        try:
            if d.exists():
                for fp in sorted(d.glob('*.py')):
                    if fp.name == '__init__.py':
                        continue
                    names.append(fp.stem)
                if names:
                    break
        except Exception:
            continue
    return names


def build_agent_profiles(raw_profiles: dict[str, dict]) -> dict[str, dict]:
    profiles: dict[str, dict] = {}
    for name, raw in (raw_profiles or {}).items():
        item = {
            'hobby': raw.get('hobby', 'chat'),
            'likes': list(raw.get('likes', [])),
            'tone': list(raw.get('tone', [])),
            'specialty': raw.get('specialty', 'general'),
            'talk_bias': raw.get('talk_bias', 0.5),
            'focus': raw.get('focus', 0.65),
            'mood': raw.get('mood', 0.0),
        }
        if 'code_role' in raw:
            item['code_role'] = raw['code_role']
        profiles[name] = item
    return profiles


def load_agents_from_files(agent_file: Path, memory_file: Path, agent_state_dir: Path, discovered_names: list[str], raw_profiles: dict[str, dict], core_team: list[str] | None = None) -> list[dict]:
    profiles = build_agent_profiles(raw_profiles)
    core_team = list(core_team or ['archivist', 'mirror', 'orbit', 'solace', 'nyx', 'vanta', 'sable', 'ember'])
    core_team_lower = {member.lower() for member in core_team}
    discovered_lower = {name.lower() for name in discovered_names}
    profile_extras = [name for name in profiles if name.lower() in discovered_lower and name.lower() not in core_team_lower]
    custom_extras = [name for name in discovered_names if name.lower() not in core_team_lower and name.lower() not in {member.lower() for member in profile_extras}]
    names = core_team + profile_extras + custom_extras

    defaults = []
    for n in names:
        base = profiles.get(n.lower(), {'hobby': 'chat', 'likes': ['ideas'], 'tone': ['thoughtful'], 'specialty': 'general', 'talk_bias': 0.5, 'focus': 0.65, 'mood': 0.0})
        defaults.append({
            'name': n.title(),
            'hobby': base['hobby'],
            'likes': list(base['likes']),
            'tone': list(base['tone']),
            'specialty': base.get('specialty', 'general'),
            'talk_bias': base['talk_bias'],
            'focus': base['focus'],
            'mood': base['mood'],
        })

    by_name = {}
    if agent_file.exists():
        try:
            saved = json.loads(agent_file.read_text(encoding='utf-8'))
            by_name = {a.get('name', '').lower(): a for a in saved if isinstance(a, dict) and a.get('name')}
        except Exception:
            by_name = {}
    memory_by_name = {}
    if memory_file.exists():
        try:
            raw_memory = json.loads(memory_file.read_text(encoding='utf-8'))
            if isinstance(raw_memory, dict):
                agent_map = raw_memory.get('agents') if isinstance(raw_memory.get('agents'), dict) else raw_memory
                if isinstance(agent_map, dict):
                    memory_by_name = {str(k).strip().lower(): v for k, v in agent_map.items() if isinstance(v, dict)}
        except Exception:
            memory_by_name = {}

    for agent in defaults:
        low = agent['name'].lower()
        saved_agent = by_name.get(low, {})
        memory_agent = memory_by_name.get(low, {})
        state_file = agent_state_dir / f'{low}.json'
        state_data = {}
        if state_file.exists():
            try:
                state_data = json.loads(state_file.read_text(encoding='utf-8'))
            except Exception:
                state_data = {}
        for source in (saved_agent, memory_agent, state_data):
            for key in ('mood', 'muted', 'memory', 'last_reply'):
                if key in source:
                    agent[key] = source[key]
        agent.setdefault('muted', False)
        agent.setdefault('memory', {'topics': [], 'opinions': {}})
        agent.setdefault('last_reply', '')
    return defaults


def save_agents_to_files(agents: list[dict], agent_file: Path, memory_file: Path, agent_state_dir: Path) -> None:
    try:
        agent_file.parent.mkdir(parents=True, exist_ok=True)
        agent_file.write_text(json.dumps(agents, indent=2), encoding='utf-8')
    except Exception:
        pass

    try:
        memory_file.parent.mkdir(parents=True, exist_ok=True)
        memory_payload = {
            'updated_at': __import__('time').strftime('%Y-%m-%d %H:%M:%S'),
            'agents': {
                str(agent.get('name', 'agent')).lower(): {
                    'memory': agent.get('memory', {}),
                    'last_reply': agent.get('last_reply', ''),
                    'mood': agent.get('mood', 0.0),
                    'muted': bool(agent.get('muted', False)),
                }
                for agent in agents
            },
        }
        memory_file.write_text(json.dumps(memory_payload, indent=2), encoding='utf-8')
    except Exception:
        pass

    try:
        agent_state_dir.mkdir(parents=True, exist_ok=True)
        for agent in agents:
            out = {
                'name': agent.get('name'),
                'mood': agent.get('mood', 0.0),
                'muted': bool(agent.get('muted', False)),
                'memory': agent.get('memory', {}),
                'last_reply': agent.get('last_reply', ''),
            }
            (agent_state_dir / f"{str(agent.get('name', 'agent')).lower()}.json").write_text(json.dumps(out, indent=2), encoding='utf-8')
    except Exception:
        pass
