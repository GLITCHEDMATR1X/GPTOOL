#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pygame

VIRTUAL_W, VIRTUAL_H = 1920, 1080
ROOT = Path(__file__).resolve().parent
APP_TITLE = "Side Modes"
BG = (7, 10, 16)
PANEL = (12, 18, 28)
PANEL2 = (18, 26, 40)
TEXT = (230, 236, 244)
SUB = (150, 164, 180)
RED = (182, 46, 58)
GOLD = (196, 164, 102)
BLUE = (86, 126, 196)
GREEN = (88, 176, 130)
WARN = (220, 120, 82)

@dataclass
class Mode:
    key: str
    label: str
    filename: str
    desc: str
    color: tuple[int,int,int]

MODES = [
    Mode('hvh2','Heaven vs Hell II','hvh2.py','Uses the original HVH2 script and its own built-in assets path expectations.', RED),
    Mode('book','Book of Blood','book.py','Narrative side module.', BLUE),
]

def launch(mode: Mode) -> tuple[bool,str]:
    path = ROOT / mode.filename
    if not path.exists():
        return False, f"Missing {mode.filename}"
    try:
        proc = subprocess.run([sys.executable, str(path)], cwd=str(ROOT))
        return proc.returncode == 0, f"Returned from {mode.label} ({proc.returncode})."
    except Exception as exc:
        return False, f"Launch failed: {exc!r}"

class App:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption(APP_TITLE)
        self.screen = pygame.display.set_mode((VIRTUAL_W, VIRTUAL_H), pygame.RESIZABLE)
        self.virtual = pygame.Surface((VIRTUAL_W, VIRTUAL_H)).convert()
        self.clock = pygame.time.Clock()
        self.font_s = pygame.font.SysFont('consolas', 20)
        self.font_b = pygame.font.SysFont('consolas', 28)
        self.font_h = pygame.font.SysFont('consolas', 48, bold=True)
        self.sel = 0
        self.status = 'HVH1 removed. HVH2 kept as the active battle side mode.'
        self.status_color = SUB
        self.card_rects = []
    def vp(self):
        ww, wh = self.screen.get_size()
        scale = min(ww / VIRTUAL_W, wh / VIRTUAL_H)
        w = int(VIRTUAL_W*scale); h = int(VIRTUAL_H*scale)
        return pygame.Rect((ww-w)//2,(wh-h)//2,w,h)
    def draw(self):
        self.virtual.fill(BG)
        for y in range(VIRTUAL_H):
            t = y / max(1, VIRTUAL_H-1)
            c = (int(BG[0]*(1-t)+16*t), int(BG[1]*(1-t)+10*t), int(BG[2]*(1-t)+18*t))
            pygame.draw.line(self.virtual,c,(0,y),(VIRTUAL_W,y))
        title = self.font_h.render('Side Modes', True, TEXT)
        self.virtual.blit(title, (60, 42))
        sub = self.font_s.render('HVH1 removed. HVH2 and Book remain available here.', True, SUB)
        self.virtual.blit(sub, (64, 102))
        self.card_rects = []
        x, y = 64, 190
        for i, mode in enumerate(MODES):
            rect = pygame.Rect(x, y + i*210, 760, 168)
            self.card_rects.append(rect)
            pygame.draw.rect(self.virtual, PANEL2 if i==self.sel else PANEL, rect, border_radius=18)
            pygame.draw.rect(self.virtual, mode.color, rect, width=3, border_radius=18)
            self.virtual.blit(self.font_b.render(mode.label, True, TEXT), (rect.x+24, rect.y+18))
            lines = [mode.desc, f'File: {mode.filename}']
            for j, line in enumerate(lines):
                self.virtual.blit(self.font_s.render(line, True, SUB), (rect.x+24, rect.y+62+j*28))
        box = pygame.Rect(860, 190, 1000, 430)
        pygame.draw.rect(self.virtual, PANEL, box, border_radius=18)
        pygame.draw.rect(self.virtual, GOLD, box, width=3, border_radius=18)
        lines = [
            'Controls:',
            'Up/Down select',
            'Enter launch',
            'Esc quit',
            '',
            'Notes:',
            'HVH1 was removed from this launcher.',
            'HVH2 uses its original assets path again.',
            'No HVH asset folders are bundled in this return.',
            '',
            f'Status: {self.status}',
        ]
        yy = box.y + 22
        for idx, line in enumerate(lines):
            color = TEXT if idx in (0,5) else (self.status_color if idx == len(lines)-1 else SUB)
            self.virtual.blit(self.font_s.render(line, True, color), (box.x+24, yy))
            yy += 28
        vp = self.vp()
        self.screen.fill((0,0,0))
        self.screen.blit(pygame.transform.smoothscale(self.virtual, (vp.w, vp.h)), (vp.x, vp.y))
        pygame.display.flip()
    def run(self):
        running = True
        while running:
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    running = False
                elif e.type == pygame.KEYDOWN:
                    if e.key == pygame.K_ESCAPE:
                        running = False
                    elif e.key == pygame.K_UP:
                        self.sel = (self.sel - 1) % len(MODES)
                    elif e.key == pygame.K_DOWN:
                        self.sel = (self.sel + 1) % len(MODES)
                    elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        ok, msg = launch(MODES[self.sel])
                        self.status = msg
                        self.status_color = GREEN if ok else WARN
                elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    vp = self.vp()
                    if vp.collidepoint(e.pos):
                        mx = int((e.pos[0]-vp.x) * VIRTUAL_W / max(1,vp.w))
                        my = int((e.pos[1]-vp.y) * VIRTUAL_H / max(1,vp.h))
                        for i,r in enumerate(self.card_rects):
                            if r.collidepoint((mx,my)):
                                self.sel = i
                                ok, msg = launch(MODES[i])
                                self.status = msg
                                self.status_color = GREEN if ok else WARN
                                break
            self.draw()
            self.clock.tick(60)
        pygame.quit()

def parse_args():
    parser = argparse.ArgumentParser(description='Side mode launcher')
    parser.add_argument('--capture-frame', metavar='PNG_PATH')
    return parser.parse_args()

def main():
    args = parse_args()
    app = App()
    if args.capture_frame:
        app.draw()
        pygame.image.save(app.virtual, args.capture_frame)
        pygame.quit()
        return
    app.run()

if __name__ == '__main__':
    main()
