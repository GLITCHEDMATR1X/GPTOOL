from __future__ import annotations

from pathlib import Path

from direct.gui.DirectButton import DirectButton
from direct.gui.DirectFrame import DirectFrame
from direct.gui.DirectLabel import DirectLabel
from direct.gui.DirectWaitBar import DirectWaitBar
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import TextNode

from .constants import BLOCK_DEFS, HOTBAR_IDS, ZONE_DEFS, ZONE_ORDER


class GameUI:
    def __init__(self, app):
        self.app = app
        self.help_visible = True
        self.debug_visible = False
        self.portal_visible = False
        self.portal_cards: dict[str, tuple[DirectButton, DirectLabel]] = {}

        self.crosshair = OnscreenText(
            text='+',
            pos=(0, -0.02),
            scale=0.085,
            fg=(1, 1, 1, 0.95),
            align=TextNode.ACenter,
            mayChange=True,
        )

        self.hotbar = OnscreenText(
            text='',
            pos=(0, -0.92),
            scale=0.05,
            fg=(1, 1, 1, 0.95),
            align=TextNode.ACenter,
            mayChange=True,
        )

        self.help_text = OnscreenText(
            text='',
            pos=(-1.28, 0.94),
            scale=0.043,
            fg=(0.92, 0.97, 1.0, 0.95),
            align=TextNode.ALeft,
            mayChange=True,
        )

        self.debug_text = OnscreenText(
            text='',
            pos=(-1.28, 0.58),
            scale=0.04,
            fg=(0.85, 1.0, 0.85, 0.95),
            align=TextNode.ALeft,
            mayChange=True,
        )

        self.status_text = OnscreenText(
            text='Ready',
            pos=(0, 0.88),
            scale=0.045,
            fg=(1.0, 0.95, 0.80, 0.95),
            align=TextNode.ACenter,
            mayChange=True,
        )

        self.zone_text = OnscreenText(
            text='Day Zone',
            pos=(1.27, 0.92),
            scale=0.05,
            fg=(0.95, 0.98, 1.0, 0.96),
            align=TextNode.ARight,
            mayChange=True,
        )

        self.menu_frame = DirectFrame(
            frameColor=(0.02, 0.03, 0.05, 0.95),
            frameSize=(-0.62, 0.62, -0.86, 0.46),
            pos=(0, 0, 0),
            parent=self.app.aspect2d,
        )
        self.menu_frame.hide()

        DirectLabel(
            parent=self.menu_frame,
            text='Zonez',
            text_scale=0.09,
            text_fg=(0.96, 0.98, 1.0, 1.0),
            frameColor=(0, 0, 0, 0),
            pos=(0, 0, 0.30),
        )
        DirectLabel(
            parent=self.menu_frame,
            text='Pause Menu',
            text_scale=0.045,
            text_fg=(0.62, 0.82, 1.0, 0.95),
            frameColor=(0, 0, 0, 0),
            pos=(0, 0, 0.22),
        )

        btn_style = dict(
            scale=0.07,
            frameSize=(-2.1, 2.1, -0.46, 0.46),
            text_fg=(0.96, 0.98, 1.0, 1.0),
            frameColor=(0.10, 0.14, 0.20, 0.98),
            pressEffect=1,
        )

        DirectButton(parent=self.menu_frame, text='Resume', pos=(0, 0, 0.08), command=self.app.toggle_pause, extraArgs=[False], **btn_style)
        DirectButton(parent=self.menu_frame, text='Zone Portal', pos=(0, 0, -0.04), command=self.app.toggle_zone_portal, extraArgs=[True], **btn_style)
        DirectButton(parent=self.menu_frame, text='Save World', pos=(0, 0, -0.16), command=self.app.save_game, **btn_style)
        DirectButton(parent=self.menu_frame, text='Load Save', pos=(0, 0, -0.28), command=self.app.load_game, **btn_style)
        DirectButton(parent=self.menu_frame, text='New Seed', pos=(0, 0, -0.40), command=self.app.regenerate_world, **btn_style)

        DirectLabel(
            parent=self.menu_frame,
            text='World Size',
            text_scale=0.042,
            text_fg=(0.82, 0.90, 1.0, 1.0),
            frameColor=(0, 0, 0, 0),
            pos=(0, 0, -0.54),
        )
        size_btn_style = dict(
            scale=0.07,
            frameSize=(-0.8, 0.8, -0.46, 0.46),
            text_fg=(0.96, 0.98, 1.0, 1.0),
            frameColor=(0.10, 0.14, 0.20, 0.98),
            pressEffect=1,
        )
        DirectButton(parent=self.menu_frame, text='-', pos=(-0.28, 0, -0.66), command=self.app.change_world_size, extraArgs=[-1], **size_btn_style)
        DirectButton(parent=self.menu_frame, text='+', pos=(0.28, 0, -0.66), command=self.app.change_world_size, extraArgs=[1], **size_btn_style)
        self.world_size_text = DirectLabel(
            parent=self.menu_frame,
            text='6 chunks',
            text_scale=0.046,
            text_fg=(1.0, 1.0, 1.0, 1.0),
            frameColor=(0, 0, 0, 0),
            pos=(0, 0, -0.66),
        )

        DirectButton(parent=self.menu_frame, text='Exit', pos=(0, 0, -0.78), command=self.app.exit_game, **btn_style)

        self.portal_frame = DirectFrame(
            frameColor=(0.02, 0.03, 0.05, 0.97),
            frameSize=(-1.25, 1.25, -0.72, 0.72),
            pos=(0, 0, 0),
            parent=self.app.aspect2d,
        )
        self.portal_frame.hide()

        DirectLabel(
            parent=self.portal_frame,
            text='ZONE PORTAL',
            text_scale=0.082,
            text_fg=(0.97, 0.99, 1.0, 1.0),
            frameColor=(0, 0, 0, 0),
            pos=(0, 0, 0.62),
        )
        DirectLabel(
            parent=self.portal_frame,
            text='Our buddies stay inside the zone bounds. We keep every zone secure.',
            text_scale=0.038,
            text_fg=(0.70, 0.86, 1.0, 0.96),
            frameColor=(0, 0, 0, 0),
            pos=(0, 0, 0.53),
        )
        DirectLabel(
            parent=self.portal_frame,
            text='Press Z or Esc to close',
            text_scale=0.034,
            text_fg=(0.74, 0.78, 0.84, 0.94),
            frameColor=(0, 0, 0, 0),
            pos=(0, 0, -0.66),
        )

        preview_size = (0.28, 0.16)
        x_positions = (-0.78, 0.0, 0.78)
        y_positions = (0.26, -0.14, -0.54)
        for index, zone_key in enumerate(ZONE_ORDER):
            zone = ZONE_DEFS[zone_key]
            col = index % 3
            row = index // 3
            x = x_positions[col]
            y = y_positions[row]
            frame = DirectButton(
                parent=self.portal_frame,
                text='',
                scale=1.0,
                frameSize=(-preview_size[0], preview_size[0], -preview_size[1], preview_size[1]),
                frameColor=(0.12, 0.16, 0.22, 0.98),
                relief=1,
                borderWidth=(0.012, 0.012),
                command=self.app.portal_select_zone,
                extraArgs=[zone_key],
                pos=(x, 0, y),
                pressEffect=1,
            )
            preview_path = self._resolve_zone_preview(zone_key)
            preview_tex = self._load_preview_texture(preview_path)
            if preview_tex is not None:
                frame['image'] = preview_tex
                frame['image_scale'] = (preview_size[0] - 0.01, 1.0, preview_size[1] - 0.01)
                frame['image_color'] = (1.0, 1.0, 1.0, 1.0)
            label = DirectLabel(
                parent=self.portal_frame,
                text=zone.name,
                text_scale=0.040,
                text_fg=(0.96, 0.98, 1.0, 1.0),
                frameColor=(0, 0, 0, 0),
                pos=(x, 0, y - 0.205),
            )
            self.portal_cards[zone_key] = (frame, label)

        self.loading_backdrop = DirectFrame(
            frameColor=(0.02, 0.03, 0.05, 1.0),
            frameSize=(-1.78, 1.78, -1.0, 1.0),
            pos=(0, 0, 0),
            parent=self.app.aspect2d,
        )
        self.loading_backdrop.hide()

        self.loading_frame = DirectFrame(
            parent=self.loading_backdrop,
            frameColor=(0.06, 0.08, 0.11, 0.97),
            frameSize=(-0.76, 0.76, -0.27, 0.27),
            pos=(0, 0, 0),
        )
        self.loading_frame.hide()

        self.loading_title = DirectLabel(
            parent=self.loading_frame,
            text='Zonez',
            text_scale=0.112,
            text_fg=(1, 1, 1, 1),
            frameColor=(0, 0, 0, 0),
            pos=(0, 0, 0.15),
        )

        self.loading_detail = DirectLabel(
            parent=self.loading_frame,
            text='',
            text_scale=0.045,
            text_fg=(0.84, 0.93, 1.0, 1.0),
            frameColor=(0, 0, 0, 0),
            pos=(0, 0, 0.02),
        )

        self.loading_bar = DirectWaitBar(
            parent=self.loading_frame,
            range=100,
            value=0,
            pos=(0, 0, -0.10),
            scale=0.56,
            frameSize=(-1.0, 1.0, -0.10, 0.10),
            frameColor=(0.08, 0.11, 0.14, 1.0),
            barColor=(0.36, 0.68, 0.96, 1.0),
            text='',
        )

        self.refresh_hotbar(0)
        self.refresh_help()
        self.refresh_world_size()
        self.refresh_debug('', hide=True)

    def _resolve_zone_preview(self, zone_key: str) -> Path | None:
        root = self.app.project_root
        ordered_candidates = [
            root / 'assets' / 'ui' / 'zone_previews' / f'{zone_key}.png',
            root / 'assets' / 'boundaries' / f'{zone_key}_horizon.png',
            root / 'assets' / 'boundaries' / 'default_horizon.png',
        ]
        for path in ordered_candidates:
            if path.exists():
                return path
        return None

    def _load_preview_texture(self, preview_path: Path | None):
        if preview_path is None:
            return None
        try:
            return self.app._safe_load_texture(preview_path)
        except Exception:
            return None

    def refresh_hotbar(self, selected_index: int) -> None:
        parts = []
        for idx, block_id in enumerate(HOTBAR_IDS, start=1):
            label = BLOCK_DEFS[block_id].name
            if idx - 1 == selected_index:
                parts.append(f'[{idx}:{label}]')
            else:
                parts.append(f'{idx}:{label}')
        self.hotbar.setText('   '.join(parts))

    def refresh_help(self) -> None:
        if not self.help_visible:
            self.help_text.hide()
            return
        self.help_text.show()
        self.help_text.setText(
            'WASD fly   Space up   L-Alt down   Shift boost\n'
            'Mouse look   Arrows turn/look   Wheel zoom\n'
            '0 polar   1-5 zones   6 desert   7/9 tropical   8 tech zone   Tab next zone\n'
            'Z zone portal   V camera mode   H help   F3 debug   [ ] world size\n'
            'Esc pause / menu   Buddies stay inside the zone bounds'
        )

    def refresh_debug(self, text: str, hide: bool = False) -> None:
        if hide or not self.debug_visible:
            self.debug_text.hide()
            return
        self.debug_text.show()
        self.debug_text.setText(text)

    def set_status(self, text: str) -> None:
        self.status_text.setText(text)

    def set_zone(self, text: str) -> None:
        self.zone_text.setText(text)
        self.refresh_zone_portal()

    def toggle_help(self) -> None:
        self.help_visible = not self.help_visible
        self.refresh_help()

    def toggle_debug(self) -> None:
        self.debug_visible = not self.debug_visible
        self.refresh_debug('', hide=not self.debug_visible)

    def refresh_world_size(self) -> None:
        if hasattr(self, 'world_size_text'):
            chunks = int(self.app.world.get_world_size_chunks())
            units = int(self.app.world.get_boundary_half_extent() * 2)
            self.world_size_text['text'] = f'{chunks} chunks ({units}u)'

    def show_menu(self, visible: bool) -> None:
        self.refresh_world_size()
        if visible:
            self.menu_frame.show()
        else:
            self.menu_frame.hide()

    def refresh_zone_portal(self) -> None:
        for zone_key, (frame, label) in self.portal_cards.items():
            is_current = zone_key == self.app.active_zone_key
            frame['frameColor'] = (0.22, 0.40, 0.62, 0.98) if is_current else (0.12, 0.16, 0.22, 0.98)
            label['text_fg'] = (1.0, 1.0, 1.0, 1.0) if is_current else (0.90, 0.94, 1.0, 1.0)

    def show_zone_portal(self, visible: bool) -> None:
        self.portal_visible = visible
        if visible:
            self.refresh_zone_portal()
            self.portal_frame.show()
        else:
            self.portal_frame.hide()

    def show_loading(self, title: str, detail: str = '', progress: float = 0.0) -> None:
        self.loading_title['text'] = 'Zones'
        action = title.strip()
        if detail.strip():
            action = f'{action}\n{detail.strip()}'
        self.set_loading_detail(action)
        self.set_loading_progress(progress)
        self.loading_backdrop.show()
        self.loading_frame.show()

    def set_loading_detail(self, detail: str) -> None:
        self.loading_detail['text'] = detail

    def set_loading_progress(self, progress: float) -> None:
        value = max(0.0, min(1.0, progress))
        self.loading_bar['value'] = int(round(value * 100.0))

    def hide_loading(self) -> None:
        self.loading_frame.hide()
        self.loading_backdrop.hide()
