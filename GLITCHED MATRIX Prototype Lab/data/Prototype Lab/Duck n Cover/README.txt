Duck & Cover (Pygame)

Goal:
- Fly as a flock and drop bombs.
- Avoid windmills (propellers kill ducks).
- Eat insects to gain ammo (+1 per insect).

Controls:
- Mouse: move the flock (lead duck follows mouse; others in formation)
- Left Click or Space: drop bomb (uses 1 ammo)
- Z: zoom in (1x -> 2x -> 3x)
- X: zoom out (3x -> 2x -> 1x)
- C: camera mode toggle (zoom anchored to center vs anchored to lead duck)
- F: fullscreen toggle
- P: pause/unpause (cursor visible when paused)
- Esc: quit

Audio / Assets:
Drop your sound files into these folders (wav/ogg recommended; mp3 depends on SDL_mixer):
- assets/sfx/quack/           (drop-bomb button)
- assets/sfx/explosion/       (bomb explosion)
- assets/sfx/people_hit/      (human hit)
- assets/sfx/building_hit/    (structure destroyed)
- assets/sfx/duck_fly/        (looped wing/flying; first file is looped)
- assets/sfx/insect_eat/      (plays when eating an insect)
- assets/music/               (optional ambience/music; first file loops)

Windmills:
- Spawn at randomized intervals (not constant).
