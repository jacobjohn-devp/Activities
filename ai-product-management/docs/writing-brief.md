# Writing brief: AI Product Management course, chapters 2–14

## The course
"AI Product Management" is an internal course that takes experienced product managers to AI product management. The readers are already technical: they've shipped complex software, read API docs, and work closely with engineers. They want depth, accuracy and judgement that puts them in the top 1% of AI PMs. Don't explain basic software concepts. Do explain AI concepts precisely, with the trade-offs and the product consequences.

Today is 16 October 2026. Chapter 1 is finished. Read it before you write anything: it's in `../src/index.template.html` (the `LESSONS`, `QUIZ` and `GLOSS` arrays, and the `labHTML` function). Match its depth, tone, structure and HTML conventions exactly.

## Voice
- Plain, direct, specific. Short sentences. Active voice. Write the way a sharp senior PM or staff engineer would talk to a peer.
- British or American spelling is fine, but keep it consistent within a chapter (chapter 1 uses "summarise", "behaviour", so prefer British).
- Never use: asides set off by em-dashes, "not X, but Y" framing, colon-then-reveal sentences, scare quotes around invented labels, stock phrases ("it's worth noting", "in today's fast-paced world", "game-changer", "delve", "landscape" as filler, "unlock", "leverage" as a verb). No emoji.
- Concrete over abstract: worked examples, numbers, real failure cases, decision rules, thresholds.
- Every lesson ends with a "What changes for you" box: 2–4 bullets saying exactly what the PM does differently in specs, reviews, roadmaps or rituals.

## Accuracy rules (important)
- Use web search to check anything perishable: product names, protocol status, regulation dates, pricing patterns, benchmark names, recent research findings. Prefer primary sources (vendor docs, official announcements, standards bodies, the EU's own AI Act pages, peer-reviewed or well-known papers).
- If you can't verify a specific number, model name, date or claim from a reliable source, leave it out or describe it qualitatively. Never invent statistics, quotes, studies or product features.
- Avoid naming specific model versions or exact scores. Lab names (Anthropic, OpenAI, Google) and well-established products and standards (MCP, A2A, SWE-bench, Claude Code, Cursor, GitHub Copilot, OpenAI Codex) are fine when accurate.
- Mark dated statements with "as of October 2026" when they'll age.
- Illustrative numbers must be labelled as illustrative.

## Output format
Write one JSON file per chapter: `chapters/ch<N>.json` (for example `ch2.json`). Validate each with `python3 -I -c "import json,sys; json.load(open(sys.argv[1]))" ch2.json`.

```json
{
  "id": 2,
  "lessons": [
    { "t": "Lesson title (matches the outline, can be tightened)", "shelf": "Durable | Shifting | Shifting fast | Perishable", "html": "<p>…</p>…<div class=\"pm\"><p class=\"eyebrow\">What changes for you</p><ul><li>…</li></ul></div>" }
  ],
  "lab": {
    "title": "Imperative lab title",
    "time": "about 90 minutes",
    "intro": "<p>One or two sentences on what the lab proves.</p>",
    "steps": ["<strong>Short step name.</strong> What to do, precisely, including sizes and thresholds.", "…"],
    "template": "<div class=\"tbl\"><table>…</table></div>  (optional: a worksheet, rubric, or table to fill in)",
    "done": "<p>What good looks like when finished.</p>"
  },
  "quiz": [
    { "q": "A realistic scenario question.", "o": ["option", "option", "option", "option"], "a": 1, "w": "Why the right answer is right, in 1–2 sentences." }
  ],
  "deliverable": { "title": "Name of the work artefact", "html": "<p>…</p><ol><li>…</li></ol><p>…</p>" },
  "reading": [ { "label": "Source name", "url": "https://…" } ]
}
```

### HTML you may use inside strings
Only these (they're already styled): `<p>`, `<strong>`, `<em>`, `<code>`, `<sup>`, `<h3>`, `<ul>`, `<ol>`, `<li>`, `<a href target="_blank" rel="noopener">`, tables as `<div class="tbl"><table><thead><tr><th>…</th></tr></thead><tbody><tr><td>…</td></tr></tbody></table></div>` (first column renders bold), a callout as `<div class="callout"><p class="eyebrow">Short label</p><p>…</p></div>`, and the closing `<div class="pm"><p class="eyebrow">What changes for you</p><ul><li>…</li></ul></div>`, which must be the LAST element of every lesson's html. No inline styles, no classes beyond these, no scripts, no images. Use typographic quotes (’ “ ”) and × − characters directly; JSON handles them.

### Sizes
- Lessons: follow the chapter outline you're given (titles can be tightened). 350–650 words each, at least one table or callout per lesson where it helps.
- Lab: 5–8 steps, practical enough to run at work in one sitting, with a template.
- Quiz: exactly 6 scenario questions, 4 options each, `a` is the zero-based index of the correct option. Vary which index is correct (not always 1). Wrong options must be plausible.
- Deliverable: one page artefact the PM takes back to their team.
- Reading: 3–5 primary or highly reputable sources you actually opened and checked. Real URLs only.

### Cross-references
Refer to other chapters by number and name where useful ("Chapter 5, Evals are the spec"). The full outline is in `../src/index.template.html` in the `CH` array.

When finished, reply with: the files written, a one-line summary per lesson, and any claims you deliberately left out because you couldn't verify them.
