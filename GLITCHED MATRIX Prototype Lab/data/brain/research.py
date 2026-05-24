import json
import os
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Dict, Optional, List, Tuple

# Curated lookup tool (NOT a full web browser).
# Intended for quick definitions / references while keeping the app stable.
#
# Sources:
# - Wikipedia (definitions / summaries)
# - Reddit (topic "vibe" + common themes from a recent thread)
#
# This module returns short summaries only. The UI decides whether to show them.

WIKI_SUMMARY_ENDPOINT = "https://en.wikipedia.org/api/rest_v1/page/summary/"
WIKI_SEARCH_ENDPOINT = "https://en.wikipedia.org/w/rest.php/v1/search/page?q={q}&limit=1"

REDDIT_SEARCH_ENDPOINT = "https://www.reddit.com/search.json?q={q}&limit=6&sort=relevance&t=week"

@dataclass
class ResearchResult:
    ok: bool
    title: str
    summary: str
    url: str

class ResearchEngine:
    def __init__(self, cache_path: str = "data/web_cache.json"):
        self.cache_path = cache_path
        self.cache: Dict[str, dict] = {}
        self.enabled = True

        # Rate limiting
        self.min_interval_s = 3.0
        self._last_request_t = 0.0

        self._load_cache()

    def _load_cache(self):
        try:
            if os.path.exists(self.cache_path):
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    self.cache = json.load(f)
            else:
                self.cache = {}
        except Exception:
            self.cache = {}

    def _save_cache(self):
        try:
            os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def set_enabled(self, v: bool):
        self.enabled = bool(v)

    # ---------------- Wikipedia ----------------

    def lookup_wikipedia(self, query: str, timeout_s: float = 6.0) -> ResearchResult:
        q = " ".join(query.strip().split())
        if not q:
            return ResearchResult(False, "", "", "")

        key = "wiki:" + q.lower()
        cached = self.cache.get(key)
        if cached and (time.time() - cached.get("t", 0)) < 60 * 60 * 24 * 7:
            return ResearchResult(True, cached.get("title", ""), cached.get("summary", ""), cached.get("url", ""))

        self._polite_rate_limit()

        # Direct summary guess
        title_guess = q.replace(" ", "_")
        url = WIKI_SUMMARY_ENDPOINT + urllib.parse.quote(title_guess, safe="")
        try:
            data = self._fetch_json(url, timeout_s=timeout_s)
            if data and "extract" in data and data.get("type") != "disambiguation":
                title = data.get("title", q)
                summary = (data.get("extract") or "").strip()[:900]
                page_url = ""
                content_urls = data.get("content_urls") or {}
                desktop = content_urls.get("desktop") or {}
                page_url = desktop.get("page") or ""
                res = ResearchResult(True, title, summary, page_url)
                self.cache[key] = {"t": time.time(), "title": title, "summary": summary, "url": page_url}
                self._save_cache()
                return res
        except Exception:
            pass

        # Search fallback
        try:
            search_url = WIKI_SEARCH_ENDPOINT.format(q=urllib.parse.quote(q))
            sdata = self._fetch_json(search_url, timeout_s=timeout_s)
            pages = (sdata or {}).get("pages") or []
            if pages:
                title = pages[0].get("title") or q
                title_guess = title.replace(" ", "_")
                url = WIKI_SUMMARY_ENDPOINT + urllib.parse.quote(title_guess, safe="")
                data = self._fetch_json(url, timeout_s=timeout_s)
                if data and "extract" in data:
                    summary = (data.get("extract") or "").strip()[:900]
                    content_urls = data.get("content_urls") or {}
                    desktop = content_urls.get("desktop") or {}
                    page_url = desktop.get("page") or ""
                    res = ResearchResult(True, title, summary, page_url)
                    self.cache[key] = {"t": time.time(), "title": title, "summary": summary, "url": page_url}
                    self._save_cache()
                    return res
        except Exception:
            pass

        return ResearchResult(False, q, "", "")

    # ---------------- Reddit ----------------

    def lookup_reddit(self, topic: str, timeout_s: float = 7.0) -> ResearchResult:
        q = " ".join(topic.strip().split())
        if not q:
            return ResearchResult(False, "", "", "")

        key = "reddit:" + q.lower()
        cached = self.cache.get(key)
        if cached and (time.time() - cached.get("t", 0)) < 60 * 60 * 12:
            return ResearchResult(True, cached.get("title", ""), cached.get("summary", ""), cached.get("url", ""))

        self._polite_rate_limit()

        try:
            url = REDDIT_SEARCH_ENDPOINT.format(q=urllib.parse.quote(q))
            data = self._fetch_json(url, timeout_s=timeout_s)
            posts = ((data or {}).get("data") or {}).get("children") or []
            if not posts:
                return ResearchResult(False, f"Reddit: {q}", "No recent results.", "")

            # pick the first non-nsfw post with a permalink
            chosen = None
            for p in posts:
                d = (p or {}).get("data") or {}
                if d.get("over_18"):
                    continue
                if not d.get("permalink"):
                    continue
                chosen = d
                break
            if not chosen:
                chosen = (posts[0] or {}).get("data") or {}

            permalink = chosen.get("permalink") or ""
            thread_url = "https://www.reddit.com" + permalink
            title = chosen.get("title") or q
            subreddit = chosen.get("subreddit") or ""

            # Fetch thread JSON for top comments
            tdata = self._fetch_json(thread_url + ".json?limit=12&sort=top", timeout_s=timeout_s)
            comments = self._extract_top_comments(tdata, limit=14)

            # Heuristic summarization: themes + sentiment
            summary = self._summarize_comments(title, subreddit, comments)

            res = ResearchResult(True, f"Reddit/{subreddit}: {title}" if subreddit else f"Reddit: {title}", summary[:900], thread_url)
            self.cache[key] = {"t": time.time(), "title": res.title, "summary": res.summary, "url": res.url}
            self._save_cache()
            return res
        except Exception:
            return ResearchResult(False, f"Reddit: {q}", "Lookup failed.", "")

    def _extract_top_comments(self, thread_json: object, limit: int = 12) -> List[str]:
        out: List[str] = []
        try:
            if not isinstance(thread_json, list) or len(thread_json) < 2:
                return out
            comments_listing = thread_json[1]
            children = (((comments_listing or {}).get("data") or {}).get("children") or [])
            for c in children:
                d = (c or {}).get("data") or {}
                body = (d.get("body") or "").strip()
                if not body:
                    continue
                if body.lower() in ("[deleted]", "[removed]"):
                    continue
                # lightly clean
                body = body.replace("\n", " ")
                body = " ".join(body.split())
                if len(body) < 20:
                    continue
                out.append(body[:420])
                if len(out) >= limit:
                    break
        except Exception:
            return out
        return out

    def _summarize_comments(self, title: str, subreddit: str, comments: List[str]) -> str:
        if not comments:
            return "No top comments available."

        # simple keyword frequency
        stop = set(["the","a","an","and","or","but","if","then","this","that","to","of","in","on","for","with","is","are","was","were","be","been","as","it","i","you","we","they","them","my","your","our","me","so","just","really","very","not","do","does","did","can","could","would","should","from","at","by","about","into","over","under"])
        freq: Dict[str,int] = {}
        pos_words = set(["love","like","great","good","amazing","helpful","better","best","agree","right","true","works","recommend","interesting"]) 
        neg_words = set(["hate","bad","worse","worst","awful","terrible","stupid","dumb","wrong","fake","scam","doesn't","broken","annoying"]) 

        pos = 0
        neg = 0
        for c in comments:
            low = c.lower()
            for w in pos_words:
                if w in low:
                    pos += 1
            for w in neg_words:
                if w in low:
                    neg += 1
            # token freq
            toks = [t.strip(".,!?;:()[]{}\"'`") for t in low.split()]
            for t in toks:
                if len(t) < 4 or len(t) > 18:
                    continue
                if t in stop:
                    continue
                if t.startswith("http"):
                    continue
                freq[t] = freq.get(t, 0) + 1

        top = sorted(freq.items(), key=lambda kv: kv[1], reverse=True)[:10]
        themes = [k for k,_ in top[:6]]

        vibe = "mixed"
        if pos > neg + 2:
            vibe = "mostly positive"
        elif neg > pos + 2:
            vibe = "mostly negative"

        # compress themes
        theme_line = ", ".join(themes) if themes else "(no strong repeating themes)"

        # synthesize a short narrative without quoting comments verbatim
        lines: List[str] = []
        if subreddit:
            lines.append(f"Recent thread vibe in r/{subreddit}: {vibe}.")
        else:
            lines.append(f"Recent thread vibe: {vibe}.")
        lines.append(f"Common themes: {theme_line}.")
        # add one 'signal' sentence based on vibe
        if vibe == "mostly positive":
            lines.append("People are leaning toward practical advice and shared experiences.")
        elif vibe == "mostly negative":
            lines.append("People are pushing back, pointing out downsides and edge cases.")
        else:
            lines.append("Opinions are split; arguments cluster around tradeoffs and personal context.")

        return " ".join(lines)[:900]

    # ---------------- router ----------------

    def lookup(self, query: str) -> ResearchResult:
        if not self.enabled:
            return ResearchResult(False, "", "", "")

        q = " ".join(query.strip().split())
        if not q:
            return ResearchResult(False, "", "", "")

        low = q.lower()
        if low.startswith("reddit:"):
            return self.lookup_reddit(q.split(":", 1)[1].strip())
        if low.startswith("r/"):
            # treat subreddit name as a topic
            return self.lookup_reddit(q)

        return self.lookup_wikipedia(q)

    # ---------------- utils ----------------

    def _polite_rate_limit(self):
        now = time.time()
        wait = self.min_interval_s - (now - self._last_request_t)
        if wait > 0:
            time.sleep(min(wait, 0.4))
        self._last_request_t = time.time()

    def _fetch_json(self, url: str, timeout_s: float = 6.0) -> Optional[dict]:
        req = urllib.request.Request(
            url,
            headers={
                # Reddit requires a UA; Wikipedia is also fine with this.
                "User-Agent": "ChatSpace/1.1 (local game research; contact: none)",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read(1024 * 1024)  # cap 1MB
        return json.loads(raw.decode("utf-8", errors="replace"))
