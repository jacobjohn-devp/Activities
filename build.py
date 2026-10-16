#!/usr/bin/env python3
"""Build the Internal Learning site: a library home page plus every course in courses/.

Each course lives in courses/<slug>/:
  course.json        outline and library card (title, summary, hue, parts, chapters, status)
  ch1.json … chN.json  chapter content (lessons, optional lab, quiz, deliverable, reading)
  og/*.png           share images (tools/make_og.py)

Output in dist/:
  /                         library home, prerendered, with SEO tags
  /<course>/                course home         /<course>/ch/<chapter>/   chapter pages
  /<course>/ch/<chapter>.md, /<course>/index.md   Markdown copies
  /<course>/llms.txt, /<course>/llms-full.txt     per-course LLM files
  /llms.txt, /llms-full.txt, /index.md            site-wide LLM files
  /sitemap.xml, /robots.txt, /404.html, /_headers, /_redirects
  /assets/app.<hash>.css, /assets/<course>.<hash>.js

Courses with "status": "draft" are built (with noindex) but left out of the library,
sitemap and llms.txt. Absolute URLs need the site address: site.json "url" or SITE_URL.

  python3 build.py                 build dist/
  python3 build.py --check         validate content only
  python3 build.py --artifact SLUG also write artifact-SLUG.html (single file, hash routes, for Claude artifacts; not deployed)

Standard library only. Exits non-zero on any content problem so CI can gate on it.
"""
import argparse
import datetime
import glob
import hashlib
import html
import json
import os
import re
import shutil
import sys
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, 'src', 'course.template.html')
COURSES = os.path.join(HERE, 'courses')
DIST = os.path.join(HERE, 'dist')
PLACEHOLDER = 'var COURSE = {} /*COURSE*/;'
LANG = 'en-GB'
SITE_NAME = 'Internal Learning'
SITE_TAGLINE = 'Courses and field notes for product teams, written as we learn.'
HUES = ['lime', 'sky', 'orange', 'pink', 'yellow', 'blue']
SHAPES = ['disc', 'ring', 'pill', 'half', 'stripes', 'discs']
ALLOWED_TAGS = {'p', 'strong', 'em', 'code', 'sup', 'h3', 'ul', 'ol', 'li', 'a', 'div', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'br'}
BALANCED = ['p', 'ul', 'ol', 'li', 'div', 'table', 'strong', 'em']
FAVICON = ("data:image/svg+xml," + "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E"
           "%3Crect width='64' height='64' fill='%23ebebeb'/%3E%3Ccircle cx='40' cy='22' r='22' fill='%239bcb1a'/%3E"
           "%3Crect x='6' y='30' width='34' height='28' fill='%23111111'/%3E%3C/svg%3E")


def esc(s):
    return html.escape(str(s), quote=True)


def plain(fragment, limit=None):
    text = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', fragment or ''))).strip()
    if limit and len(text) > limit:
        text = text[:limit - 1].rsplit(' ', 1)[0] + '…'
    return text


# ---------------------------------------------------------------- content

def check_html(label, text, problems):
    tags = set(re.findall(r'</?([a-z0-9]+)', text)) - ALLOWED_TAGS
    if tags:
        problems.append(f'{label}: tags not allowed {sorted(tags)}')
    for t in BALANCED:
        opened = len(re.findall(r'<%s[ >]' % t, text))
        closed = text.count('</%s>' % t)
        if opened != closed:
            problems.append(f'{label}: <{t}> opened {opened}, closed {closed}')
    if re.search(r'<script|\son\w+=|javascript:', text, re.I):
        problems.append(f'{label}: scripts or event handlers are not allowed')


