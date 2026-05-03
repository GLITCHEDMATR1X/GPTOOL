# GPTOOL human-player-import-recovery local copy

Direct `git clone` to the execution container failed because DNS could not resolve `github.com`.

This folder contains the two recovery-branch files pulled through the GitHub connector:

- `tools/run_human_player_proof.py`
- `docs/HUMAN_PLAYER_RECOVERY.md`

PR: https://github.com/GLITCHEDMATR1X/GPTOOL/pull/5
Branch: `human-player-import-recovery`

To use these, copy the files into a full GPTOOL checkout, then run:

```bash
python tools/run_human_player_proof.py --search-root "D:\Apps\BACKUP" --window-type default
```
