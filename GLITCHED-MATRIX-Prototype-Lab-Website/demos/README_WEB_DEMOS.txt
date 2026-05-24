Playable Web Demo Notes

The GitHub site currently runs embedded demos through assets/js/demos.js and assets/data/demo_manifest.json.

Playable generated demos:
- Sky and Ground
- Block Busters
- Duck n Cover
- Where's Renaldo
- Mewtants
- DreamCrawler2D
- Helix Biogenics
- Isometric World Machine
- Holo Campaign

HoloVerse is intentionally not embedded in this pass.

The canvas games are generated in JavaScript so GitHub Pages can host them without a Python server. If a true one-file Python/Pygame demo is later converted through pygbag or another static web build tool, place the exported static files under this demos folder and update assets/data/demo_manifest.json to point to the new route.
