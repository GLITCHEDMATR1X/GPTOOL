import time
from typing import List

def clamp(v: float, a: float, b: float) -> float:
    return a if v < a else (b if v > b else v)

def now_iso() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")

def wrap_text_lines(font, text: str, max_width: int) -> List[str]:
    # Simple greedy wrapper
    words = text.split(" ")
    lines: List[str] = []
    cur = ""
    for w in words:
        test = (cur + " " + w).strip()
        if font.size(test)[0] <= max_width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines
