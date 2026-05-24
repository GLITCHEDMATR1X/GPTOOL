# Zonez

Zonez is a finite-zone Panda3D sandbox with streaming terrain, themed distant backdrops, replaceable art, and positional audio.

## Folder layout
- `main.py`: launcher
- `sandbox_proto/`: runtime code
- `assets/textures/`: block atlases
- `assets/boundaries/`: replaceable horizon and sky art for each zone
- `assets/sfx/`: replaceable UI, world, and zone sounds
- `zones/`: zone data folders
- `saves/`: local save data

## Included in this version
- surface-first chunk generation with no floating tropical voids
- distant themed boundary backdrops instead of visible wall blocks
- replaceable horizon and sky art per zone through `assets/boundaries/`
- pause menu expanded to include an `Exit` button
- loading title branded as `Zonez`
- root directory cleaned so runtime files are grouped instead of mixed with capture scripts
- dynamic positional SFX remain external and swappable by filename

## Controls
- WASD: move
- Space: ascend
- Left Alt: descend
- Shift: speed boost
- Arrow keys: turn / look
- Mouse: look
- Mouse wheel: zoom
- Tab: next zone
- Z: zone portal
- V: first-person / third-person
- H: help
- F3: debug
- Esc: menu / close overlay

## Run
```bash
pip install -r requirements.txt
python main.py
```

## Replaceable assets
- Horizons: `assets/boundaries/*_horizon.png`
- Sky blends: `assets/boundaries/*_ceiling.png`
- Sounds: `assets/sfx/`


## World size
- Use `[` and `]` or the pause menu buttons to shrink or expand the world.
- Expanding the world moves the outer backdrop farther out and generates more surface chunks so terrain reaches the zone edge.

## Boundary art slots
- Outer walls render as the current zone sky color by default.
- To replace an individual wall with art, put PNG files in `assets/boundaries/` or `assets/boundaries/walls/` with names like `day_zone_north.png`, `day_zone_west.png`, or `tropical_zone_south_east.png`.
- Sky blend images stay replaceable through `assets/boundaries/*_ceiling.png`.
