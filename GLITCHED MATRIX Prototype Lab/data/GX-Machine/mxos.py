#!/usr/bin/env python3
"""Minimal MXOS standalone shell.

This cleaned build keeps MXOS as a small prototype/tool launcher only.
ChatSpace, game generation, salvage, scanners, validators, reviewers, and
nonfunctional legacy controls are intentionally not included here.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path
import tkinter as tk
from tkinter import BOTH, END, LEFT, RIGHT, Frame, Label, Button, Canvas, messagebox
import tkinter.ttk as ttk

APP_BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = APP_BASE_DIR / "data"
PROTOTYPE_ROOT = DATA_DIR / "Prototype Lab"
HOLOVERSE_MAIN = DATA_DIR / "HoloVerse" / "main.py"
MATRIXCORE_DIR = DATA_DIR / "database" / "MatrixCore"

THEME = {
    "bg": "#020304",
    "panel": "#05090b",
    "panel2": "#071013",
    "line": "#203236",
    "text": "#e8f4f6",
    "muted": "#91a6ad",
    "accent": "#efff3f",
    "cyan": "#21d8e8",
    "danger": "#ff4a4a",
}


def _safe_rel(path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(APP_BASE_DIR.resolve()))
    except Exception:
        return str(path)


def _find_entry(folder: Path) -> Path | None:
    preferred = [folder / "main.py", folder / "launcher.py", folder / f"{folder.name}.py", folder / f"{folder.name.replace(' ', '_')}.py"]
    for p in preferred:
        if p.exists() and p.is_file():
            return p
    try:
        py = sorted([p for p in folder.glob("*.py") if p.name.lower() not in {"sound_handler.py", "sfx.py"}], key=lambda p: p.name.lower())
        if len(py) == 1:
            return py[0]
    except Exception:
        pass
    return None


class MinimalMXOS:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("MXOS - Minimal Prototype Workspace")
        self.root.configure(bg=THEME["bg"])
        self.root.geometry("1100x760")
        self.root.minsize(900, 560)
        self.items: list[dict] = []
        self.selected: dict | None = None
        self.tiles: list[tk.Misc] = []
        self.status = tk.StringVar(value="MXOS ready.")
        self._build()
        self.refresh()

    def _button(self, parent, text, command, accent=False, danger=False):
        bg = "#18251a" if accent else ("#300709" if danger else "#10191d")
        fg = THEME["accent"] if accent else ("#ffffff" if danger else THEME["text"])
        return Button(parent, text=text, command=command, bg=bg, fg=fg, activebackground="#1b2d32", activeforeground="#ffffff", relief="flat", bd=0, padx=18, pady=10, font=("Consolas", 10, "bold"), cursor="hand2")

    def _build(self) -> None:
        top = Frame(self.root, bg=THEME["bg"])
        top.pack(side="top", fill="x", padx=18, pady=(16, 8))
        Label(top, text="MXOS", bg=THEME["bg"], fg=THEME["accent"], font=("Consolas", 24, "bold")).pack(side=LEFT)
        Label(top, text="  Minimal prototype/tool workspace", bg=THEME["bg"], fg=THEME["muted"], font=("Segoe UI", 10)).pack(side=LEFT, padx=8)
        self._button(top, "EXIT", self.root.destroy, danger=True).pack(side=RIGHT)
        self._button(top, "REFRESH", self.refresh).pack(side=RIGHT, padx=8)
        self._button(top, "RUN SELECTED", self.run_selected, accent=True).pack(side=RIGHT, padx=8)

        host = Frame(self.root, bg=THEME["panel"], highlightthickness=1, highlightbackground=THEME["line"])
        host.pack(side="top", fill=BOTH, expand=True, padx=18, pady=(0, 8))
        host.grid_rowconfigure(0, weight=1)
        host.grid_columnconfigure(0, weight=1)
        self.canvas = Canvas(host, bg=THEME["panel"], bd=0, highlightthickness=0)
        self.scroll = ttk.Scrollbar(host, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scroll.grid(row=0, column=1, sticky="ns")
        self.inner = Frame(self.canvas, bg=THEME["panel"])
        self.win = self.canvas.create_window((0,0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._sync)
        self.canvas.bind("<Configure>", self._sync)
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.inner.bind("<MouseWheel>", self._wheel)

        bottom = Frame(self.root, bg=THEME["bg"])
        bottom.pack(side="bottom", fill="x", padx=18, pady=(0, 14))
        Label(bottom, textvariable=self.status, bg=THEME["bg"], fg=THEME["muted"], font=("Segoe UI", 10), anchor="w").pack(side=LEFT, fill="x", expand=True)
        self._button(bottom, "OPEN FOLDER", self.open_selected_folder).pack(side=RIGHT, padx=8)

    def _sync(self, _event=None):
        try:
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            self.canvas.itemconfigure(self.win, width=max(700, self.canvas.winfo_width()))
        except Exception:
            pass

    def _wheel(self, event):
        try:
            self.canvas.yview_scroll((-1 if event.delta > 0 else 1) * 3, "units")
            return "break"
        except Exception:
            return None

    def _discover(self) -> list[dict]:
        items = []
        if HOLOVERSE_MAIN.exists():
            items.append({"name": "HoloVerse", "type": "System", "entry": HOLOVERSE_MAIN, "folder": HOLOVERSE_MAIN.parent})
        items.append({"name": "Prototype Lab", "type": "Folder", "entry": None, "folder": PROTOTYPE_ROOT})
        items.append({"name": "MatrixCore", "type": "Folder", "entry": None, "folder": MATRIXCORE_DIR})
        if PROTOTYPE_ROOT.exists():
            seen=set()
            for folder in sorted([p for p in PROTOTYPE_ROOT.rglob("*") if p.is_dir()], key=lambda p: p.name.lower()):
                if folder.name.lower() in {"assets", "screenshots", "__pycache__", "logs", "saves", "sound", "sounds", "music"}:
                    continue
                entry = _find_entry(folder)
                if entry and str(entry.resolve()).lower() not in seen:
                    seen.add(str(entry.resolve()).lower())
                    items.append({"name": folder.name, "type": "Prototype", "entry": entry, "folder": folder})
        return items

    def refresh(self):
        self.items = self._discover()
        self.tiles.clear()
        for child in list(self.inner.winfo_children()):
            child.destroy()
        cols = 4
        for c in range(cols):
            self.inner.grid_columnconfigure(c, weight=1, uniform="icon")
        for idx, item in enumerate(self.items):
            tile = self._tile(self.inner, item)
            tile.grid(row=idx//cols, column=idx%cols, sticky="nsew", padx=12, pady=12)
        if self.items:
            self.select(self.items[0], self.tiles[0])
        self.status.set(f"{len(self.items)} item(s) ready.")

    def _tile(self, parent, item):
        tile = Frame(parent, bg=THEME["panel2"], highlightthickness=2, highlightbackground=THEME["line"])
        tile.grid_columnconfigure(0, weight=1)
        icon = Canvas(tile, width=150, height=92, bg="#020506", bd=0, highlightthickness=1, highlightbackground="#30464a")
        icon.grid(row=0, column=0, pady=(14, 8))
        initials = "".join(part[:1] for part in item["name"].split()[:2]).upper() or "MX"
        icon.create_oval(38, 14, 112, 82, outline="#14363c", width=3)
        icon.create_oval(62, 30, 88, 56, fill=THEME["accent"], outline="")
        icon.create_text(75, 43, text=initials, fill="#020506", font=("Consolas", 15, "bold"))
        icon.create_text(75, 80, text=item["type"].upper(), fill="#789096", font=("Consolas", 8, "bold"))
        Label(tile, text=item["name"].upper(), bg=THEME["panel2"], fg=THEME["text"], font=("Consolas", 12, "bold"), wraplength=190, justify="center").grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 4))
        Label(tile, text=_safe_rel(Path(item["folder"])), bg=THEME["panel2"], fg=THEME["muted"], font=("Segoe UI", 8), wraplength=200, justify="center").grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 12))
        self.tiles.append(tile)
        for w in (tile, icon):
            w.bind("<Button-1>", lambda e, i=item, t=tile: self.select(i, t))
            w.bind("<Double-1>", lambda e, i=item, t=tile: (self.select(i, t), self.run_selected()))
            w.bind("<MouseWheel>", self._wheel)
        return tile

    def select(self, item, tile):
        self.selected = item
        for t in self.tiles:
            t.configure(highlightbackground=THEME["line"])
        if tile:
            tile.configure(highlightbackground=THEME["accent"])
        self.status.set(f"Selected {item['name']}.")

    def run_selected(self):
        item = self.selected
        if not item:
            self.status.set("Select an item first.")
            return
        entry = item.get("entry")
        if entry and Path(entry).exists():
            try:
                subprocess.Popen([sys.executable, str(entry)], cwd=str(Path(entry).parent))
                self.status.set(f"Launched {item['name']}.")
            except Exception as exc:
                messagebox.showerror("MXOS", f"Could not launch {item['name']}:\n{exc}")
        else:
            self.open_selected_folder()

    def open_selected_folder(self):
        item = self.selected
        folder = Path(item.get("folder")) if item else APP_BASE_DIR
        try:
            if os.name == "nt":
                os.startfile(str(folder))
            else:
                subprocess.Popen(["xdg-open", str(folder)])
            self.status.set(f"Opened {folder.name}.")
        except Exception as exc:
            messagebox.showerror("MXOS", f"Could not open folder:\n{exc}")


def main() -> None:
    root = tk.Tk()
    MinimalMXOS(root)
    root.mainloop()


if __name__ == "__main__":
    main()
