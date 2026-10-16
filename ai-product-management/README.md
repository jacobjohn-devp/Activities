# AI Product Management

A 14-chapter internal course that takes experienced product managers to AI product management. It's a static site built in the Internal Learning design system, with Hoppy the course buddy (off by default; readers switch him on from the header).

## Layout

| Path | What it is |
| --- | --- |
| `chapters/course.json` | The outline: parts, chapter titles, slugs, core questions, shapes and shelf life. |
| `chapters/ch1.json` … `ch14.json` | Chapter content: lessons, lab, quiz, deliverable and reading (chapter 1 also holds the glossary). |
| `src/index.template.html` | The app: styles, chapter 1's explainers and cost lab, Hoppy, the hangar and the router. Content is injected at the `COURSE` placeholder. |
| `static/og/` | 1200×630 share images, one per page, made by `tools/make_og.py`. |
| `site.json` | The site's public address, used for canonical URLs, Open Graph and the sitemap. |
| `docs/writing-brief.md` | Voice, accuracy rules, JSON shape and allowed HTML for chapter content. |
| `build.py` | Validates content and writes `dist/`. Standard library only. |

## What the build produces

| URL | Purpose |
| --- | --- |
| `/` and `/ch/<slug>/` | One real page per chapter, fully prerendered for search engines, with its own title, description, canonical URL, Open Graph and Twitter tags, and JSON-LD (`Course`, `LearningResource`, `BreadcrumbList`). The app takes over in the browser. |
| `/llms.txt` | The [llms.txt](https://llmstxt.org) index of the course for LLMs and AI search. |
| `/llms-full.txt` | Every chapter in one Markdown file. |
| `/index.md`, `/ch/<slug>.md` | Clean Markdown copy of each page. |
| `/sitemap.xml`, `/robots.txt` | Search engine files. The sitemap needs the site address. |
| `/404.html` | Not-found page. |
| `/assets/app.<hash>.css/js` | Shared app code, cached forever (the hash changes when it does). |

## Setting the domain

When the custom domain is attached, put it in `site.json`:

```json
{ "url": "https://learn.example.com" }
```

or set a `SITE_URL` variable in the Cloudflare build settings. Until then, the build skips the sitemap and absolute canonical and Open Graph URLs, and says so in the build log. After the domain is live, add it to Google Search Console and submit `/sitemap.xml`.

## Editing

1. Edit `chapters/chN.json` (or `course.json` for titles and questions). Follow `docs/writing-brief.md`.
2. Check and build:

   ```bash
   python3 build.py --check
   python3 build.py
   ```

3. Preview locally:

   ```bash
   python3 -m http.server 8000 --directory dist
   ```

4. Push or open a pull request. CI validates and builds it; Cloudflare deploys `main`.

If a chapter title, part or shape changes, regenerate the share images (needs Pillow) and commit them:

```bash
python3 tools/make_og.py
```

Perishable chapters (3, 8, 11 and the EU AI Act section of 12) are labelled with their shelf life and should be reviewed each quarter.

## Deployment

Cloudflare (Workers with static assets) builds from this repository:

| Setting | Value |
| --- | --- |
| Production branch | `main` |
| Root directory | `ai-product-management` |
| Build command | `python3 build.py` |
| Deploy command | `npx wrangler deploy` |
| Environment variable (optional) | `SITE_URL` = the public address |

`wrangler.jsonc` uploads `dist/` as static assets, serves `/ch/<slug>/` from its `index.html`, and returns `404.html` for unknown paths. Its `name` must match the Worker's name in the Cloudflare dashboard.

Learner progress, quiz answers, lab ticks, the hangar, the theme and the Hoppy setting are stored in each visitor's own browser (`localStorage`). Nothing is sent to a server.
