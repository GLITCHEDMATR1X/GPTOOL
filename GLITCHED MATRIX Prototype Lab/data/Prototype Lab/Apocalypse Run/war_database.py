from __future__ import annotations

import json
import re
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def _safe_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding='utf-8')


class ConflictIntelDB:
    """Small persistence layer for war-map intel, conflict history, and feed text.

    The older story/database app is repurposed here as backend storage instead of a
    separate primary UI. The map remains the main experience.
    """

    def __init__(self, base_dir: Optional[Path] = None, max_recent: int = 80) -> None:
        self.base_dir = Path(base_dir) if base_dir else Path(__file__).resolve().parent
        self.db_dir = self.base_dir / 'database' / 'war_conflicts'
        self.campaign_dir = self.db_dir / 'campaigns'
        self.event_dir = self.db_dir / 'events'
        self.story_dir = self.db_dir / 'stories'
        self.snapshot_path = self.campaign_dir / 'current_campaign.json'
        self.story_path = self.story_dir / 'battle_feed_story.json'
        self.event_log_path = self.event_dir / 'event_log.jsonl'
        self.recent_events: deque[dict[str, Any]] = deque(maxlen=max_recent)
        self._last_sync_tick: Optional[int] = None
        self._ensure_layout()
        self._seed_story_bank()
        self._load_recent()

    def _ensure_layout(self) -> None:
        self.campaign_dir.mkdir(parents=True, exist_ok=True)
        self.event_dir.mkdir(parents=True, exist_ok=True)
        self.story_dir.mkdir(parents=True, exist_ok=True)

    def _seed_story_bank(self) -> None:
        if self.story_path.exists():
            return
        payload = {
            'tone': 'war-room',
            'description': 'Context fragments used by the live battle feed in the world map sidebar.',
            'fragments': {
                'theater': [
                    'The front is unstable and command channels are saturated.',
                    'Border pressure keeps shifting where troop surplus spikes.',
                    'Industrial output and frontline momentum are now the decisive levers.'
                ],
                'air': [
                    'Strike craft are sweeping above the theater.',
                    'Air cover is active and target priorities are changing in real time.'
                ],
                'ground': [
                    'Ground skirmishes are feeding back into regional control.',
                    'Local engagements are being rolled into the macro campaign.'
                ]
            }
        }
        _safe_write_json(self.story_path, payload)

    def _load_recent(self) -> None:
        if not self.event_log_path.exists():
            return
        try:
            lines = self.event_log_path.read_text(encoding='utf-8').splitlines()[-self.recent_events.maxlen:]
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if isinstance(obj, dict):
                    self.recent_events.append(obj)
        except Exception:
            self.recent_events.clear()

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def sync_from_world(self, sim: Any) -> None:
        try:
            factions = []
            for fid, faction in sorted(sim.factions.items()):
                factions.append({
                    'fid': int(fid),
                    'name': str(faction.name),
                    'style': str(faction.style),
                    'color': list(getattr(faction, 'color', (0, 0, 0))),
                    'troops': round(float(getattr(faction, 'troops', 0.0)), 2),
                    'resources': round(float(getattr(faction, 'resources', 0.0)), 2),
                    'regions': sorted(int(r) for r in getattr(faction, 'regions', set())),
                    'buildings': dict(getattr(faction, 'buildings', {})),
                })
            payload = {
                'updated_at': self._now_iso(),
                'seed': int(getattr(sim, 'seed', 0)),
                'tick': int(getattr(sim, 'tick', 0)),
                'wars': sorted([[int(a), int(b)] for a, b in getattr(sim, 'wars', set())]),
                'player_fid': None if getattr(sim, 'player_fid', None) is None else int(sim.player_fid),
                'factions': factions,
            }
            _safe_write_json(self.snapshot_path, payload)
            self._last_sync_tick = int(getattr(sim, 'tick', 0))
        except Exception:
            return

    def maybe_sync(self, sim: Any, interval_ticks: int = 12) -> None:
        tick = int(getattr(sim, 'tick', 0))
        if self._last_sync_tick is None or abs(tick - self._last_sync_tick) >= max(1, int(interval_ticks)):
            self.sync_from_world(sim)

    def _translate_message(self, raw: str) -> str:
        raw = (raw or '').strip()
        if not raw:
            return 'INTEL // No report available.'

        invasion = re.match(r'^INVASION:\s*(.*?) begins an invasion against (.*?)\.$', raw)
        if invasion:
            return f'ALERT // {invasion.group(1)} opens a new offensive against {invasion.group(2)}.'

        conquest = re.match(r'^CONQUEST:\s*(.*?) destroys the Capital of region (\d+)\..*$', raw)
        if conquest:
            return f'SHIFT // {conquest.group(1)} breaks Region {conquest.group(2)} and folds it into their line.'

        elim = re.match(r'^ELIMINATED:\s*(.*?) has lost all regions and collapses as a faction\.$', raw)
        if elim:
            return f'COLLAPSE // {elim.group(1)} is erased from the campaign map.'

        build = re.match(r'^BUILD:\s*(.*?) completes a (.*?)\.$', raw)
        if build:
            return f'INDUSTRY // {build.group(1)} finishes a {build.group(2)} and deepens its war footing.'

        ground = re.match(r'^GROUND:\s*(.*)$', raw)
        if ground:
            return f'GROUND // {ground.group(1)}'

        mode = re.match(r'^MODE:([^:]+):(.*)$', raw)
        if mode:
            key = mode.group(1).strip().upper()
            detail = mode.group(2).strip()
            return f'{key} // {detail}'

        view = re.match(r'^VIEW:\s*(.*)$', raw)
        if view:
            return f'SCAN // {view.group(1)}'

        status = re.match(r'^Status:\s*(.*)$', raw)
        if status:
            return f'THEATER // {status.group(1)}'

        return f'INTEL // {raw}'

    def record_event(self, raw: str, tick: int, context: Optional[Dict[str, Any]] = None) -> None:
        translated = self._translate_message(raw)
        event = {
            'timestamp': self._now_iso(),
            'tick': int(tick),
            'raw': raw,
            'feed': translated,
            'context': context or {},
        }
        self.recent_events.appendleft(event)
        try:
            self.event_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.event_log_path.open('a', encoding='utf-8') as handle:
                handle.write(json.dumps(event) + '\n')
        except Exception:
            return

    def _frontline_summary(self, sim: Any, screen_ctx: Dict[str, Any]) -> List[str]:
        lines: List[str] = []
        active = sum(1 for f in sim.factions.values() if len(getattr(f, 'regions', [])) > 0)
        wars = getattr(sim, 'wars', set())
        lines.append(f'THEATER // {active} surviving powers, {len(wars)} active invasions.')

        player_fid = screen_ctx.get('player_fid')
        enemy_fid = screen_ctx.get('enemy_fid')
        if player_fid is not None and player_fid in sim.factions:
            pf = sim.factions[player_fid]
            if enemy_fid is not None and enemy_fid in sim.factions:
                ef = sim.factions[enemy_fid]
                lines.append(f'COMMAND // {pf.name} is currently aligned against {ef.name}.')
            else:
                lines.append(f'COMMAND // {pf.name} is waiting for the next live border clash.')

        cell = screen_ctx.get('inspected_cell') or screen_ctx.get('selected_cell')
        if cell:
            x, y = int(cell[0]), int(cell[1])
            try:
                rid = int(sim.region_at(x, y))
                owner = int(sim.owner_at(x, y))
                ruins = float(sim.ruins_at(x, y))
                owner_name = sim.factions[owner].name if owner in sim.factions else 'Unclaimed water'
                cell_line = f'SCAN // Cell {x},{y} sits in Region {rid} under {owner_name} control.'
                if ruins > 0.08:
                    cell_line += f' Ruin load {ruins:0.2f} indicates recent damage.'
                lines.append(cell_line)
            except Exception:
                pass

        if screen_ctx.get('air_mode'):
            lines.append('AIRSPACE // Strike craft are active over the map and hunting exposed targets.')
        if screen_ctx.get('mode_key') and screen_ctx.get('mode_key') != 'doomsday':
            lines.append(f'MODE // {str(screen_ctx.get("mode_key")).upper()} theater is active.')
        return lines

    def compose_feed(self, sim: Any, screen_ctx: Dict[str, Any], max_lines: int = 9) -> List[str]:
        lines: List[str] = []
        for line in self._frontline_summary(sim, screen_ctx):
            if line not in lines:
                lines.append(line)
        for item in list(self.recent_events):
            feed = str(item.get('feed', '')).strip()
            if not feed or feed in lines:
                continue
            lines.append(feed)
            if len(lines) >= max_lines:
                break
        return lines[:max_lines]
