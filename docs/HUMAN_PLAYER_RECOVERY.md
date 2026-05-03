# Human Player Recovery Workflow

This workflow restores the rigged third-person human player proof lane that was validated during Pass 16 but not committed because generated proof projects and local model assets are intentionally ignored.

## What happened

Pass 16 proved that imported human actors worked:

- broad scan found rigged human candidates in the local backup tree;
- import copied rigged GLB base meshes and FBX animation clips into a generated project;
- screenshot/stress proof ran without a crash log;
- both playable simulation characters reported `actor_loaded=True`.

The loader code stayed in GPTOOL. The generated project and model assets did not stay in Git because `.gitignore` excludes generated proof folders, screenshots, examples, and release archives.

## Recovery command

Run this from the GPTOOL repo on the machine that has the backup/source assets:

```bash
python tools/run_human_player_proof.py --search-root "D:\Apps\BACKUP" --window-type default
```

For headless/offscreen proof:

```bash
python tools/run_human_player_proof.py --search-root "D:\Apps\BACKUP" --window-type offscreen
```

The runner will:

1. generate a clean Panda3D proof project;
2. import real rigged human candidates with `bridge.py import-human-assets`;
3. run `main.py --settings-check`;
4. run built-in screenshot/stress proof;
5. fail if `human_manifest.json` is missing;
6. fail if the proof reports placeholder/procedural fallback instead of imported `Actor` assets;
7. fail if a crash log appears.

## Expected outputs

```text
GeneratedHumanPlayerRecovery/assets/characters/humans/human_manifest.json
GeneratedHumanPlayerRecovery/reports/human_player_import_recovery.json
GeneratedHumanPlayerRecovery/reports/human_player_recovery.json
GeneratedHumanPlayerRecovery/reports/human_player_recovery_result.json
GeneratedHumanPlayerRecovery/screenshots/human_player_recovery.png
```

## Strict proof rule

A panda, box person, or procedural humanoid is not accepted as player proof.

The proof must show:

```json
"actor_loaded": true
```

for each playable simulation character in the proof JSON.

## Useful targeted commands

Prefer male/female survivor candidates:

```bash
python tools/run_human_player_proof.py --search-root "D:\Apps\BACKUP" --prefer female male survivor human character idle cranberry rig
```

Require candidate paths/names to contain a token:

```bash
python tools/run_human_player_proof.py --search-root "D:\Apps\BACKUP" --require survivor
```

Keep an already-generated project and only re-import/re-proof:

```bash
python tools/run_human_player_proof.py --search-root "D:\Apps\BACKUP" --keep-existing
```

## Git policy

Do not commit the recovered model assets unless their license and size are approved. Commit the workflow, sample manifest, and proof runner. Store large proof bundles in Releases or local backups.
