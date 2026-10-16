# AI Product Management

A 14-chapter internal course that takes experienced product managers to AI product management. It ships as a single static page, built in the Internal Learning design system, with Hoppy the course buddy.

## Layout

| Path | What it is |
| --- | --- |
| `src/index.template.html` | The page: styles, chapter 1, the explainers, the cost lab, Hoppy, the hangar and the router. Chapters 2–14 are injected at the `CHDATA` placeholder. |
| `chapters/ch2.json` … `ch14.json` | One file per chapter: lessons, lab, quiz, deliverable and reading. |
| `docs/writing-brief.md` | The brief chapters were written to: voice, accuracy rules, JSON shape and allowed HTML. Use it for every edit. |
| `build.py` | Validates the chapters and writes `dist/`. Standard library only. |
| `dist/` | Build output (not committed). |

## Editing a chapter

1. Edit `chapters/chN.json`. Lesson HTML may only use the tags listed in the writing brief, and every lesson must end with the "What changes for you" box.
2. Check and build:

   ```bash
   python3 build.py --check
   python3 build.py
   ```

3. Preview locally:

   ```bash
   python3 -m http.server 8000 --directory dist
   ```

4. Open a pull request. CI validates and builds it, and Cloudflare posts a preview build. Merging to `main` deploys to production.

Perishable chapters (3, 8, 11 and the EU AI Act section of 12) are marked with their shelf life and should be reviewed each quarter.

## Deployment

Cloudflare (Workers with static assets) builds from this repository:

| Setting | Value |
| --- | --- |
| Production branch | `main` |
| Root directory | `ai-product-management` |
| Build command | `python3 build.py` |
| Deploy command | `npx wrangler deploy` |

`wrangler.jsonc` tells Wrangler to upload `dist/` as static assets. Its `name` must match the Worker's name in the Cloudflare dashboard. `build.py` also writes `dist/_headers` with basic security headers.

Learner progress, quiz answers, lab ticks, the hangar and the theme choice are stored in each visitor's own browser (`localStorage`). Nothing is sent to a server.
