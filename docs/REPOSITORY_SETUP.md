# Repository Setup

This repository is the lean source-control form of GPTOOL / GPT Game Generation Bridge.

Suggested GitHub repository:

```text
GLITCHEDMATR1X/gpt-game-generation-bridge
```

Alternative short name:

```text
GLITCHEDMATR1X/gptool
```

From this folder:

```bash
git status
git remote add origin https://github.com/GLITCHEDMATR1X/gpt-game-generation-bridge.git
git push -u origin main
```

If the remote already exists:

```bash
git remote set-url origin https://github.com/GLITCHEDMATR1X/gpt-game-generation-bridge.git
git push -u origin main
```

Keep source files, docs, profiles, rules, runtime hooks, validator scripts, small sample images, and CI workflow files in the repository.

Do not commit generated proof worlds, local Panda3D runtime binaries, build folders, virtual environments, screenshots, or release zips. Put those in GitHub Releases instead.
