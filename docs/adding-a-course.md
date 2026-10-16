# Adding a course

Every course is a folder in `courses/`. The build turns each one into its own section of the site at `/<slug>/`, with a card on the library home page.

## 1. Start it

```bash
python3 tools/new_course.py claude-code-playbook "Claude Code playbook" --hue orange --shape half
```

This creates `courses/claude-code-playbook/` with a valid `course.json`, a sample `ch1.json`, and `"status": "draft"`. Drafts build and can be previewed at `/<slug>/`, but stay out of the library, the sitemap and `llms.txt`, and are marked `noindex`.

## 2. Fill in course.json

| Field | What it's for |
| --- | --- |
| `title`, `tagline` | Name and one-line description (page titles, search snippets) |
| `summary` | Two sentences for the library card |
| `lede` | Paragraph under the title on the course home |
| `card` | Short label on the course home's title card |
| `hue`, `shape` | The course's colour (`lime`, `sky`, `orange`, `pink`, `yellow`, `blue`) and library card shape (`disc`, `ring`, `pill`, `half`, `stripes`, `discs`) |
| `tags`, `audience`, `level` | Card tags and structured data |
| `updated` | Date of the last real content change (YYYY-MM-DD) |
| `status` | `draft` or `published` |
| `parts` | Groups of chapters: `n` (I, II…), `title`, `hue`, `blurb` |
| `chapters` | One entry per chapter: `id` (1, 2, 3…), `part` (index into `parts`), `slug`, `title`, `sub`, `q` (the core question), `shelf` (shelf life), `shape`, and `lessons` (planned titles) |

A short reference piece can be a course with one part and one or two chapters.

## 3. Write the chapters

One `chN.json` per chapter, following `docs/writing-brief.md`. Only `lessons` is required; `lab`, `quiz`, `deliverable` and `reading` are optional, and the page adapts. Every lesson must end with the "What changes for you" box.

## 4. Build, preview, publish

```bash
python3 build.py --check
python3 build.py
python3 -m http.server 8000 --directory dist
```

Then open `http://localhost:8000/<slug>/`. When it's ready:

1. Set `"status": "published"` in `course.json`.
2. Add the slug to `"order"` in `site.json` to choose where its card sits in the library.
3. Make share images: `python3 tools/make_og.py <slug>` (needs Pillow), and commit the PNGs.
4. Push. CI validates and builds; Cloudflare deploys.

## Course-specific extras

`features` in `course.json` switches on extras built for one course. Today there's one: `vocabulary-lab`, the AI Product Management course's chapter 1 explainers, cost calculator and glossary. New extras go in `src/course.template.html` behind a feature flag so other courses are unaffected.
