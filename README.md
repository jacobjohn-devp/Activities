# Internal Learning

A library of practical, sourced courses for product teams, published as a static site. The home page lists every course; each course has its own pages, labs, quizzes and progress tracking, built in the Internal Learning design system, with Hoppy the course buddy (off by default).

| Course | Folder | Status |
| --- | --- | --- |
| AI Product Management | [`courses/ai-product-management/`](courses/ai-product-management/) | Published |

**Adding a course:** see [`docs/adding-a-course.md`](docs/adding-a-course.md). **Writing chapters:** see [`docs/writing-brief.md`](docs/writing-brief.md).

## Layout

| Path | What it is |
| --- | --- |
| `courses/<slug>/` | One course: `course.json` (outline and library card), `ch1.json` … (content), `og/` (share images) |
| `src/course.template.html` | The course app shared by every course: styles, router, Hoppy, the hangar, and course-specific extras behind feature flags |
| `build.py` | Validates every course and writes `dist/`. Standard library only |
| `site.json` | Site address, library order, and redirects for old links |
| `tools/new_course.py` | Starts a new course as a draft |
| `tools/make_og.py` | Draws the 1200×630 share images (needs Pillow) |
| `static/` | Site-wide files, such as the library's share image |
| `wrangler.jsonc` | Cloudflare Workers static-assets config |

## What the build produces

| URL | Purpose |
| --- | --- |
| `/` | Library home with a card per published course |
| `/<course>/`, `/<course>/ch/<chapter>/` | Course and chapter pages, prerendered, each with its own title, description, canonical URL, Open Graph and Twitter tags, share image and JSON-LD |
| `/llms.txt`, `/llms-full.txt` | Site-wide [llms.txt](https://llmstxt.org) index and full text |
| `/<course>/llms.txt`, `/<course>/llms-full.txt` | The same for each course |
| `/index.md`, `/<course>/index.md`, `/<course>/ch/<chapter>.md` | Markdown copies of every page |
| `/sitemap.xml`, `/robots.txt`, `/404.html`, `/_headers`, `/_redirects` | Search, error, header and redirect files |

## Build and preview

```bash
python3 build.py --check
python3 build.py
python3 -m http.server 8000 --directory dist
```

`python3 build.py --artifact <slug>` also writes a single-file `artifact-<slug>.html` for publishing a course as a Claude artifact. It isn't deployed.

## Setting the domain

Put the public address in `site.json` (`"url": "https://learn.example.com"`) or set `SITE_URL` in Cloudflare's build variables. Until then the build skips the sitemap and absolute canonical and Open Graph URLs. Once the domain is live, add it to Google Search Console and submit `/sitemap.xml`.

## Deployment

Cloudflare (Workers with static assets) builds from this repository:

| Setting | Value |
| --- | --- |
| Production branch | `main` |
| Root directory | *(repository root, leave empty)* |
| Build command | `python3 build.py` |
| Deploy command | `npx wrangler deploy` |

CI (`.github/workflows/site.yml`) validates and builds every pull request and push to `main`.

Reader progress, quiz answers, lab ticks, the hangar, the theme and the Hoppy setting are stored in each visitor's own browser. Nothing is sent to a server.
