# Anti-Heroes GPTOOL Profile

This pass adds a conservative GPTOOL workflow for improving **The Anti-Heroes** from the GX Prototype Lab repository.

The goal is not to replace Anti-Heroes with a generated starter project. The goal is to make GPTOOL act as an AI-facing guardrail before and after Anti-Heroes gameplay passes.

## What this profile protects

Anti-Heroes should remain:

- a third-person Panda3D prototype;
- grounded in the existing GX Prototype Lab game files;
- focused on a readable city sandbox, street traversal, districts, combat, NPCs, contracts, and hero/villain progression;
- validated through the real player-visible route whenever a Panda3D runtime is available.

The profile rejects the wrong direction: generic template replacement, unrelated feature sprawl, untested visual claims, and silent fallback behavior that hides crashes.

## Added files

```text
profiles/antiheroes.json
tools/run_antiheroes_pass.py
docs/ANTI_HEROES_GPTOOL_PROFILE.md
```

## Standard command

From the GPTOOL repo:

```bash
python tools/run_antiheroes_pass.py --gx-root ../GX-Prototype-Lab --runtime auto
```

The helper will:

1. locate The Anti-Heroes inside the GX Prototype Lab checkout;
2. copy the Anti-Heroes profile manifest into that project reports folder;
3. write a profile-aware command text file;
4. generate a GPTOOL work order;
5. run `bridge.py full-pass` against the existing Anti-Heroes folder.

## Safer static-only route

Use this if Panda3D is not available yet:

```bash
python tools/run_antiheroes_pass.py --gx-root ../GX-Prototype-Lab --runtime mock_display --no-smoke
```

This still checks syntax, imports, assets, UI/text heuristics, and command scope. It does not count as visual proof.

## Runtime proof route

Use this when Panda3D or a portable runtime is available:

```bash
python tools/run_antiheroes_pass.py --gx-root ../GX-Prototype-Lab --runtime portable_python --runtime-path runtimes/panda3d_py313 --require-screenshot
```

Expected outputs inside Anti-Heroes:

```text
reports/antiheroes_command.txt
reports/antiheroes_profile_manifest.json
reports/antiheroes_work_order.json
reports/antiheroes_work_order.md
reports/latest_report.json
reports/latest_report.md
reports/antiheroes_scene_proof.json
screenshots/antiheroes_gptool_probe.png
```

## Default improvement direction

The runner's default command is intentionally broad but guarded:

```text
improve The Anti-Heroes as a third-person city sandbox: preserve existing combat/editor/menu systems, make districts and street traversal more readable, add hero-villain stance and service anchors only where safe, and verify with Panda3D proof instead of placeholders
```

Override it when needed:

```bash
python tools/run_antiheroes_pass.py --gx-root ../GX-Prototype-Lab --command "tighten Anti-Heroes ground camera, keep combat intact, and prove the player route with a screenshot"
```

## Anti-Heroes pass order

Recommended order before heavy feature work:

1. **Route proof pass** — prove the real player route launches, screenshots, and writes scene state.
2. **City readability pass** — improve district labels, landmarks, roads, and safe spawn orientation.
3. **Ground traversal pass** — stabilize walking, camera follow, collisions, and flight toggle behavior.
4. **State anchors pass** — add or expose hero/villain stance, district ownership, contracts, vendors, rearm points, and safehouse anchors.
5. **Combat pressure pass** — only after route/city/traversal proof is stable.

## Rule of thumb

GPTOOL should make Anti-Heroes safer to upgrade. It should not flatten the project into another generated demo.
