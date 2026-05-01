from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

TOOL_VERSION = "0.7.2-pass19-fauna-demo-sheet"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _rgba255(color: list[float]) -> tuple[int, int, int]:
    vals = list(color or [0.0, 0.8, 1.0, 1.0])
    while len(vals) < 4:
        vals.append(1.0)
    return tuple(max(0, min(255, int(float(v) * 255 if float(v) <= 1.0 else float(v)))) for v in vals[:3])


def _hex(color: list[float]) -> str:
    r, g, b = _rgba255(color)
    return f"#{r:02x}{g:02x}{b:02x}"


def _species_svg(spec: dict[str, Any], x: int, y: int, w: int, h: int) -> str:
    body = spec.get("body", "quadruped")
    color = _hex(spec.get("color", [0.0, 0.8, 1.0, 1]))
    accent = _hex(spec.get("accent", [0.9, 1.0, 1.0, 1]))
    name = html.escape(str(spec.get("name", "Fauna")))
    region = html.escape(str(spec.get("region", "HOLOVERSE")))
    bot = html.escape(str(spec.get("bot", "Guide")))
    traits = spec.get("traits") or []
    trait_text = html.escape(" • ".join(str(t) for t in traits[:2]))
    cx = x + w // 2
    cy = y + h // 2 - 6
    lines: list[str] = []
    lines.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" fill="#071015" stroke="{accent}" stroke-opacity="0.55"/>')
    lines.append(f'<text x="{cx}" y="{y+24}" text-anchor="middle" fill="{accent}" font-size="15" font-family="Consolas, monospace" font-weight="700">{name}</text>')
    lines.append(f'<text x="{cx}" y="{y+43}" text-anchor="middle" fill="#d8f6ff" font-size="11" font-family="Consolas, monospace">{region} // {bot}</text>')
    if body in {"bird", "flying_insect", "manta"}:
        lines.append(f'<ellipse cx="{cx-48}" cy="{cy}" rx="54" ry="18" fill="{accent}" fill-opacity="0.34" stroke="{accent}"/>')
        lines.append(f'<ellipse cx="{cx+48}" cy="{cy}" rx="54" ry="18" fill="{accent}" fill-opacity="0.34" stroke="{accent}"/>')
        lines.append(f'<ellipse cx="{cx}" cy="{cy}" rx="42" ry="24" fill="{color}" stroke="#ffffff" stroke-opacity="0.22"/>')
        lines.append(f'<circle cx="{cx+35}" cy="{cy-2}" r="13" fill="{color}" stroke="{accent}"/>')
        if body == "flying_insect":
            lines.append(f'<line x1="{cx-20}" y1="{cy-18}" x2="{cx-58}" y2="{cy-44}" stroke="{accent}" stroke-width="3"/>')
            lines.append(f'<line x1="{cx+20}" y1="{cy-18}" x2="{cx+58}" y2="{cy-44}" stroke="{accent}" stroke-width="3"/>')
    else:
        lines.append(f'<ellipse cx="{cx}" cy="{cy}" rx="56" ry="30" fill="{color}" stroke="#ffffff" stroke-opacity="0.22"/>')
        lines.append(f'<circle cx="{cx+48}" cy="{cy-7}" r="21" fill="{color}" stroke="{accent}"/>')
        lines.append(f'<path d="M {cx-55} {cy-4} C {cx-94} {cy-28}, {cx-104} {cy+20}, {cx-72} {cy+24}" fill="none" stroke="{accent}" stroke-width="8" stroke-linecap="round"/>')
        legs = 4 if body in {"quadruped", "fox", "lizard", "amphibian"} else 2
        for i in range(legs):
            lx = cx - 34 + i * (68 // max(1, legs - 1))
            lines.append(f'<line x1="{lx}" y1="{cy+24}" x2="{lx-7}" y2="{cy+54}" stroke="{color}" stroke-width="8" stroke-linecap="round"/>')
        if body in {"quadruped", "fox"}:
            lines.append(f'<path d="M {cx+40} {cy-27} L {cx+50} {cy-55} L {cx+59} {cy-27}" fill="{accent}"/>')
            lines.append(f'<path d="M {cx+58} {cy-25} L {cx+73} {cy-50} L {cx+75} {cy-20}" fill="{accent}"/>')
        if body == "lizard":
            lines.append(f'<path d="M {cx+65} {cy+2} L {cx+100} {cy+12} L {cx+65} {cy+19}" fill="{accent}"/>')
        if body == "amphibian":
            for dx in [-30, 0, 30]:
                lines.append(f'<circle cx="{cx+dx}" cy="{cy-30}" r="6" fill="{accent}"/>')
    lines.append(f'<text x="{cx}" y="{y+h-30}" text-anchor="middle" fill="#b8d8e8" font-size="10" font-family="Consolas, monospace">{trait_text}</text>')
    return "\n".join(lines)


def build_svg(manifest: dict[str, Any], *, title: str = "HoloVerse Fauna Demo Sheet") -> str:
    fauna = manifest.get("fauna") or []
    cols = 4
    card_w, card_h = 270, 210
    gap = 18
    margin = 28
    rows = max(1, (len(fauna) + cols - 1) // cols)
    width = margin * 2 + cols * card_w + (cols - 1) * gap
    height = 118 + rows * card_h + (rows - 1) * gap + margin
    pieces = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<defs><radialGradient id="bg" cx="50%" cy="30%" r="75%"><stop offset="0" stop-color="#06222b"/><stop offset="0.55" stop-color="#02080d"/><stop offset="1" stop-color="#000000"/></radialGradient></defs>',
        '<rect width="100%" height="100%" fill="url(#bg)"/>',
        '<g opacity="0.16" stroke="#00eaff" stroke-width="1">',
    ]
    for gx in range(0, width, 40):
        pieces.append(f'<line x1="{gx}" y1="0" x2="{gx}" y2="{height}"/>')
    for gy in range(0, height, 40):
        pieces.append(f'<line x1="0" y1="{gy}" x2="{width}" y2="{gy}"/>')
    pieces.extend([
        '</g>',
        f'<text x="{width//2}" y="42" text-anchor="middle" fill="#00f0ff" font-size="30" font-family="Consolas, monospace" font-weight="700">{html.escape(title)}</text>',
        f'<text x="{width//2}" y="70" text-anchor="middle" fill="#e7fbff" font-size="14" font-family="Consolas, monospace">Generated from GPTOOL fauna manifest // preview-only asset candidates</text>',
        f'<text x="{width//2}" y="94" text-anchor="middle" fill="#ffdd66" font-size="12" font-family="Consolas, monospace">Not a final HoloVerse merge. Use Panda3D screenshot proof before promotion.</text>',
    ])
    for i, spec in enumerate(fauna):
        col = i % cols
        row = i // cols
        x = margin + col * (card_w + gap)
        y = 118 + row * (card_h + gap)
        pieces.append(_species_svg(spec, x, y, card_w, card_h))
    pieces.append('</svg>')
    return "\n".join(pieces) + "\n"


def generate_sheet(preview_dir: str | Path, output: str | Path | None = None) -> dict[str, Any]:
    preview = Path(preview_dir).resolve()
    manifest_path = preview / "assets" / "fauna" / "fauna_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing fauna manifest: {manifest_path}")
    manifest = _read_json(manifest_path)
    out = Path(output).resolve() if output else preview / "reports" / "fauna_demo_sheet.svg"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_svg(manifest), encoding="utf-8")
    report = {
        "schema_version": "holoverse_fauna_demo_sheet_result.v1",
        "tool_version": TOOL_VERSION,
        "preview_dir": str(preview),
        "manifest": str(manifest_path),
        "output": str(out),
        "species_count": len(manifest.get("fauna") or []),
        "note": "SVG proof sheet is a fallback visual demonstration. Panda3D screenshot proof is still required before promotion.",
    }
    (preview / "reports").mkdir(parents=True, exist_ok=True)
    (preview / "reports" / "fauna_demo_sheet_result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a dependency-free SVG demo sheet from a HoloVerse fauna preview manifest.")
    parser.add_argument("preview_dir")
    parser.add_argument("--output")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = generate_sheet(args.preview_dir, args.output)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("HoloVerse fauna demo sheet: PASS")
        print(f"Output: {result['output']}")
        print(f"Species: {result['species_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
