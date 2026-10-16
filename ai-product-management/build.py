#!/usr/bin/env python3
"""Build the AI Product Management course.

Merges chapters/ch*.json into src/index.template.html and writes a
self-contained site to dist/ (index.html plus Cloudflare _headers).
Only the standard library is used, so it runs on any Python 3.8+.

  python3 build.py              build into dist/
  python3 build.py --check      validate chapters only, write nothing
  python3 build.py --artifact   also write dist/artifact.html (body-only page for Claude artifacts)

Exits non-zero if any chapter fails validation, so CI can gate on it.
"""
import argparse
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, 'src', 'index.template.html')
CHAPTERS = os.path.join(HERE, 'chapters')
DIST = os.path.join(HERE, 'dist')
PLACEHOLDER = 'var CHDATA = {} /*CHDATA*/;'
ALLOWED_TAGS = {'p', 'strong', 'em', 'code', 'sup', 'h3', 'ul', 'ol', 'li', 'a', 'div', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'br'}
BALANCED = ['p', 'ul', 'ol', 'li', 'div', 'table', 'strong', 'em']
HEADERS = """/*
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  X-Frame-Options: SAMEORIGIN
  Permissions-Policy: camera=(), microphone=(), geolocation=()
"""


def check_html(label, html, problems):
    tags = set(re.findall(r'</?([a-z0-9]+)', html)) - ALLOWED_TAGS
    if tags:
        problems.append(f'{label}: tags not allowed {sorted(tags)}')
    for t in BALANCED:
        opened = len(re.findall(r'<%s[ >]' % t, html))
        closed = html.count('</%s>' % t)
        if opened != closed:
            problems.append(f'{label}: <{t}> opened {opened}, closed {closed}')
    if re.search(r'<script|on\w+=|javascript:', html, re.I):
        problems.append(f'{label}: scripts or event handlers are not allowed')


def load_chapters():
    data, problems = {}, []
    for path in sorted(glob.glob(os.path.join(CHAPTERS, 'ch*.json'))):
        name = os.path.basename(path)
        try:
            d = json.load(open(path, encoding='utf-8'))
        except json.JSONDecodeError as e:
            problems.append(f'{name}: invalid JSON ({e})')
            continue
        cid = d.get('id')
        if not isinstance(cid, int) or not 2 <= cid <= 14 or name != f'ch{cid}.json':
            problems.append(f'{name}: "id" must be 2–14 and match the file name')
            continue
        for key in ('lessons', 'lab', 'quiz', 'deliverable'):
            if key not in d:
                problems.append(f'{name}: missing "{key}"')
        for i, lesson in enumerate(d.get('lessons', []), 1):
            html = lesson.get('html', '')
            if not lesson.get('t'):
                problems.append(f'{name} lesson {i}: missing title "t"')
            if '<div class="pm">' not in html or not html.rstrip().endswith('</ul></div>'):
                problems.append(f'{name} lesson {i}: must end with the "What changes for you" box')
            check_html(f'{name} lesson {i}', html, problems)
        lab = d.get('lab', {})
        if not lab.get('steps'):
            problems.append(f'{name}: lab has no steps')
        for part in [lab.get('intro', ''), lab.get('template', ''), lab.get('done', '')] + list(lab.get('steps', [])):
            check_html(f'{name} lab', part, problems)
        for j, q in enumerate(d.get('quiz', []), 1):
            if not (isinstance(q.get('a'), int) and 0 <= q['a'] < len(q.get('o', []))):
                problems.append(f'{name} quiz {j}: answer index out of range')
        check_html(f'{name} deliverable', d.get('deliverable', {}).get('html', ''), problems)
        data[cid] = d
    return data, problems


def build_page(data):
    src = open(TEMPLATE, encoding='utf-8').read()
    if PLACEHOLDER not in src:
        sys.exit('build: chapter placeholder missing from src/index.template.html')
    js = json.dumps(data, ensure_ascii=False).replace('</', '<\\/')
    return src.replace(PLACEHOLDER, 'var CHDATA = ' + js + ';', 1)


def standalone(page):
    body_start = page.index('<div class="wrap">')
    return ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            '<meta name="description" content="A 14-chapter course that takes experienced product managers to AI product management.">\n'
            '<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}'
            'body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>\n'
            + page[:body_start] + '</head>\n<body>\n' + page[body_start:] + '\n</body>\n</html>\n')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--check', action='store_true', help='validate only')
    ap.add_argument('--artifact', action='store_true', help='also write dist/artifact.html')
    args = ap.parse_args()

    data, problems = load_chapters()
    print(f'chapters loaded: {sorted(data)}')
    if problems:
        print('\n'.join('  ✗ ' + p for p in problems))
        sys.exit(f'build failed: {len(problems)} problem(s)')
    if args.check:
        print('check passed')
        return

    page = build_page(data)
    os.makedirs(DIST, exist_ok=True)
    with open(os.path.join(DIST, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(standalone(page))
    with open(os.path.join(DIST, '_headers'), 'w', encoding='utf-8') as f:
        f.write(HEADERS)
    if args.artifact:
        with open(os.path.join(DIST, 'artifact.html'), 'w', encoding='utf-8') as f:
            f.write(page)
    print(f'built dist/index.html ({os.path.getsize(os.path.join(DIST, "index.html")) // 1024} KB)')


if __name__ == '__main__':
    main()
