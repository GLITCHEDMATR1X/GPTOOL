import re
from dataclasses import dataclass, field
from typing import Dict, List

STOPWORDS = {
    "the","a","an","and","or","but","if","then","so","to","of","in","on","at","for","with",
    "is","are","was","were","be","been","being","i","you","he","she","they","we","it","me",
    "my","your","our","their","this","that","these","those","as","not","do","did","does"
}

_word_re = re.compile(r"[a-zA-Z0-9']+")

def tokenize(text: str) -> List[str]:
    words = [w.lower() for w in _word_re.findall(text)]
    return [w for w in words if w and w not in STOPWORDS and 2 <= len(w) <= 24]

@dataclass
class Lexicon:
    weights: Dict[str, float] = field(default_factory=dict)
    phrases: List[str] = field(default_factory=list)

    def observe(self, text: str):
        toks = tokenize(text)
        for t in toks:
            self.weights[t] = self.weights.get(t, 0.0) + 1.0

        s = " ".join(text.strip().split())
        if 8 <= len(s) <= 100 and s.count(" ") >= 2:
            self.phrases.append(s)
            if len(self.phrases) > 80:
                self.phrases.pop(0)

    def decay(self, factor: float = 0.992):
        if not self.weights:
            return
        dead = []
        for k, v in self.weights.items():
            nv = v * factor
            if nv < 0.08:
                dead.append(k)
            else:
                self.weights[k] = nv
        for k in dead:
            self.weights.pop(k, None)

    def top_words(self, n: int = 6) -> List[str]:
        items = sorted(self.weights.items(), key=lambda kv: kv[1], reverse=True)
        return [k for k, _ in items[:n]]
