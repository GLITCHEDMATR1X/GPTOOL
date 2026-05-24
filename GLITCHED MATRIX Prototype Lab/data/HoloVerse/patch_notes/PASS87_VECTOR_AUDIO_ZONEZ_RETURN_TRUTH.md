# Pass 87 — Vector Wars source truth, audio ownership, and hub return repair

## Decisions

- Vector Wars `main.py` is a large pygame game. HoloVerse is Panda3D. Launching the real `main.py` inside the Panda3D render graph is not possible without a real port.
- The previous Panda3D native adapter was kept to avoid a child window, but it is a port/approximation and felt like a placeholder compared with the real source.
- Artifact slot 5 now routes to the real Vector Wars `main.py` through the embedded child-window route. On Windows, HoloVerse attempts to parent the child window into the main HoloVerse window.
- HoloVerse root owns music for embedded/external child modes. Child modes keep their event SFX but do not start their own music bed.

## Fixes

- Vector Wars manifest and dimension index now use `embedded_external` for the real source route.
- Vector Wars child source honors `HOLOVERSE_ROOT_OWNS_MUSIC` / `NEON_DOGFIGHT_DISABLE_MUSIC` and does not start pygame mixer music under HoloVerse.
- HoloVerse passes root-music ownership env vars to child modes.
- HoloVerse starts a single root dimension music bed for embedded child modes.
- Native and external returns reload the default HoloVerse shell and reset the player/camera to the safe hub anchor, preventing the floating/unfinished hub return after Zonez.
