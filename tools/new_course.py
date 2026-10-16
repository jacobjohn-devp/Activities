#!/usr/bin/env python3
"""Start a new course in courses/<slug>/ with a valid outline and one sample chapter.

  python3 tools/new_course.py <slug> "Course title" [--hue sky] [--shape ring]

The course starts as a draft: it builds and you can preview it at /<slug>/,
but it stays out of the library, sitemap and llms.txt until you set
"status": "published" in course.json.
"""
import argparse
import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HUES = ['lime', 'sky', 'orange', 'pink', 'yellow', 'blue']
SHAPES = ['disc', 'ring', 'pill', 'half', 'stripes', 'discs']


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('slug', help='lowercase-with-hyphens, used in the URL')
    ap.add_argument('title')
    ap.add_argument('--hue', default='sky', choices=HUES)
    ap.add_argument('--shape', default='ring', choices=SHAPES)
    args = ap.parse_args()
    if not re.fullmatch(r'[a-z0-9]+(-[a-z0-9]+)*', args.slug):
        sys.exit('slug must be lowercase letters, digits and single hyphens')
    folder = os.path.join(HERE, 'courses', args.slug)
    if os.path.exists(folder):
        sys.exit(f'courses/{args.slug} already exists')
    os.makedirs(folder)
    course = {
        'slug': args.slug, 'title': args.title,
        'tagline': 'One sentence on what this course is and who it is for.',
        'summary': 'Two sentences for the library card: what the reader learns and why it matters.',
        'lede': 'The paragraph under the title on the course home page.',
        'card': args.title, 'hue': args.hue, 'shape': args.shape,
        'tags': ['Topic'], 'audience': 'Product managers', 'level': 'Intermediate',
        'updated': datetime.date.today().isoformat(), 'status': 'draft', 'features': [],
        'parts': [{'n': 'I', 'title': 'Foundations', 'hue': args.hue, 'blurb': 'What this part covers.'}],
        'chapters': [{'id': 1, 'part': 0, 'slug': 'getting-started', 'shape': args.shape, 'title': 'Getting started',
                      'sub': 'Basics · 1 lessons', 'shelf': 'Durable',
                      'q': 'The question the reader can answer after this chapter?',
                      'lessons': ['First lesson title']}],
    }
    ch1 = {
        'id': 1,
        'lessons': [{
            't': 'First lesson title', 'shelf': 'Durable',
            'html': '<p>Write the lesson here. See docs/writing-brief.md for the voice, accuracy rules and the HTML you can use.</p>'
                    '<div class="pm"><p class="eyebrow">What changes for you</p><ul><li>One concrete thing the reader does differently.</li></ul></div>',
        }],
        'quiz': [{'q': 'A realistic scenario question?', 'o': ['Option A', 'Option B', 'Option C', 'Option D'], 'a': 1, 'w': 'Why B is right.'}],
    }
    json.dump(course, open(os.path.join(folder, 'course.json'), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    json.dump(ch1, open(os.path.join(folder, 'ch1.json'), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print(f'created courses/{args.slug}/ (draft). Next: edit course.json and ch1.json, add chapters, run python3 build.py, '
          f'then python3 tools/make_og.py {args.slug} for share images.')


if __name__ == '__main__':
    main()
