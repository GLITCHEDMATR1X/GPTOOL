"""
Dimension manager for HoloVerse layered biome content.

The world grid and terrain stay shared. The active dimension owns:
    * the drop-in asset folder used by surface placement
    * the neon grid color palette
    * future fauna/ambient rules

No UI is created here. main.py binds Tab and tells the outer world to cycle.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


Color = tuple[float, float, float, float]


@dataclass(frozen=True)
class GridPalette:
    """Line colors for one dimension layer."""

    minor: Color
    major: Color
    region: Color
    minor_glow: Color
    major_glow: Color
    region_glow: Color
    surface_tint: tuple[float, float, float]


@dataclass(frozen=True)
class DimensionDefinition:
    """Drop-in dimension/biome definition."""

    dimension_id: int
    name: str
    biome_folder: str
    palette: GridPalette


class DimensionManager:
    """Tracks the active layer without owning terrain or object placement."""

    def __init__(self, assets_root: Path) -> None:
        self.assets_root = assets_root
        self.dimensions: list[DimensionDefinition] = [
            DimensionDefinition(
                dimension_id=1,
                name="Sonar Ocean Floor",
                biome_folder="biome1",
                palette=GridPalette(
                    minor=(0.060, 0.70, 0.98, 0.25),
                    major=(0.12, 0.92, 1.00, 0.50),
                    region=(1.00, 0.060, 0.045, 0.62),
                    minor_glow=(0.040, 0.68, 1.00, 0.060),
                    major_glow=(0.10, 0.86, 1.00, 0.14),
                    region_glow=(1.00, 0.055, 0.040, 0.16),
                    surface_tint=(0.55, 0.80, 1.00),
                ),
            ),
            DimensionDefinition(
                dimension_id=2,
                name="Crystal Data Reef",
                biome_folder="biome2",
                palette=GridPalette(
                    minor=(0.58, 0.22, 1.00, 0.27),
                    major=(0.88, 0.46, 1.00, 0.52),
                    region=(0.12, 1.00, 0.72, 0.64),
                    minor_glow=(0.48, 0.18, 1.00, 0.070),
                    major_glow=(0.82, 0.38, 1.00, 0.16),
                    region_glow=(0.10, 1.00, 0.70, 0.18),
                    surface_tint=(0.85, 0.58, 1.00),
                ),
            ),
            DimensionDefinition(
                dimension_id=3,
                name="Bubble Lava Valleys",
                biome_folder="biome3",
                palette=GridPalette(
                    minor=(1.00, 0.34, 0.08, 0.24),
                    major=(1.00, 0.62, 0.12, 0.50),
                    region=(0.20, 0.95, 1.00, 0.58),
                    minor_glow=(1.00, 0.24, 0.05, 0.060),
                    major_glow=(1.00, 0.56, 0.08, 0.145),
                    region_glow=(0.16, 0.92, 1.00, 0.17),
                    surface_tint=(1.00, 0.46, 0.18),
                ),
            ),
            DimensionDefinition(
                dimension_id=4,
                name="Kelp Signal Shelf",
                biome_folder="biome1",
                palette=GridPalette(
                    minor=(0.14, 0.95, 0.78, 0.25),
                    major=(0.26, 1.00, 0.92, 0.52),
                    region=(0.90, 0.18, 1.00, 0.60),
                    minor_glow=(0.10, 0.88, 0.70, 0.065),
                    major_glow=(0.18, 1.00, 0.86, 0.15),
                    region_glow=(0.86, 0.14, 1.00, 0.17),
                    surface_tint=(0.38, 1.00, 0.78),
                ),
            ),
            DimensionDefinition(
                dimension_id=5,
                name="Amethyst Fault Spires",
                biome_folder="biome2",
                palette=GridPalette(
                    minor=(0.42, 0.42, 1.00, 0.28),
                    major=(0.62, 0.62, 1.00, 0.54),
                    region=(1.00, 0.32, 0.76, 0.62),
                    minor_glow=(0.36, 0.36, 1.00, 0.075),
                    major_glow=(0.58, 0.54, 1.00, 0.16),
                    region_glow=(1.00, 0.24, 0.70, 0.18),
                    surface_tint=(0.62, 0.62, 1.00),
                ),
            ),
            DimensionDefinition(
                dimension_id=6,
                name="Thermal Bubble Trench",
                biome_folder="biome3",
                palette=GridPalette(
                    minor=(1.00, 0.22, 0.16, 0.25),
                    major=(1.00, 0.48, 0.20, 0.52),
                    region=(0.12, 0.78, 1.00, 0.60),
                    minor_glow=(1.00, 0.18, 0.12, 0.070),
                    major_glow=(1.00, 0.42, 0.16, 0.15),
                    region_glow=(0.10, 0.74, 1.00, 0.18),
                    surface_tint=(1.00, 0.34, 0.22),
                ),
            ),
            DimensionDefinition(
                dimension_id=7,
                name="Abyssal Kelp Forest",
                biome_folder="biome4",
                palette=GridPalette(
                    minor=(0.02, 0.52, 0.42, 0.26),
                    major=(0.08, 0.92, 0.74, 0.52),
                    region=(0.24, 1.00, 0.38, 0.62),
                    minor_glow=(0.01, 0.48, 0.38, 0.070),
                    major_glow=(0.06, 0.88, 0.68, 0.155),
                    region_glow=(0.18, 1.00, 0.32, 0.18),
                    surface_tint=(0.14, 0.74, 0.58),
                ),
            ),
            DimensionDefinition(
                dimension_id=8,
                name="Mirror Glass Shoals",
                biome_folder="biome5",
                palette=GridPalette(
                    minor=(0.66, 0.92, 1.00, 0.24),
                    major=(0.86, 1.00, 1.00, 0.50),
                    region=(0.58, 0.36, 1.00, 0.60),
                    minor_glow=(0.58, 0.90, 1.00, 0.065),
                    major_glow=(0.82, 1.00, 1.00, 0.150),
                    region_glow=(0.52, 0.30, 1.00, 0.17),
                    surface_tint=(0.78, 0.94, 1.00),
                ),
            ),
            DimensionDefinition(
                dimension_id=9,
                name="Archive Ruins Reef",
                biome_folder="biome6",
                palette=GridPalette(
                    minor=(0.98, 0.70, 0.30, 0.25),
                    major=(1.00, 0.86, 0.48, 0.52),
                    region=(0.18, 0.88, 1.00, 0.62),
                    minor_glow=(0.92, 0.62, 0.22, 0.070),
                    major_glow=(1.00, 0.78, 0.34, 0.155),
                    region_glow=(0.12, 0.82, 1.00, 0.18),
                    surface_tint=(0.94, 0.70, 0.38),
                ),
            ),
            DimensionDefinition(
                dimension_id=10,
                name="Storm Current Trench",
                biome_folder="biome7",
                palette=GridPalette(
                    minor=(0.10, 0.28, 1.00, 0.26),
                    major=(0.26, 0.58, 1.00, 0.54),
                    region=(1.00, 0.08, 0.52, 0.62),
                    minor_glow=(0.06, 0.24, 1.00, 0.075),
                    major_glow=(0.20, 0.52, 1.00, 0.160),
                    region_glow=(1.00, 0.06, 0.46, 0.18),
                    surface_tint=(0.30, 0.48, 1.00),
                ),
            ),
        ]
        self.active_index = 0

    @property
    def active(self) -> DimensionDefinition:
        return self.dimensions[self.active_index]

    @property
    def active_asset_dir(self) -> Path:
        return self.assets_root / self.active.biome_folder

    def cycle_next(self) -> DimensionDefinition:
        self.active_index = (self.active_index + 1) % len(self.dimensions)
        return self.active

    def set_index(self, index: int) -> DimensionDefinition:
        if not self.dimensions:
            raise ValueError("No dimensions registered")
        self.active_index = int(index) % len(self.dimensions)
        return self.active

    def set_dimension(self, dimension_id: int) -> DimensionDefinition:
        for idx, definition in enumerate(self.dimensions):
            if definition.dimension_id == dimension_id:
                self.active_index = idx
                return definition
        raise ValueError(f"Unknown dimension id: {dimension_id}")
