# 237_site: screenshots of the site refresh

This folder holds the screenshots taken for brief 237, the site refresh: the FPGA Force name and logo, the grouped
header navigation, the drawers on long pages, and the new "What changed" page. Each image is a viewport capture
(not a full page) of one built page in `site/public/`, taken with headless Chrome. The captures were made at commit
e3990a5a, before the follow-up commit that changed the site URL, the tagline and the drawer teasers, so those three
details differ slightly from the current pages.

## Records

| Path | What |
|---|---|
| `<page>_<width>_<theme>.png` | one page at 1280 or 390 px wide, in the light or dark theme; 18 top-level pages and one block-design page, 72 images |

## Reproduce

    python site/build.py
    node site/screenshots_237.js

## Known gaps and limits

- Viewport captures only: content below the first screen of each page, including the closed drawers, is not shown.
- Taken before the follow-up commit (site URL, tagline, teasers), so those details are out of date in the images.
- One machine and one Chrome build; other browsers were not captured.
