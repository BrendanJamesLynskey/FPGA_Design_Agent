# Portfolio pack

What a portfolio page (for example a project card on the author's landing site) needs to show this project, all taken
from the site itself:

- [`portfolio.json`](portfolio.json): the title, the one-line description, three measured facts (each with its
  `source`, a path into `site/data`), the canonical URL and the media below. `site/tests/test_showcase.py` checks that
  every fact's number is the value at its source.
- `hero_1200x630.png`: a frame of the home page's loop replay (a recorded run travelling the loop), 1200 × 630.
- `hero_square.png`: the hero line, two of the headline facts and the chart of every development run, 1080 × 1080.
- `loop_replay.webm` and `loop_replay.mp4`: the loop replay, silent, under 2 MB, recorded frame by frame from the page.

To regenerate after the site changes (puppeteer is a heavy job: take a heavy slot), build the site, capture the frames
with a puppeteer script that steps the home page's loop player, and encode them with ffmpeg at 4 frames per second
(VP9 for WebM, H.264 for MP4).

Showcase projects add their own cards in the same shape (see [docs/showcase_pages.md](../../docs/showcase_pages.md)).
