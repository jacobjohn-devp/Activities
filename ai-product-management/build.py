#!/usr/bin/env python3
"""Build the AI Product Management course site.

Reads chapters/course.json (outline) and chapters/ch1.json … ch14.json
(content), injects them into src/index.template.html, and writes a static
site to dist/:

  /                      home, prerendered, with SEO and Open Graph tags
  /ch/<slug>/            one page per chapter, prerendered
  /ch/<slug>.md, /index.md   clean Markdown copies for LLMs
  /llms.txt, /llms-full.txt  LLM index and full text (llmstxt.org)
  /sitemap.xml, /robots.txt, /404.html, /_headers
  /assets/app.<hash>.css|js  shared, cache-forever assets
  /og/*.png              share images (from static/og, made by tools/make_og.py)

Absolute URLs (canonical, Open Graph, sitemap) need the site's address. Set
it in site.json ("url") or the SITE_URL environment variable; without it the
build still works but skips the sitemap and absolute URLs.

  python3 build.py              build dist/
  python3 build.py --check      validate content only
  python3 build.py --artifact   also write artifact.html (single file, hash routes, for Claude artifacts; not deployed)

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
TEMPLATE = os.path.join(HERE, 'src', 'index.template.html')
CHAPTERS = os.path.join(HERE, 'chapters')
STATIC = os.path.join(HERE, 'static')
DIST = os.path.join(HERE, 'dist')
PLACEHOLDER = 'var COURSE = {} /*COURSE*/;'
LANG = 'en-GB'
SITE_NAME = 'AI Product Management'
ALLOWED_TAGS = {'p', 'strong', 'em', 'code', 'sup', 'h3', 'ul', 'ol', 'li', 'a', 'div', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'br'}
BALANCED = ['p', 'ul', 'ol', 'li', 'div', 'table', 'strong', 'em']
FAVICON = ("data:image/svg+xml," + "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E"
           "%3Crect width='64' height='64' fill='%23ebebeb'/%3E%3Ccircle cx='40' cy='22' r='22' fill='%239bcb1a'/%3E"
           "%3Crect x='6' y='30' width='34' height='28' fill='%23111111'/%3E%3C/svg%3E")


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


def load_course():
    problems = []
    course = json.load(open(os.path.join(CHAPTERS, 'course.json'), encoding='utf-8'))
    ids = [c['id'] for c in course['chapters']]
    if ids != list(range(1, len(ids) + 1)):
        problems.append('course.json: chapter ids must run 1, 2, 3 … in order')
    slugs = [c['slug'] for c in course['chapters']]
    if len(set(slugs)) != len(slugs) or any(not re.fullmatch(r'[a-z0-9-]+', s) for s in slugs):
        problems.append('course.json: slugs must be unique lowercase-with-hyphens')
    data = {}
    for path in sorted(glob.glob(os.path.join(CHAPTERS, 'ch*.json'))):
        name = os.path.basename(path)
        try:
            d = json.load(open(path, encoding='utf-8'))
        except json.JSONDecodeError as e:
            problems.append(f'{name}: invalid JSON ({e})')
            continue
        cid = d.get('id')
        if cid not in ids or name != f'ch{cid}.json':
            problems.append(f'{name}: "id" must match the file name and course.json')
            continue
        required = ('lessons', 'quiz', 'glossary') if cid == 1 else ('lessons', 'lab', 'quiz', 'deliverable')
        for key in required:
            if key not in d:
                problems.append(f'{name}: missing "{key}"')
        for i, lesson in enumerate(d.get('lessons', []), 1):
            text = lesson.get('html', '')
            if not lesson.get('t'):
                problems.append(f'{name} lesson {i}: missing title "t"')
            if '<div class="pm">' not in text or not text.rstrip().endswith('</ul></div>'):
                problems.append(f'{name} lesson {i}: must end with the "What changes for you" box')
            check_html(f'{name} lesson {i}', text, problems)
        if cid != 1:
            lab = d.get('lab', {})
            if not lab.get('steps'):
                problems.append(f'{name}: lab has no steps')
            for part in [lab.get('intro', ''), lab.get('template', ''), lab.get('done', '')] + list(lab.get('steps', [])):
                check_html(f'{name} lab', part, problems)
            check_html(f'{name} deliverable', d.get('deliverable', {}).get('html', ''), problems)
        for j, q in enumerate(d.get('quiz', []), 1):
            if not (isinstance(q.get('a'), int) and 0 <= q['a'] < len(q.get('o', []))):
                problems.append(f'{name} quiz {j}: answer index out of range')
        data[cid] = d
    if 1 not in data:
        problems.append('ch1.json is missing')
    return course, data, problems


# ---------------------------------------------------------------- HTML → Markdown (for llms.txt and .md pages)

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
            rows = []
            for tr in _find(k, 'tr'):
                rows.append([_inline(c).strip().replace('|', '\\|') for c in tr.kids if not isinstance(c, str) and c.tag in ('th', 'td')])
            if rows:
                width = max(len(r) for r in rows)
                rows = [r + [''] * (width - len(r)) for r in rows]
                md = ['| ' + ' | '.join(rows[0]) + ' |', '|' + ' --- |' * width] + ['| ' + ' | '.join(r) + ' |' for r in rows[1:]]
                out.append('\n'.join(md))
        elif k.tag == 'div' and ('callout' in cls or 'pm' in cls):
            tmp = []
            _blocks(k, tmp, depth)
            out.append('\n>\n'.join('> ' + b.replace('\n', '\n> ') for b in tmp))
        else:
            _blocks(k, out, depth)


def _find(n, tag):
    found = []
    for k in n.kids:
        if not isinstance(k, str):
            if k.tag == tag:
                found.append(k)
            found.extend(_find(k, tag))
    return found


def to_markdown(fragment):
    tree = _Tree()
    tree.feed(fragment or '')
    out = []
    _blocks(tree.root, out)
    return '\n\n'.join(b for b in out if b.strip())


def plain(fragment, limit=None):
    text = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', fragment or ''))).strip()
    if limit and len(text) > limit:
        text = text[:limit - 1].rsplit(' ', 1)[0] + '…'
    return text


# ---------------------------------------------------------------- page pieces

def esc(s):
    return html.escape(str(s), quote=True)


class Site:
    def __init__(self, course, data, url):
        self.course, self.data, self.url = course, data, (url or '').rstrip('/')
        self.chapters = course['chapters']
        self.today = datetime.date.today().isoformat()

    def path(self, c=None):
        return '/' if c is None else f'/ch/{c["slug"]}/'

    def abs(self, path):
        return self.url + path if self.url else path

    def words(self, c):
        d = self.data.get(c['id'], {})
        n = sum(len(plain(l['html']).split()) for l in d.get('lessons', []))
        return n

    def minutes(self, c):
        return max(30, round(self.words(c) / 220 + 75))

    def part(self, c):
        return self.course['parts'][c['part']]

    # --- prerendered body (replaced by the app once JS runs; this is what crawlers and no-JS readers get)
    def prerender_home(self):
        h = [f'<div class="prerender"><p class="eyebrow">Internal Learning · course</p><h1>{esc(self.course["title"])}</h1>',
             f'<p class="lede">{esc(self.course["tagline"])} Fourteen chapters with precise mental models, hands-on labs and a work artefact at the end of every chapter, written for product managers who already ship complex software.</p>']
        for i, p in enumerate(self.course['parts']):
            h.append(f'<section id="part-{i + 1}"><h2>Part {esc(p["n"])} · {esc(p["title"])}</h2><p>{esc(p["blurb"])}</p><ol>')
            for c in self.chapters:
                if c['part'] == i:
                    h.append(f'<li value="{c["id"]}"><a href="{self.path(c)}">{esc(c["title"])}</a>: {esc(c["q"])}</li>')
            h.append('</ol></section>')
        h.append('</div>')
        return ''.join(h)

    def prerender_chapter(self, c):
        d, p = self.data[c['id']], self.part(c)
        h = [f'<div class="prerender"><nav aria-label="Breadcrumb" class="eyebrow"><a href="/">{esc(SITE_NAME)}</a> · Part {esc(p["n"])} · {esc(p["title"])}</nav>',
             f'<h1>{esc(c["title"])}</h1><p class="lede">{esc(c["q"])}</p>']
        for i, l in enumerate(d['lessons'], 1):
            h.append(f'<section id="l{i}"><h2>Lesson {c["id"]}.{i} · {esc(l["t"])}</h2>{l["html"]}</section>')
        if c['id'] == 1:
            h.append('<section id="lab"><h2>Lab: model the cost of an AI feature</h2><p>An interactive calculator for cost per request, per user and per month, split by uncached input, cached input, output and thinking tokens.</p></section>')
            h.append('<section id="glossary"><h2>Glossary</h2><dl>' + ''.join(
                f'<dt>{esc(g["term"])}</dt><dd>{esc(g["def"])}</dd>' for g in d['glossary']) + '</dl></section>')
        else:
            lab = d['lab']
            h.append(f'<section id="lab"><h2>Lab: {esc(lab["title"])}</h2>{lab.get("intro", "")}<ol>' +
                     ''.join(f'<li>{s}</li>' for s in lab['steps']) + '</ol>' + lab.get('template', '') + lab.get('done', '') + '</section>')
        h.append('<section id="quiz"><h2>Check yourself</h2><ol>' + ''.join(
            f'<li>{esc(q["q"])}<ul>' + ''.join(f'<li>{esc(o)}</li>' for o in q['o']) + '</ul></li>' for q in d['quiz']) + '</ol></section>')
        if 'deliverable' in d:
            h.append(f'<section id="deliverable"><h2>Deliverable: {esc(d["deliverable"]["title"])}</h2>{d["deliverable"]["html"]}</section>')
        if d.get('reading'):
            h.append('<section><h2>Further reading</h2><ul>' + ''.join(
                f'<li><a href="{esc(r["url"])}" rel="noopener">{esc(r["label"])}</a></li>' for r in d['reading']) + '</ul></section>')
        i = c['id'] - 1
        nav = []
        if i > 0:
            nav.append(f'<a href="{self.path(self.chapters[i - 1])}">Previous: {esc(self.chapters[i - 1]["title"])}</a>')
        if i < len(self.chapters) - 1:
            nav.append(f'<a href="{self.path(self.chapters[i + 1])}">Next: {esc(self.chapters[i + 1]["title"])}</a>')
        h.append('<nav class="pager" aria-label="Chapters">' + ''.join(nav) + '</nav></div>')
        return ''.join(h)

    # --- head
    def head(self, kind, title, description, path, image, md_path, jsonld, css_href, fonts_link):
        canonical = self.abs(path)
        img = self.abs(image)
        tags = [
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">',
            f'<title>{esc(title)}</title>',
            f'<meta name="description" content="{esc(description)}">',
            '<meta name="robots" content="index, follow, max-image-preview:large">',
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
        if self.url:
            tags += [f'<link rel="canonical" href="{canonical}">',
                     f'<meta property="og:url" content="{canonical}">',
                     f'<meta property="og:image" content="{img}">',
                     '<meta property="og:image:width" content="1200">', '<meta property="og:image:height" content="630">',
                     f'<meta property="og:image:alt" content="{esc(title)}">',
                     f'<meta name="twitter:image" content="{img}">']
        tags += ['<link rel="preconnect" href="https://fonts.googleapis.com">',
                 '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
                 fonts_link,
                 f'<link rel="stylesheet" href="{css_href}">',
                 '<style>body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>']
        for block in jsonld:
            tags.append('<script type="application/ld+json">' + json.dumps(block, ensure_ascii=False).replace('</', '<\\/') + '</script>')
        return '\n'.join(tags)

    def course_ld(self):
        return {
            '@context': 'https://schema.org', '@type': 'Course',
            'name': self.course['title'], 'description': self.course['tagline'],
            'url': self.abs('/'), 'image': self.abs('/og/home.png'), 'inLanguage': LANG,
            'isAccessibleForFree': True, 'educationalLevel': 'Advanced',
            'audience': {'@type': 'Audience', 'audienceType': 'Product managers'},
            'provider': {'@type': 'Organization', 'name': 'Internal Learning'},
            'teaches': [c['title'] for c in self.chapters],
            'dateModified': self.today,
            'hasPart': [{'@type': 'LearningResource', 'position': c['id'], 'name': c['title'], 'url': self.abs(self.path(c))} for c in self.chapters],
        }

    def chapter_ld(self, c):
        return [{
            '@context': 'https://schema.org', '@type': 'LearningResource',
            'name': c['title'], 'description': c['q'], 'url': self.abs(self.path(c)),
            'image': self.abs(f'/og/{c["slug"]}.png'), 'inLanguage': LANG, 'isAccessibleForFree': True,
            'learningResourceType': 'Course chapter', 'educationalLevel': 'Advanced',
            'timeRequired': f'PT{self.minutes(c)}M', 'position': c['id'], 'dateModified': self.today,
            'teaches': [l['t'] for l in self.data[c['id']]['lessons']],
            'isPartOf': {'@type': 'Course', 'name': self.course['title'], 'url': self.abs('/')},
        }, {
            '@context': 'https://schema.org', '@type': 'BreadcrumbList',
            'itemListElement': [
                {'@type': 'ListItem', 'position': 1, 'name': self.course['title'], 'item': self.abs('/')},
                {'@type': 'ListItem', 'position': 2, 'name': c['title'], 'item': self.abs(self.path(c))},
            ],
        }]

    # --- markdown
    def chapter_md(self, c):
        d, p = self.data[c['id']], self.part(c)
        out = [f'# Chapter {c["id"]}: {c["title"]}', f'> {c["q"]}',
               f'Part {p["n"]}, {p["title"]}. Shelf life: {c["shelf"]}. Web version: {self.abs(self.path(c))}']
        for i, l in enumerate(d['lessons'], 1):
            out.append(f'## Lesson {c["id"]}.{i}: {l["t"]}\n\nShelf life: {l.get("shelf", "")}\n\n{to_markdown(l["html"])}')
        if c['id'] == 1:
            out.append('## Glossary\n\n' + '\n'.join(f'- **{g["term"]}** ({g["area"]}): {g["def"]}' for g in d['glossary']))
        else:
            lab = d['lab']
            steps = '\n'.join(f'{i}. {to_markdown(s)}' for i, s in enumerate(lab['steps'], 1))
            out.append(f'## Lab: {lab["title"]} ({lab.get("time", "")})\n\n{to_markdown(lab.get("intro", ""))}\n\n{steps}\n\n{to_markdown(lab.get("template", ""))}\n\n{to_markdown(lab.get("done", ""))}'.strip())
        quiz = []
        for i, q in enumerate(d['quiz'], 1):
            opts = '\n'.join(f'   - {o}' for o in q['o'])
            quiz.append(f'{i}. {q["q"]}\n{opts}\n   - Answer: {q["o"][q["a"]]}. {q["w"]}')
        out.append('## Check yourself\n\n' + '\n'.join(quiz))
        if 'deliverable' in d:
            out.append(f'## Deliverable: {d["deliverable"]["title"]}\n\n{to_markdown(d["deliverable"]["html"])}')
        if d.get('reading'):
            out.append('## Further reading\n\n' + '\n'.join(f'- [{r["label"]}]({r["url"]})' for r in d['reading']))
        return '\n\n'.join(out) + '\n'

    def home_md(self):
        out = [f'# {self.course["title"]}', f'> {self.course["tagline"]}']
        for i, p in enumerate(self.course['parts']):
            out.append(f'## Part {p["n"]}: {p["title"]}\n\n{p["blurb"]}\n\n' + '\n'.join(
                f'{c["id"]}. [{c["title"]}]({self.abs("/ch/" + c["slug"] + ".md")}): {c["q"]}' for c in self.chapters if c['part'] == i))
        return '\n\n'.join(out) + '\n'

    def llms_txt(self):
        lines = [f'# {self.course["title"]}', '',
                 f'> {self.course["tagline"]} Written for product managers who already ship complex software. Each chapter has lessons, a hands-on lab, a quiz and a work deliverable. Content is current as of October 2026; chapters are labelled with how fast they date.', '',
                 'The course runs in four parts: how the machine thinks (vocabulary, how LLMs are built, reading the frontier), building blocks (context engineering, evals, agents, knowledge and data), shipping AI products (AI coding, AI experience design, reliability, unit economics, security and governance) and strategy and leadership (strategy on a moving frontier, the AI-native product team and a capstone).', '',
                 'Every chapter is available as clean Markdown at the links below.', '']
        for i, p in enumerate(self.course['parts']):
            lines.append(f'## Part {p["n"]}: {p["title"]}')
            lines.append('')
            for c in self.chapters:
                if c['part'] == i:
                    lines.append(f'- [{c["id"]}. {c["title"]}]({self.abs("/ch/" + c["slug"] + ".md")}): {c["q"]}')
            lines.append('')
        lines += ['## Optional', '', f'- [Full course text]({self.abs("/llms-full.txt")}): every chapter in one Markdown file',
                  f'- [Course home]({self.abs("/")}): the interactive web version', '']
        return '\n'.join(lines)


# ---------------------------------------------------------------- build

def split_template(src):
    style = re.search(r'<style>([\s\S]*?)</style>', src).group(1)
    fonts = re.search(r'<link rel="stylesheet" href="https://fonts\.googleapis\.com[^>]+>', src).group(0)
    body = src[src.index('<div class="wrap">'):src.index('<script>')]
    script = re.search(r'<script>([\s\S]*?)</script>', src).group(1)
    return style, fonts, body, script


def hashed(name, ext, content):
    h = hashlib.sha256(content.encode('utf-8')).hexdigest()[:10]
    return f'/assets/{name}.{h}.{ext}'


def write(rel, content):
    path = os.path.join(DIST, rel.lstrip('/'))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def main():
    ap = argparse.ArgumentParser(description='Build the AI Product Management course site.')
    ap.add_argument('--check', action='store_true', help='validate content only')
    ap.add_argument('--artifact', action='store_true', help='also write artifact.html (not deployed)')
    args = ap.parse_args()

    course, data, problems = load_course()
    print(f'chapters loaded: {sorted(data)}')
    if problems:
        print('\n'.join('  ✗ ' + p for p in problems))
        sys.exit(f'build failed: {len(problems)} problem(s)')
    if args.check:
        print('check passed')
        return

    cfg_path = os.path.join(HERE, 'site.json')
    cfg = json.load(open(cfg_path)) if os.path.exists(cfg_path) else {}
    url = os.environ.get('SITE_URL') or cfg.get('url') or ''
    site = Site(course, data, url)

    src = open(TEMPLATE, encoding='utf-8').read()
    if PLACEHOLDER not in src:
        sys.exit('build: COURSE placeholder missing from src/index.template.html')
    payload = json.dumps({'title': course['title'], 'tagline': course['tagline'], 'parts': course['parts'],
                          'chapters': course['chapters'], 'data': data}, ensure_ascii=False).replace('</', '<\\/')
    full = src.replace(PLACEHOLDER, 'var COURSE = ' + payload + ';', 1)

    if os.path.isdir(DIST):
        shutil.rmtree(DIST)
    os.makedirs(DIST)

    style, fonts, body, script = split_template(full)
    css_href, js_href = hashed('app', 'css', style), hashed('app', 'js', script)
    write(css_href, style)
    write(js_href, script)
    if os.path.isdir(os.path.join(STATIC, 'og')):
        shutil.copytree(os.path.join(STATIC, 'og'), os.path.join(DIST, 'og'))

    ch1 = course['chapters'][0]
    def page(kind, title, description, path, image, md_path, jsonld, prerender):
        b = body.replace('<main id="app"></main>', f'<main id="app">{prerender}</main>', 1)
        b = b.replace('href="#home"', 'href="/"').replace('href="#ch1"', f'href="{site.path(ch1)}"')
        return (f'<!doctype html>\n<html lang="{LANG}">\n<head>\n'
                + site.head(kind, title, description, path, image, md_path, jsonld, css_href, fonts)
                + f'\n</head>\n<body>\n{b}<script>window.__SITE = true;</script>\n<script src="{js_href}"></script>\n</body>\n</html>\n')

    write('/index.html', page('website', f'{course["title"]} · A course for product managers',
                              plain(course['tagline'] + ' Lessons, labs and quizzes on LLMs, evals, agents, AI coding, pricing and governance.', 160),
                              '/', '/og/home.png', '/index.md', [site.course_ld()], site.prerender_home()))
    for c in course['chapters']:
        write(site.path(c) + 'index.html', page('article', f'{c["title"]} · {course["title"]}', plain(c['q'], 160),
                                                 site.path(c), f'/og/{c["slug"]}.png', f'/ch/{c["slug"]}.md',
                                                 site.chapter_ld(c), site.prerender_chapter(c)))
        write(f'/ch/{c["slug"]}.md', site.chapter_md(c))

    write('/index.md', site.home_md())
    write('/llms.txt', site.llms_txt())
    write('/llms-full.txt', site.home_md() + '\n\n' + '\n\n'.join(site.chapter_md(c) for c in course['chapters']))

    not_found = ('<div class="prerender"><p class="eyebrow">404</p><h1>That page isn’t here</h1>'
                 '<p>The link may be out of date. Every chapter is listed on the <a href="/">course home</a>.</p></div>')
    nf = page('website', f'Page not found · {course["title"]}', 'This page doesn’t exist.', '/404.html', '/og/home.png', '/index.md', [], not_found)
    write('/404.html', nf.replace('content="index, follow, max-image-preview:large"', 'content="noindex"')
          .replace(f'<script>window.__SITE = true;</script>\n<script src="{js_href}"></script>\n', ''))

    robots = 'User-agent: *\nAllow: /\n'
    if url:
        urls = ['/'] + [site.path(c) for c in course['chapters']]
        write('/sitemap.xml', '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
              ''.join(f'  <url><loc>{site.abs(u)}</loc><lastmod>{site.today}</lastmod></url>\n' for u in urls) + '</urlset>\n')
        robots += f'\nSitemap: {site.abs("/sitemap.xml")}\n'
    else:
        print('  ! no site URL set (site.json "url" or SITE_URL): skipped sitemap.xml and absolute canonical/Open Graph URLs')
    write('/robots.txt', robots)
    write('/_headers', '/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n'
                       '  X-Frame-Options: SAMEORIGIN\n  Permissions-Policy: camera=(), microphone=(), geolocation=()\n'
                       '/assets/*\n  Cache-Control: public, max-age=31536000, immutable\n'
                       '/og/*\n  Cache-Control: public, max-age=86400\n'
                       '/*.md\n  Content-Type: text/markdown; charset=utf-8\n'
                       '/llms*.txt\n  Content-Type: text/plain; charset=utf-8\n')

    if args.artifact:
        # Kept out of dist/ so it is never deployed alongside the site
        with open(os.path.join(HERE, 'artifact.html'), 'w', encoding='utf-8') as f:
            f.write(full)

    total = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(DIST) for f in fs)
    print(f'built dist/: {len(course["chapters"]) + 1} pages, llms.txt, {"sitemap, " if url else ""}{total // 1024} KB total')


if __name__ == '__main__':
    main()
