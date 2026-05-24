GLITCHED MATRIX Prototype Lab GitHub Site Refresh
=================================================

Use this folder as the replacement GitHub Pages site bundle.

What changed:
- Homepage wording now reflects the latest HoloVerse, MatrixCore, Gleebs, Urban Warzone, Metropolis Robot Selector, and Prototype Lab inventory.
- Patch notes were refreshed at assets/data/combined_patch_notes.txt while preserving the older exported history below the new notes.
- New optimized images were added from the current Prototype Lab build, including at least one Gleebs image.
- The existing layout, navigation, trailer, admin panel, lightbox, Steam link, and page structure were preserved.

Easiest image replacement:
1. Open assets/images/site_current/.
2. Replace an image with a new image using the same filename.
3. Open assets/data/image_manifest.json and change assetVersion to a new value.
4. Upload/commit the site files.

Advanced image replacement:
- Edit assets/data/image_manifest.json and change the image paths.
- You can also open the live editor with ?admin=1 or Ctrl+Shift+A while viewing the page.

Main files:
- index.html
- style.css
- admin.js
- assets/data/combined_patch_notes.txt
- assets/data/image_manifest.json
- assets/images/site_current/


Playable demo gallery
=====================

This refresh adds a Play Demos section to the static GitHub Pages site. The current playable demos are generated browser/canvas slices for Sky and Ground, Block Busters, Duck n Cover, Where's Renaldo, Mewtants, DreamCrawler2D, Helix Biogenics, Isometric World Machine, and Holo Campaign. They do not load sprite, sound, Python runtime, or EXE assets.

To update the demo grid without changing the layout:

1. Edit assets/data/demo_manifest.json.
2. Replace thumbnails in assets/images/site_current/demo_thumbs using the same filenames, or change the thumbnail paths in the manifest.
3. Bump assetVersion in demo_manifest.json so browsers refresh cached thumbnails.

HoloVerse is intentionally not embedded yet. The current demos are lightweight, asset-free teasers for existing simple prototypes only.

Pass 3 GitHub Pages fix notes
-----------------------------
If the Play Demos canvas was showing as a plain black box, replace the site with this pass and wait for GitHub Pages to finish deploying. This build cache-busts the demo JavaScript/CSS, resets the old browser-local image config key, and includes an inline fallback player so the demo panel stays visible even if an external script path is stale during deployment.

The easiest image replacement path is still:
assets/images/site_current/
assets/images/site_current/demo_thumbs/

After replacing images, update assets/data/image_manifest.json or keep the same filenames, then bump the assetVersion value.


PASS 4 PLAYER FIX — 2026-04-29
- Restored the actual <canvas id="demoCanvas"> inside the Play Demos player shell.
- Added script-side canvas creation as a safety net if a cached HTML shell is missing it.
- Bumped CSS/JS/data cache versions to 20260429-pass5-layout-imagefix.
- Bumped the localStorage config key so stale image paths from older deployed passes do not override the new site_current assets.
- Kept the layout, demo manifest workflow, and image replacement folders intact.

PASS 5 — LAYOUT + IMAGE FIX (20260429-pass5-layout-imagefix)
- The Patch Notes sidebar is constrained so it cannot cover the playable demo player or help panels.
- The demo player now uses a two-column contained layout beside the sidebar and only expands to a three-column help/player/help view on very wide screens.
- A new emergency canvas boot shim hides the loading overlay and starts a generated fallback player if the external demo runtime or manifest loads late.
- Site image config uses a fresh storage key and clears older local browser image overrides, so current assets/images/site_current media should load again without stale paths taking over.
- Image cards now show a visible fallback tile instead of an empty/broken media slot if a path is wrong.


Pass 6 — 20260429-pass6-demo-image-patchnotes
- Real screenshot thumbnails added for the simple web-demo gallery.
- Demo card clicks now switch player/runtime/help text reliably.
- Patch notes now force-load newest bundled notes at the top.
- Current image manifest force-loads to repair stale local browser image paths.


Pass 7 — Block Busters Single Demo
-----------------------------------
The Play Demos section now uses one dedicated Block Busters browser demo instead of a multi-game gallery. The web demo uses original Block Busters pixel/block art where available, generated fallbacks where needed, low-volume audio, and a mute button.

Replace header/gallery images through assets/images/site_current and keep filenames unchanged for the safest update path.