def load_course(folder):
    problems = []
    slug = os.path.basename(folder)
    try:
        course = json.load(open(os.path.join(folder, 'course.json'), encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as e:
        return None, {}, [f'{slug}/course.json: {e}']
    p = lambda m: problems.append(f'{slug}/course.json: {m}')
    if course.get('slug') != slug:
        p(f'"slug" must be "{slug}" (the folder name)')
    for key in ('title', 'tagline', 'summary', 'parts', 'chapters'):
        if not course.get(key):
            p(f'missing "{key}"')
    if course.get('hue') not in HUES:
        p(f'"hue" must be one of {HUES}')
    if course.get('status', 'published') not in ('published', 'draft'):
        p('"status" must be "published" or "draft"')
    chapters = course.get('chapters', [])
    ids = [c.get('id') for c in chapters]
    if ids != list(range(1, len(ids) + 1)):
        p('chapter ids must run 1, 2, 3 … in order')
    slugs = [c.get('slug', '') for c in chapters]
    if len(set(slugs)) != len(slugs) or any(not re.fullmatch(r'[a-z0-9-]+', s) for s in slugs):
        p('chapter slugs must be unique lowercase-with-hyphens')
    for c in chapters:
        for key in ('title', 'sub', 'q', 'shelf', 'shape'):
            if not c.get(key):
                p(f'chapter {c.get("id")}: missing "{key}"')
        if not 0 <= c.get('part', -1) < len(course.get('parts', [])):
            p(f'chapter {c.get("id")}: "part" must index into "parts"')
        if c.get('shape') not in SHAPES:
            p(f'chapter {c.get("id")}: "shape" must be one of {SHAPES}')
    for part in course.get('parts', []):
        if part.get('hue') not in HUES:
            p(f'part {part.get("n")}: "hue" must be one of {HUES}')
    special = 'vocabulary-lab' in course.get('features', [])
    data = {}
    for path in sorted(glob.glob(os.path.join(folder, 'ch*.json'))):
        name = f'{slug}/{os.path.basename(path)}'
        try:
            d = json.load(open(path, encoding='utf-8'))
        except json.JSONDecodeError as e:
            problems.append(f'{name}: invalid JSON ({e})')
            continue
        cid = d.get('id')
        if cid not in ids or os.path.basename(path) != f'ch{cid}.json':
            problems.append(f'{name}: "id" must match the file name and course.json')
            continue
        if not d.get('lessons'):
            problems.append(f'{name}: needs at least one lesson')
        if cid == 1 and special and 'glossary' not in d:
            problems.append(f'{name}: the vocabulary-lab feature needs a "glossary"')
        for i, lesson in enumerate(d.get('lessons', []), 1):
            text = lesson.get('html', '')
            if not lesson.get('t'):
                problems.append(f'{name} lesson {i}: missing title "t"')
            if '<div class="pm">' not in text or not text.rstrip().endswith('</ul></div>'):
                problems.append(f'{name} lesson {i}: must end with the "What changes for you" box')
            check_html(f'{name} lesson {i}', text, problems)
        lab = d.get('lab')
        if lab is not None:
            if not lab.get('steps') or not lab.get('title'):
                problems.append(f'{name}: a lab needs "title" and "steps"')
            for part in [lab.get('intro', ''), lab.get('template', ''), lab.get('done', '')] + list(lab.get('steps', [])):
                check_html(f'{name} lab', part, problems)
        if d.get('deliverable'):
            check_html(f'{name} deliverable', d['deliverable'].get('html', ''), problems)
        for j, q in enumerate(d.get('quiz', []), 1):
            if not (isinstance(q.get('a'), int) and 0 <= q['a'] < len(q.get('o', []))):
                problems.append(f'{name} quiz {j}: answer index out of range')
        data[cid] = d
    missing = [i for i in ids if i not in data]
    if missing:
        problems.append(f'{slug}: no content file for chapter(s) {missing}')
    return course, data, problems


# ---------------------------------------------------------------- HTML → Markdown

class _Node:
    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.parent, self.kids = tag, dict(attrs), parent, []


class _Tree(HTMLParser):
    VOID = {'br'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = self.cur = _Node('root', [], None)

    def handle_starttag(self, tag, attrs):
        n = _Node(tag, attrs, self.cur)
        self.cur.kids.append(n)
        if tag not in self.VOID:
            self.cur = n

    def handle_endtag(self, tag):
        n = self.cur
        while n is not self.root and n.tag != tag:
            n = n.parent
        if n is not self.root:
            self.cur = n.parent

    def handle_data(self, data):
        self.cur.kids.append(data)


def _inline(n):
    if isinstance(n, str):
        return re.sub(r'\s+', ' ', n)
    inner = ''.join(_inline(k) for k in n.kids)
    t = n.tag
    if t == 'strong':
        return f'**{inner.strip()}**' if inner.strip() else ''
    if t == 'em':
        return f'*{inner.strip()}*' if inner.strip() else ''
    if t == 'code':
        return f'`{inner}`'
    if t == 'sup':
        return f'^{inner}'
    if t == 'br':
        return '\n'
    if t == 'a':
        return f'[{inner.strip()}]({n.attrs.get("href", "")})'
    return inner


def _find(n, tag):
    found = []
    for k in n.kids:
        if not isinstance(k, str):
            if k.tag == tag:
                found.append(k)
            found.extend(_find(k, tag))
    return found


def _blocks(n, out, depth=0):
    for k in n.kids:
        if isinstance(k, str):
            if k.strip():
                out.append(re.sub(r'\s+', ' ', k).strip())
            continue
        cls = k.attrs.get('class', '')
        if k.tag == 'p':
            text = _inline(k).strip()
            if text:
                out.append(f'**{text}**' if 'eyebrow' in cls else text)
        elif k.tag == 'h3':
            out.append('### ' + _inline(k).strip())
        elif k.tag in ('ul', 'ol'):
            lines = []
            for i, li in enumerate([x for x in k.kids if not isinstance(x, str) and x.tag == 'li'], 1):
                nested = [x for x in li.kids if not isinstance(x, str) and x.tag in ('ul', 'ol')]
                text = ''.join(_inline(x) for x in li.kids if x not in nested).strip()
                lines.append('  ' * depth + (f'{i}. ' if k.tag == 'ol' else '- ') + text)
                for sub in nested:
                    wrapper = _Node('root', [], None)
                    wrapper.kids = [sub]
                    tmp = []
                    _blocks(wrapper, tmp, depth + 1)
                    lines.extend(tmp)
            out.append('\n'.join(lines))
        elif k.tag == 'table':
            rows = [[_inline(c).strip().replace('|', '\\|') for c in tr.kids if not isinstance(c, str) and c.tag in ('th', 'td')] for tr in _find(k, 'tr')]
            if rows:
                width = max(len(r) for r in rows)
                rows = [r + [''] * (width - len(r)) for r in rows]
                out.append('\n'.join(['| ' + ' | '.join(rows[0]) + ' |', '|' + ' --- |' * width] + ['| ' + ' | '.join(r) + ' |' for r in rows[1:]]))
        elif k.tag == 'div' and ('callout' in cls or 'pm' in cls):
            tmp = []
            _blocks(k, tmp, depth)
            out.append('\n>\n'.join('> ' + b.replace('\n', '\n> ') for b in tmp))
        else:
            _blocks(k, out, depth)


def to_markdown(fragment):
    tree = _Tree()
    tree.feed(fragment or '')
    out = []
    _blocks(tree.root, out)
    return '\n\n'.join(b for b in out if b.strip())


# ---------------------------------------------------------------- shared head + card art

def shape_svg(kind):
    if kind == 'ring':
        k = '<circle class="shape-ring" cx="210" cy="90" r="78"/>'
    elif kind == 'pill':
        k = '<rect class="shape" x="150" y="-40" width="120" height="280" rx="60"/>'
    elif kind == 'half':
        k = '<path class="shape" d="M150 0 A140 140 0 0 1 290 140 L290 200 L150 200 Z"/>'
    elif kind == 'stripes':
        k = ''.join(f'<rect class="shape" x="0" y="{y}" width="320" height="{h}"/>' for y, h in ((36, 8), (60, 12), (88, 20), (124, 32), (172, 40)))
    elif kind == 'discs':
        k = ''.join(f'<circle class="shape mult" cx="230" cy="{y}" r="64"/>' for y in (20, 110, 200))
    else:
        k = '<circle class="shape" cx="210" cy="50" r="120"/>'
    return f'<svg viewBox="0 0 320 200" preserveAspectRatio="xMidYMid slice" aria-hidden="true">{k}</svg>'


def head_tags(url, title, description, path, image, md_path, jsonld, css_href, fonts_link, kind='website', index=True):
    canonical = url + path if url else path
    tags = [
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">',
        f'<title>{esc(title)}</title>',
        f'<meta name="description" content="{esc(description)}">',
        f'<meta name="robots" content="{"index, follow, max-image-preview:large" if index else "noindex"}">',
        '<meta name="theme-color" content="#ebebeb" media="(prefers-color-scheme: light)">',
        '<meta name="theme-color" content="#17181a" media="(prefers-color-scheme: dark)">',
        f'<link rel="icon" href="{FAVICON}">',
        f'<link rel="alternate" type="text/markdown" href="{md_path}" title="Markdown version">',
        f'<meta property="og:type" content="{kind}">',
        f'<meta property="og:site_name" content="{esc(SITE_NAME)}">',
        f'<meta property="og:title" content="{esc(title)}">',
        f'<meta property="og:description" content="{esc(description)}">',
        f'<meta property="og:locale" content="{LANG.replace("-", "_")}">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{esc(title)}">',
        f'<meta name="twitter:description" content="{esc(description)}">',
    ]
    if url:
        tags += [f'<link rel="canonical" href="{canonical}">', f'<meta property="og:url" content="{canonical}">',
                 f'<meta property="og:image" content="{url}{image}">', '<meta property="og:image:width" content="1200">',
                 '<meta property="og:image:height" content="630">', f'<meta property="og:image:alt" content="{esc(title)}">',
                 f'<meta name="twitter:image" content="{url}{image}">']
    tags += ['<link rel="preconnect" href="https://fonts.googleapis.com">', '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
             fonts_link, f'<link rel="stylesheet" href="{css_href}">',
             '<style>body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>']
    for block in jsonld:
        tags.append('<script type="application/ld+json">' + json.dumps(block, ensure_ascii=False).replace('</', '<\\/') + '</script>')
    return '\n'.join(tags)


# ---------------------------------------------------------------- one course

class Course:
    def __init__(self, course, data, url, today):
        self.c, self.data, self.url, self.today = course, data, url, today
        self.slug, self.chapters = course['slug'], course['chapters']
        self.base = f'/{self.slug}/'
        self.published = course.get('status', 'published') == 'published'

    def path(self, ch=None):
        return self.base if ch is None else f'{self.base}ch/{ch["slug"]}/'

    def abs(self, path):
        return self.url + path if self.url else path

    def lessons(self):
        return sum(len(self.data[ch['id']]['lessons']) for ch in self.chapters)

    def minutes(self, ch):
        d = self.data[ch['id']]
        words = sum(len(plain(l['html']).split()) for l in d['lessons'])
        return max(20, round(words / 220 + (60 if d.get('lab') else 0) + (15 if d.get('quiz') else 0)))

    def total_hours(self):
        return max(1, round(sum(self.minutes(ch) for ch in self.chapters) / 60))

    def part(self, ch):
        return self.c['parts'][ch['part']]

    # prerendered bodies
    def prerender_home(self):
        h = [f'<div class="prerender"><nav aria-label="Breadcrumb" class="eyebrow"><a href="/">{esc(SITE_NAME)}</a> · Course</nav><h1>{esc(self.c["title"])}</h1>',
             f'<p class="lede">{esc(self.c.get("lede") or self.c["tagline"])}</p>']
        for i, p in enumerate(self.c['parts']):
            h.append(f'<section id="part-{i + 1}"><h2>Part {esc(p["n"])} · {esc(p["title"])}</h2><p>{esc(p.get("blurb", ""))}</p><ol>')
            for ch in self.chapters:
                if ch['part'] == i:
                    h.append(f'<li value="{ch["id"]}"><a href="{self.path(ch)}">{esc(ch["title"])}</a>: {esc(ch["q"])}</li>')
            h.append('</ol></section>')
        return ''.join(h) + '</div>'

    def prerender_chapter(self, ch):
        d, p = self.data[ch['id']], self.part(ch)
        h = [f'<div class="prerender"><nav aria-label="Breadcrumb" class="eyebrow"><a href="/">{esc(SITE_NAME)}</a> · <a href="{self.base}">{esc(self.c["title"])}</a> · Part {esc(p["n"])}</nav>',
             f'<h1>{esc(ch["title"])}</h1><p class="lede">{esc(ch["q"])}</p>']
        for i, l in enumerate(d['lessons'], 1):
            h.append(f'<section id="l{i}"><h2>Lesson {ch["id"]}.{i} · {esc(l["t"])}</h2>{l["html"]}</section>')
        if d.get('glossary'):
            h.append('<section id="glossary"><h2>Glossary</h2><dl>' + ''.join(f'<dt>{esc(g["term"])}</dt><dd>{esc(g["def"])}</dd>' for g in d['glossary']) + '</dl></section>')
        lab = d.get('lab')
        if lab:
            h.append(f'<section id="lab"><h2>Lab: {esc(lab["title"])}</h2>{lab.get("intro", "")}<ol>' + ''.join(f'<li>{s}</li>' for s in lab['steps']) + '</ol>' + lab.get('template', '') + lab.get('done', '') + '</section>')
        elif ch['id'] == 1 and 'vocabulary-lab' in self.c.get('features', []):
            h.append('<section id="lab"><h2>Lab: model the cost of an AI feature</h2><p>An interactive calculator for cost per request, per user and per month, split by uncached input, cached input, output and thinking tokens.</p></section>')
        if d.get('quiz'):
            h.append('<section id="quiz"><h2>Check yourself</h2><ol>' + ''.join(f'<li>{esc(q["q"])}<ul>' + ''.join(f'<li>{esc(o)}</li>' for o in q['o']) + '</ul></li>' for q in d['quiz']) + '</ol></section>')
        if d.get('deliverable'):
            h.append(f'<section id="deliverable"><h2>Deliverable: {esc(d["deliverable"]["title"])}</h2>{d["deliverable"]["html"]}</section>')
        if d.get('reading'):
            h.append('<section><h2>Further reading</h2><ul>' + ''.join(f'<li><a href="{esc(r["url"])}" rel="noopener">{esc(r["label"])}</a></li>' for r in d['reading']) + '</ul></section>')
        i, nav = ch['id'] - 1, []
        if i > 0:
            nav.append(f'<a href="{self.path(self.chapters[i - 1])}">Previous: {esc(self.chapters[i - 1]["title"])}</a>')
        if i < len(self.chapters) - 1:
            nav.append(f'<a href="{self.path(self.chapters[i + 1])}">Next: {esc(self.chapters[i + 1]["title"])}</a>')
        return ''.join(h) + '<nav class="pager" aria-label="Chapters">' + ''.join(nav) + '</nav></div>'

    # structured data
    def provider(self):
        return {'@type': 'Organization', 'name': SITE_NAME, 'url': self.abs('/')}

    def course_ld(self):
        return [{
            '@context': 'https://schema.org', '@type': 'Course', 'name': self.c['title'], 'description': self.c['tagline'],
            'url': self.abs(self.base), 'image': self.abs(f'{self.base}og/home.png'), 'inLanguage': LANG, 'isAccessibleForFree': True,
            'educationalLevel': self.c.get('level', ''), 'audience': {'@type': 'Audience', 'audienceType': self.c.get('audience', '')},
            'provider': self.provider(), 'keywords': ', '.join(self.c.get('tags', [])), 'teaches': [ch['title'] for ch in self.chapters],
            'dateModified': self.c.get('updated', self.today),
            'hasPart': [{'@type': 'LearningResource', 'position': ch['id'], 'name': ch['title'], 'url': self.abs(self.path(ch))} for ch in self.chapters],
        }, self.crumbs([(self.c['title'], self.base)])]

    def chapter_ld(self, ch):
        return [{
            '@context': 'https://schema.org', '@type': 'LearningResource', 'name': ch['title'], 'description': ch['q'],
            'url': self.abs(self.path(ch)), 'image': self.abs(f'{self.base}og/{ch["slug"]}.png'), 'inLanguage': LANG,
            'isAccessibleForFree': True, 'learningResourceType': 'Course chapter', 'educationalLevel': self.c.get('level', ''),
            'timeRequired': f'PT{self.minutes(ch)}M', 'position': ch['id'], 'dateModified': self.c.get('updated', self.today),
            'teaches': [l['t'] for l in self.data[ch['id']]['lessons']],
            'isPartOf': {'@type': 'Course', 'name': self.c['title'], 'url': self.abs(self.base)},
        }, self.crumbs([(self.c['title'], self.base), (ch['title'], self.path(ch))])]

    def crumbs(self, trail):
        items = [(SITE_NAME, '/')] + trail
        return {'@context': 'https://schema.org', '@type': 'BreadcrumbList',
                'itemListElement': [{'@type': 'ListItem', 'position': i + 1, 'name': n, 'item': self.abs(u)} for i, (n, u) in enumerate(items)]}

    # markdown + llms
    def chapter_md(self, ch):
        d, p = self.data[ch['id']], self.part(ch)
        out = [f'# {self.c["title"]}, chapter {ch["id"]}: {ch["title"]}', f'> {ch["q"]}',
               f'Part {p["n"]}, {p["title"]}. Shelf life: {ch["shelf"]}. Web version: {self.abs(self.path(ch))}']
        for i, l in enumerate(d['lessons'], 1):
            out.append(f'## Lesson {ch["id"]}.{i}: {l["t"]}\n\nShelf life: {l.get("shelf", "")}\n\n{to_markdown(l["html"])}')
        if d.get('glossary'):
            out.append('## Glossary\n\n' + '\n'.join(f'- **{g["term"]}** ({g.get("area", "")}): {g["def"]}' for g in d['glossary']))
        lab = d.get('lab')
        if lab:
            steps = '\n'.join(f'{i}. {to_markdown(s)}' for i, s in enumerate(lab['steps'], 1))
            out.append(f'## Lab: {lab["title"]} ({lab.get("time", "")})\n\n{to_markdown(lab.get("intro", ""))}\n\n{steps}\n\n{to_markdown(lab.get("template", ""))}\n\n{to_markdown(lab.get("done", ""))}'.strip())
        if d.get('quiz'):
            out.append('## Check yourself\n\n' + '\n'.join(
                f'{i}. {q["q"]}\n' + '\n'.join(f'   - {o}' for o in q['o']) + f'\n   - Answer: {q["o"][q["a"]]}. {q["w"]}' for i, q in enumerate(d['quiz'], 1)))
        if d.get('deliverable'):
            out.append(f'## Deliverable: {d["deliverable"]["title"]}\n\n{to_markdown(d["deliverable"]["html"])}')
        if d.get('reading'):
            out.append('## Further reading\n\n' + '\n'.join(f'- [{r["label"]}]({r["url"]})' for r in d['reading']))
        return '\n\n'.join(out) + '\n'

    def home_md(self):
        out = [f'# {self.c["title"]}', f'> {self.c["tagline"]}', self.c.get('lede', '')]
        for i, p in enumerate(self.c['parts']):
            out.append(f'## Part {p["n"]}: {p["title"]}\n\n{p.get("blurb", "")}\n\n' + '\n'.join(
                f'{ch["id"]}. [{ch["title"]}]({self.abs(self.base + "ch/" + ch["slug"] + ".md")}): {ch["q"]}' for ch in self.chapters if ch['part'] == i))
        return '\n\n'.join(o for o in out if o) + '\n'

    def llms_txt(self):
        lines = [f'# {self.c["title"]}', '', f'> {self.c["tagline"]} {self.c.get("summary", "")}', '',
                 f'Part of {SITE_NAME} ({self.abs("/llms.txt")}). Audience: {self.c.get("audience", "")}. Last updated {self.c.get("updated", self.today)}. Each chapter is available as Markdown below.', '']
        for i, p in enumerate(self.c['parts']):
            lines += [f'## Part {p["n"]}: {p["title"]}', '']
            lines += [f'- [{ch["id"]}. {ch["title"]}]({self.abs(self.base + "ch/" + ch["slug"] + ".md")}): {ch["q"]}' for ch in self.chapters if ch['part'] == i]
            lines.append('')
        lines += ['## Optional', '', f'- [Full course text]({self.abs(self.base + "llms-full.txt")}): every chapter in one file',
                  f'- [Course home]({self.abs(self.base)}): the interactive web version', '']
        return '\n'.join(lines)

    def full_md(self):
        return self.home_md() + '\n\n' + '\n\n'.join(self.chapter_md(ch) for ch in self.chapters)


# ---------------------------------------------------------------- library home

def library_card(co):
    c = co.c
    chapters, lessons, hours = len(co.chapters), co.lessons(), co.total_hours()
    upd = datetime.date.fromisoformat(c['updated']).strftime('%B %Y') if c.get('updated') else ''
    tags = ''.join(f'<span class="tag line">{esc(t)}</span>' for t in c.get('tags', []))
    return (f'<a class="course lib-card hue-{c["hue"]}" href="{co.base}" data-store="{esc(c.get("storageKey") or "il-progress-" + co.slug)}" data-total="{lessons}">'
            f'<div class="heroimg">{shape_svg(c.get("shape", "disc"))}'
            f'<div class="tcard"><span class="tnum">Course</span><span class="tmark">Learning</span><div class="tname">{esc(c["title"])}</div>'
            f'<div class="tsub">{chapters} chapters · {lessons} lessons</div></div></div>'
            f'<p class="q">{esc(c["summary"])}</p>'
            f'<div class="meta"><span class="tag hue">{esc(c.get("level", "Course"))}</span><span>About {hours} hours</span>{f"<span>Updated {upd}</span>" if upd else ""}</div>'
            f'<div class="meta">{tags}</div><div class="lib-progress" hidden></div></a>')


LIBRARY_SCRIPT = r"""
(function () {
  /* Theme toggle, shared with the courses */
  var THEMES = ['system', 'light', 'dark'], theme = 'system';
  try { theme = localStorage.getItem('il-theme') || 'system'; } catch (e) {}
  var btn = document.getElementById('theme-btn');
  function apply() {
    if (theme === 'system') document.documentElement.removeAttribute('data-theme'); else document.documentElement.setAttribute('data-theme', theme);
    if (btn) btn.textContent = 'Theme: ' + theme;
  }
  if (btn) btn.addEventListener('click', function () { theme = THEMES[(THEMES.indexOf(theme) + 1) % 3]; try { localStorage.setItem('il-theme', theme); } catch (e) {} apply(); });
  apply();
  /* Show each reader's own progress on the course cards (stored in their browser only) */
  document.querySelectorAll('.lib-card').forEach(function (card) {
    var done = {}; try { done = JSON.parse(localStorage.getItem(card.dataset.store) || '{}') || {}; } catch (e) {}
    var n = Object.keys(done).filter(function (k) { return /^\d+\.\d+$/.test(k); }).length, total = +card.dataset.total;
    if (!n) return;
    var pct = Math.min(100, Math.round(100 * n / total)), el = card.querySelector('.lib-progress');
    el.innerHTML = '<div class="progress"><div class="head"><span>' + n + ' of ' + total + ' lessons</span><span>' + pct + '%</span></div><div class="track" role="progressbar" aria-valuenow="' + pct + '" aria-valuemin="0" aria-valuemax="100" aria-label="Your progress"><div class="fill" style="width:' + pct + '%"></div></div></div>';
    el.hidden = false;
  });
})();
"""


def library_page(courses, url, css_href, fonts, today):
    pub = [co for co in courses if co.published]
    n_ch = sum(len(co.chapters) for co in pub)
    n_ls = sum(co.lessons() for co in pub)
    cards = ''.join(library_card(co) for co in pub)
    body = f'''<div class="wrap">
  <header class="bar">
    <a class="mark" href="/">Internal Learning</a>
    <nav aria-label="Site"><a href="#courses">Courses</a><button type="button" class="theme-btn" id="theme-btn">Theme: system</button></nav>
  </header>
  <main>
    <section class="hero hue-lime lib-hero">
      <div><p class="eyebrow">Internal Learning · library</p><h1>Learn it once. Keep it.</h1>
        <p class="lede">{esc(SITE_TAGLINE)} Each course is practical, sourced and dated, written for people who already ship and want the next level of depth.</p>
        <div class="facts"><span class="tag">{len(pub)} course{"" if len(pub) == 1 else "s"}</span><span class="tag">{n_ch} chapters</span><span class="tag line">{n_ls} lessons</span></div>
        <div class="facts"><a class="btn" href="{pub[0].base if pub else "#courses"}">Start with {esc(pub[0].c["title"]) if pub else "a course"}</a><a class="btn secondary" href="#courses">Browse courses</a></div>
      </div>
      <div class="hero-art" aria-hidden="true"><svg viewBox="0 0 520 340" preserveAspectRatio="xMidYMid slice">
        <rect x="300" y="-40" width="170" height="300" rx="85" style="fill:var(--sky)"/><circle cx="210" cy="250" r="120" style="fill:var(--lime)"/>
        <circle cx="470" cy="300" r="50" style="fill:none;stroke:var(--orange);stroke-width:22px"/><circle cx="120" cy="60" r="34" style="fill:var(--pink)"/></svg>
        <div class="tcard"><span class="tmark">Learning</span><div class="tname">The library</div><div class="tsub">Updated as we learn</div></div></div>
    </section>
    <section class="part" id="courses"><div class="part-head"><span class="tag">Courses</span><h2>Start anywhere</h2><p>Every course stands on its own. Your progress is saved in this browser.</p></div>
      <div class="grid">{cards}</div></section>
  </main>
</div>'''
    ld = [{'@context': 'https://schema.org', '@type': 'WebSite', 'name': SITE_NAME, 'description': SITE_TAGLINE, 'url': (url or '') + '/', 'inLanguage': LANG},
          {'@context': 'https://schema.org', '@type': 'ItemList', 'name': f'{SITE_NAME} courses',
           'itemListElement': [{'@type': 'ListItem', 'position': i + 1, 'url': co.abs(co.base), 'name': co.c['title']} for i, co in enumerate(pub)]}]
    head = head_tags(url, f'{SITE_NAME} · Courses for product teams', plain(SITE_TAGLINE + ' ' + ' '.join(co.c['title'] for co in pub), 160),
                     '/', '/og/library.png', '/index.md', ld, css_href, fonts)
    return f'<!doctype html>\n<html lang="{LANG}">\n<head>\n{head}\n</head>\n<body>\n{body}\n<script>{LIBRARY_SCRIPT}</script>\n</body>\n</html>\n'


# ---------------------------------------------------------------- build

def split_template(src):
    style = re.search(r'<style>([\s\S]*?)</style>', src).group(1)
    fonts = re.search(r'<link rel="stylesheet" href="https://fonts\.googleapis\.com[^>]+>', src).group(0)
    body = src[src.index('<div class="wrap">'):src.index('<script>')]
    script = re.search(r'<script>([\s\S]*?)</script>', src).group(1)
    return style, fonts, body, script


def asset(name, ext, content):
    rel = f'/assets/{name}.{hashlib.sha256(content.encode("utf-8")).hexdigest()[:10]}.{ext}'
    write(rel, content)
    return rel


def write(rel, content):
    path = os.path.join(DIST, rel.lstrip('/'))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def inject(src, course, data):
    payload = json.dumps(dict(course, data=data), ensure_ascii=False).replace('</', '<\\/')
    return src.replace(PLACEHOLDER, 'var COURSE = ' + payload + ';', 1).replace('<title>AI Product Management</title>', f'<title>{esc(course["title"])}</title>', 1)


def main():
    ap = argparse.ArgumentParser(description='Build the Internal Learning site.')
    ap.add_argument('--check', action='store_true', help='validate content only')
    ap.add_argument('--artifact', metavar='SLUG', help='also write artifact-SLUG.html for a Claude artifact (not deployed)')
    args = ap.parse_args()

    loaded, problems = [], []
    for folder in sorted(glob.glob(os.path.join(COURSES, '*'))):
        if os.path.isdir(folder):
            course, data, probs = load_course(folder)
            problems += probs
            if course:
                loaded.append((course, data))
    print('courses loaded: ' + ', '.join(f'{c["slug"]} ({len(d)} chapters)' for c, d in loaded))
    if not loaded:
        problems.append('no courses found in courses/')
    if problems:
        print('\n'.join('  ✗ ' + p for p in problems))
        sys.exit(f'build failed: {len(problems)} problem(s)')
    if args.check:
        print('check passed')
        return

    cfg_path = os.path.join(HERE, 'site.json')
    cfg = json.load(open(cfg_path)) if os.path.exists(cfg_path) else {}
    url = (os.environ.get('SITE_URL') or cfg.get('url') or '').rstrip('/')
    today = datetime.date.today().isoformat()
    courses = [Course(c, d, url, today) for c, d in loaded]
    order = {s: i for i, s in enumerate(cfg.get('order', []))}
    courses.sort(key=lambda co: (order.get(co.slug, 999), co.c['title']))

    src = open(TEMPLATE, encoding='utf-8').read()
    if PLACEHOLDER not in src:
        sys.exit('build: COURSE placeholder missing from src/course.template.html')
    if os.path.isdir(DIST):
        shutil.rmtree(DIST)
    os.makedirs(DIST)

    style, fonts, body, _ = split_template(src)
    css_href = asset('app', 'css', style)
    if os.path.isdir(os.path.join(HERE, 'static')):
        shutil.copytree(os.path.join(HERE, 'static'), DIST, dirs_exist_ok=True)

    for co in courses:
        full = inject(src, co.c, co.data)
        js_href = asset(co.slug, 'js', split_template(full)[3])
        og = os.path.join(COURSES, co.slug, 'og')
        if os.path.isdir(og):
            shutil.copytree(og, os.path.join(DIST, co.slug, 'og'))
        ch1 = co.chapters[0]

        def page(kind, title, description, path, image, md_path, jsonld, prerender, co=co, js_href=js_href, ch1=ch1):
            b = body.replace('<main id="app"></main>', f'<main id="app">{prerender}</main>', 1)
            b = b.replace('href="#home"', f'href="{co.base}"').replace('href="#ch1"', f'href="{co.path(ch1)}"')
            b = b.replace('Learning · AI Product Management</a>', f'Learning · {esc(co.c["title"])}</a>', 1)
            return (f'<!doctype html>\n<html lang="{LANG}">\n<head>\n' + head_tags(url, title, description, path, image, md_path, jsonld, css_href, fonts, kind, co.published)
                    + f'\n</head>\n<body>\n{b}<script>window.__SITE = true;</script>\n<script src="{js_href}"></script>\n</body>\n</html>\n')

        write(co.base + 'index.html', page('website', f'{co.c["title"]} · {SITE_NAME}', plain(co.c['tagline'] + ' ' + co.c.get('summary', ''), 160),
                                           co.base, f'{co.base}og/home.png', f'{co.base}index.md', co.course_ld(), co.prerender_home()))
        for ch in co.chapters:
            write(co.path(ch) + 'index.html', page('article', f'{ch["title"]} · {co.c["title"]}', plain(ch['q'], 160), co.path(ch),
                                                    f'{co.base}og/{ch["slug"]}.png', f'{co.base}ch/{ch["slug"]}.md', co.chapter_ld(ch), co.prerender_chapter(ch)))
            write(f'{co.base}ch/{ch["slug"]}.md', co.chapter_md(ch))
        write(co.base + 'index.md', co.home_md())
        write(co.base + 'llms.txt', co.llms_txt())
        write(co.base + 'llms-full.txt', co.full_md())
        if args.artifact == co.slug:
            with open(os.path.join(HERE, f'artifact-{co.slug}.html'), 'w', encoding='utf-8') as f:
                f.write(full)

    pub = [co for co in courses if co.published]
    write('/index.html', library_page(courses, url, css_href, fonts, today))
    write('/index.md', f'# {SITE_NAME}\n\n> {SITE_TAGLINE}\n\n' + '\n'.join(f'- [{co.c["title"]}]({co.abs(co.base + "index.md")}): {co.c["summary"]}' for co in pub) + '\n')
    lines = [f'# {SITE_NAME}', '', f'> {SITE_TAGLINE} Practical, sourced and dated courses for product teams, each available as clean Markdown.', '', '## Courses', '']
    for co in pub:
        lines.append(f'- [{co.c["title"]}]({co.abs(co.base + "llms.txt")}): {co.c["summary"]} {len(co.chapters)} chapters, updated {co.c.get("updated", today)}.')
    lines += ['', '## Optional', '', f'- [Everything in one file]({co.abs("/llms-full.txt") if pub else "/llms-full.txt"}): every course, every chapter', '']
    write('/llms.txt', '\n'.join(lines))
    write('/llms-full.txt', '\n\n---\n\n'.join(co.full_md() for co in pub))

    nf_body = (f'<div class="wrap"><header class="bar"><a class="mark" href="/">Internal Learning</a></header><main><div class="prerender">'
               f'<p class="eyebrow">404</p><h1>That page isn’t here</h1><p>The link may be out of date. Every course is listed in the <a href="/">library</a>.</p></div></main></div>')
    write('/404.html', f'<!doctype html>\n<html lang="{LANG}">\n<head>\n' + head_tags(url, f'Page not found · {SITE_NAME}', 'This page doesn’t exist.', '/404.html', '/og/library.png', '/index.md', [], css_href, fonts, index=False) + f'\n</head>\n<body>\n{nf_body}\n</body>\n</html>\n')

    robots = 'User-agent: *\nAllow: /\n'
    if url:
        urls = ['/'] + [u for co in pub for u in [co.base] + [co.path(ch) for ch in co.chapters]]
        write('/sitemap.xml', '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
              ''.join(f'  <url><loc>{url}{u}</loc><lastmod>{today}</lastmod></url>\n' for u in urls) + '</urlset>\n')
        robots += f'\nSitemap: {url}/sitemap.xml\n'
    else:
        print('  ! no site URL set (site.json "url" or SITE_URL): skipped sitemap.xml and absolute canonical/Open Graph URLs')
    write('/robots.txt', robots)
    write('/_headers', '/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n'
                       '  X-Frame-Options: SAMEORIGIN\n  Permissions-Policy: camera=(), microphone=(), geolocation=()\n'
                       '/assets/*\n  Cache-Control: public, max-age=31536000, immutable\n'
                       '/*.md\n  Content-Type: text/markdown; charset=utf-8\n'
                       '/*.txt\n  Content-Type: text/plain; charset=utf-8\n')
    redirects = cfg.get('redirects', [])
    write('/_redirects', ''.join(f'{r["from"]} {r["to"]} {r.get("status", 301)}\n' for r in redirects))

    total = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(DIST) for f in fs)
    print(f'built dist/: library + {len(courses)} course(s), {sum(len(co.chapters) for co in courses)} chapter pages, {total // 1024} KB')


if __name__ == '__main__':
    main()
