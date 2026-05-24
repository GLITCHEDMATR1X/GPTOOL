# HoloUtopia Capsule Integration

HoloUtopia is connected to HoloVerse as a GPTOOL app capsule, not as a large fake adapter.

## Role

HoloUtopia is the living-civilization / Sims-like city layer for HoloVerse. The standalone app remains usable for direct testing, while HoloVerse mounts it through a small capsule contract.

## Contract

The capsule entry is:

```text
Dimensions/HoloUtopia/capsule.py
```

It exposes:

```text
prepare(host)
enter(context)
update(dt)
exit(reason)
cleanup()
get_result()
```

The thin HoloVerse adapter is:

```text
Dimensions/HoloUtopia/holoverse_native_adapter.py
```

That adapter only translates HoloVerse native-mode calls into capsule lifecycle calls.

## Ownership rule

HoloVerse owns:

```text
window
render loop
camera service
audio service
input routing
transitions
result collection
```

HoloUtopia owns only:

```text
its scene root
its UI root
its runtime instance
its optional status line
```

## Safety

The capsule keeps authored HoloUtopia data under `Dimensions/HoloUtopia/data/HoloUtopia` and does not touch HoloCore, region runtimes, artifact routing, or GX launcher files.

## Next pass ideas

```text
1. Promote HoloUtopia from optional native dimension to a purpose-driven game route.
2. Add MatrixCore/Gleebs result reactions from HoloUtopia citizen discoveries.
3. Convert more host input/camera behavior into explicit host services.
4. Add first-person entry points from HoloVerse rather than only from standalone controls.
```
