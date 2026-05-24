from __future__ import annotations

from main import PoolroomsArtGame, install_crash_logger


class Level1Game(PoolroomsArtGame):
    def __init__(self) -> None:
        super().__init__()
        self.settings["quality_preset"] = "Low"
        self.settings["water_reflections"] = 0.0
        self.settings["tile_reflections"] = 0.0
        self.settings["dof_strength"] = 0.0
        self._sync_sliders_from_settings()
        self._apply_all_settings()
        self._load_level(1)


def main() -> None:
    install_crash_logger()
    game = Level1Game()
    game.run()


if __name__ == "__main__":
    main()
