GLITCHED MATRIX Prototype Lab site image swaps
================================================

This folder is the easiest place to replace current GitHub site images without changing the page layout.

Quick method:
1. Keep the same filename.
2. Replace the image file with your new image.
3. Keep the file type the same when possible: .png stays .png, .jpg stays .jpg.
4. In assets/data/image_manifest.json, update assetVersion to a new value such as 20260429b so browsers refresh cached images.

Current slots:
- hero_header.png: wide top hero/header image.
- gallery_01_gleebs.png: Gleebs gallery image.
- gallery_02_holoverse_orb.png: HoloVerse / HoloSpace orb image.
- gallery_03_holo_conquest.jpg: Holo Conquest screenshot.
- gallery_04_anti_heroes.jpg: The Anti-Heroes screenshot.
- gallery_05_afterlife_hotel.jpg: Afterlife Hotel screenshot.
- gallery_06_apocalypse_run.jpg: Apocalypse Run screenshot.
- gallery_07_radar_hell.jpg: Radar Hell screenshot.
- gallery_08_duck_n_cover.jpg: Duck n Cover screenshot.
- gallery_09_holo_campaign.jpg: Holo Campaign contact sheet.
- gallery_10_gleebs_pot.png: compact Gleebs image.

Advanced method:
Edit assets/data/image_manifest.json and point a gallery slot to any image under assets/images/.
The admin panel can also be opened with ?admin=1 or Ctrl+Shift+A while viewing the site.
