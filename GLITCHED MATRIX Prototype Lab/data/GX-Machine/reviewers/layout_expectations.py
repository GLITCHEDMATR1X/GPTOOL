from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Dict, List, Any


@dataclass
class Zone:
    name: str
    x0: float
    y0: float
    x1: float
    y1: float
    purpose: str
    ui_allowed: bool
    weight: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _gameplay_zones() -> List[Zone]:
    return [
        Zone('top_left_hud', 0.00, 0.00, 0.22, 0.20, 'corner_hud', True, 0.7),
        Zone('top_right_hud', 0.78, 0.00, 1.00, 0.20, 'corner_hud', True, 0.7),
        Zone('bottom_left_hud', 0.00, 0.78, 0.28, 1.00, 'dialog_or_hud', True, 0.8),
        Zone('bottom_right_hud', 0.72, 0.78, 1.00, 1.00, 'dialog_or_hud', True, 0.8),
        Zone('left_side_panel', 0.00, 0.18, 0.18, 0.82, 'side_panel', True, 0.5),
        Zone('right_side_panel', 0.82, 0.18, 1.00, 0.82, 'side_panel', True, 0.5),
        Zone('center_gameplay', 0.18, 0.14, 0.82, 0.86, 'primary_action', False, 1.0),
    ]


def _editor_zones() -> List[Zone]:
    return [
        Zone('top_toolbar', 0.00, 0.00, 1.00, 0.10, 'toolbar', True, 0.7),
        Zone('left_tools', 0.00, 0.10, 0.20, 0.90, 'tool_stack', True, 0.8),
        Zone('right_inspector', 0.78, 0.10, 1.00, 0.90, 'inspector', True, 0.8),
        Zone('bottom_status', 0.00, 0.90, 1.00, 1.00, 'status', True, 0.7),
        Zone('center_canvas', 0.20, 0.10, 0.78, 0.90, 'workspace', False, 1.0),
    ]


def _showcase_zones() -> List[Zone]:
    return [
        Zone('caption_strip', 0.00, 0.88, 1.00, 1.00, 'caption_optional', True, 0.3),
        Zone('subject_core', 0.22, 0.10, 0.78, 0.88, 'main_subject', False, 1.0),
        Zone('left_balance', 0.00, 0.10, 0.22, 0.88, 'negative_space_or_secondary', True, 0.4),
        Zone('right_balance', 0.78, 0.10, 1.00, 0.88, 'negative_space_or_secondary', True, 0.4),
    ]


def _menu_zones() -> List[Zone]:
    return [
        Zone('title_band', 0.18, 0.04, 0.82, 0.18, 'title', True, 0.8),
        Zone('left_nav', 0.06, 0.20, 0.34, 0.92, 'primary_navigation', True, 0.9),
        Zone('right_content', 0.36, 0.20, 0.94, 0.92, 'primary_content', True, 0.9),
        Zone('center_deadzone', 0.34, 0.28, 0.66, 0.78, 'avoid_unplanned_overlap', True, 0.4),
    ]


PROFILES: Dict[str, Dict[str, Any]] = {
    'gameplay': {
        'name': 'gameplay',
        'zones': [z.to_dict() for z in _gameplay_zones()],
        'target': {
            'mean_luminance_min': 0.18,
            'contrast_std_min': 0.14,
            'center_clearance_min': 0.62,
            'edge_pressure_max': 0.58,
            'corner_pressure_max': 0.40,
            'center_subject_preferred': True,
        },
    },
    'editor': {
        'name': 'editor',
        'zones': [z.to_dict() for z in _editor_zones()],
        'target': {
            'mean_luminance_min': 0.20,
            'contrast_std_min': 0.12,
            'center_clearance_min': 0.12,
            'edge_pressure_max': 0.68,
            'corner_pressure_max': 0.54,
            'center_subject_preferred': False,
        },
    },
    'showcase': {
        'name': 'showcase',
        'zones': [z.to_dict() for z in _showcase_zones()],
        'target': {
            'mean_luminance_min': 0.20,
            'contrast_std_min': 0.15,
            'center_clearance_min': 0.45,
            'edge_pressure_max': 0.48,
            'corner_pressure_max': 0.32,
            'center_subject_preferred': True,
        },
    },
    'menu': {
        'name': 'menu',
        'zones': [z.to_dict() for z in _menu_zones()],
        'target': {
            'mean_luminance_min': 0.24,
            'contrast_std_min': 0.13,
            'center_clearance_min': 0.30,
            'edge_pressure_max': 0.70,
            'corner_pressure_max': 0.55,
            'center_subject_preferred': False,
        },
    },
}


def get_layout_profile(name: str) -> Dict[str, Any]:
    normalized = (name or 'gameplay').strip().lower()
    aliases = {
        'tool_editor': 'editor',
        'placement_editor': 'editor',
        'tool': 'editor',
        'ui_menu': 'menu',
        'main_menu': 'menu',
        '3d_showcase': 'showcase',
    }
    resolved = aliases.get(normalized, normalized)
    return PROFILES.get(resolved, PROFILES['gameplay'])
