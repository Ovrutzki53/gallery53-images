# gallery53-images

Image pipeline for Gallery 53 (gallery-53.com).

1. A job file is added to `jobs/` (one per product).
2. GitHub Actions downloads the source photos, cuts the object out of its background, places it on a flat palette colour (square, 18% padding) and, when asked, generates styled scenes with Gemini (Nano Banana).
3. Results are committed to `out/<job>/`; approved images are attached to the Shopify product by URL.

Palette tiles: `#EFEBE4` warm parchment · `#D8E3D1` pale sage · `#F2E6D8` peach linen · `#FAFAF8` canvas · `#1A1A1A` deep ink (light objects).

Secret needed for scenes: `GEMINI_API_KEY` (Settings → Secrets and variables → Actions).
