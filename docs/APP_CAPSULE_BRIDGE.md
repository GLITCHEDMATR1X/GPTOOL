# GPTOOL App Capsule Bridge

Pass 18 adds a project-specific bridge layer for cleanly infusing Python apps into GX / HoloVerse / HoloCore without merging unrelated apps into one large file.

## Core rule

Do not combine Python apps by pasting them into the same file. Combine them by making each app obey one shared capsule contract.

## Capsule contract

A capsule exposes:

```python
prepare(host)
enter(context)
update(dt)
exit(reason)
cleanup()
get_result()
```

The host owns the window, render loop, camera services, audio services, input services, transitions, and result collection.

## Supported app kinds

```text
panda3d_same_window
panda3d_standalone
pygame_legacy
tkinter_tool
subprocess_app
data_module
legacy_quarantine
```

## Pygame to Panda3D rule

Pygame apps must not be embedded as same-window apps while they own:

```text
pygame.display.set_mode
pygame.event pump
pygame.mixer ownership
while running loop
sys.exit
```

GPTOOL should plan these as migrations:

```text
extract portable logic
preserve original in legacy/
rebuild rendering as Panda3D scene/UI
map input through host.input
route audio through host.audio
update through capsule.update(dt)
```

## Adapter cleanup goal

Adapters should be small translators. They should not become gameplay modules.

Good adapters:

```text
load manifest
instantiate capsule
route enter/update/exit/cleanup
return result
```

Bad adapters:

```text
own window/camera/audio/tasks
contain full gameplay systems
hardcode many paths
remove host tasks
leave UI/render nodes behind
```
