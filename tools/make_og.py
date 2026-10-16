#!/usr/bin/env python3
"""Make the 1200x630 social share images: one per course page (courses/<slug>/og/) and the library's (static/og/library.png).

Needs Pillow, which the site build does not, so run it by hand when a chapter
title, part or shape changes, and commit the PNGs:

  python3 -m pip install pillow
  python3 tools/make_og.py [slug ...] [--font-dir /path/to/fonts]

The art follows the poster openers: one hue shape bleeding off the right
edge, an oversized numeral knocked out where the shape crosses it, and a
black label card bottom-left.
"""
import argparse
import json
import os

from PIL import Image, ImageChops, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # repo root
W, H = 1200, 630
SURFACE, INK, CARD, WHITE = (235, 235, 235), (17, 17, 17), (17, 17, 17), (255, 255, 255)
HUES = {'lime': (155, 203, 26), 'sky': (36, 180, 230), 'orange': (246, 168, 0), 'pink': (233, 138, 160), 'yellow': (244, 180, 0), 'blue': (63, 143, 218)}
FONT_CANDIDATES = {
    'bold': ['InterTight-ExtraBold.ttf', 'Inter-Bold.ttf', '/System/Library/Fonts/Supplemental/Arial Bold.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'],
    'black': ['InterTight-ExtraBold.ttf', '/System/Library/Fonts/Supplemental/Arial Black.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'],
    'mono': ['JetBrainsMono-SemiBold.ttf', '/System/Library/Fonts/SFNSMono.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf'],
}


def font(kind, size, font_dir):
    for name in FONT_CANDIDATES[kind]:
        path = name if os.path.isabs(name) else os.path.join(font_dir or '', name)
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def shape_mask(kind):
    """White-on-black mask of the hero shape. 'discs' returns one mask per disc so overlaps can darken."""
    def blank():
        return Image.new('L', (W, H), 0)
    if kind == 'discs':
        masks = []
        for y in (40, 315, 590):
            m = blank(); ImageDraw.Draw(m).ellipse((960 - 190, y - 190, 960 + 190, y + 190), fill=255); masks.append(m)
        return masks
    m = blank(); d = ImageDraw.Draw(m)
    if kind == 'ring':
        d.ellipse((900 - 240, 315 - 240, 900 + 240, 315 + 240), fill=255)
        d.ellipse((900 - 130, 315 - 130, 900 + 130, 315 + 130), fill=0)
    elif kind == 'pill':
        d.rounded_rectangle((780, -160, 1060, 800), radius=140, fill=255)
    elif kind == 'half':
        d.pieslice((700 - 420, 500 - 420, 700 + 420, 500 + 420), 270, 360, fill=255)
        d.rectangle((700, 500, 1120, H), fill=255)
    elif kind == 'stripes':
        for y, h in ((170, 10), (215, 18), (270, 30), (340, 48), (430, 70), (535, 95)):
            d.rectangle((0, y, W, y + h), fill=255)
    else:  # disc
        d.ellipse((880 - 360, 130 - 360, 880 + 360, 130 + 360), fill=255)
    return [m]


def wrap(draw, text, fnt, width):
    words, lines, line = text.split(), [], ''
    for w in words:
        trial = (line + ' ' + w).strip()
        if draw.textlength(trial, font=fnt) <= width or not line:
            line = trial
        else:
            lines.append(line); line = w
    return lines + [line]


def poster(title, sub, eyebrow, hue, kind, numeral, font_dir):
    img = Image.new('RGB', (W, H), SURFACE)
    masks = shape_mask(kind)
    # shape, with multiplied overlaps for stacked discs
    layer = Image.new('RGB', (W, H), WHITE)
    for m in masks:
        disc = Image.new('RGB', (W, H), WHITE); disc.paste(hue, mask=m)
        layer = ImageChops.multiply(layer, disc)
    union = masks[0].copy()
    for m in masks[1:]:
        union = ImageChops.lighter(union, m)
    img.paste(layer, mask=union)
    # oversized numeral, knocked out to the ground colour where the shape crosses it
    if numeral:
        num = Image.new('L', (W, H), 0)
        nf = font('black', 400, font_dir)
        nd = ImageDraw.Draw(num)
        tw = nd.textlength(numeral, font=nf)
        nd.text((W - 30 - tw, H - 40), numeral, font=nf, fill=255, anchor='ls')
        img.paste(INK, mask=ImageChops.subtract(num, union))
        img.paste(SURFACE, mask=ImageChops.multiply(num, union))
    # label card
    d = ImageDraw.Draw(img)
    x0, y1, cw = 60, H - 56, 560
    tf = font('bold', 54, font_dir)
    lines = wrap(d, title, tf, cw - 64)[:3]
    ch = 96 + len(lines) * 60 + 44
    y0 = y1 - ch
    d.rectangle((x0, y0, x0 + cw, y1), fill=CARD)
    mf = font('mono', 20, font_dir)
    d.text((x0 + 32, y0 + 30), eyebrow.upper(), font=mf, fill=hue)
    d.text((x0 + cw - 32, y0 + 30), 'LEARNING', font=mf, fill=WHITE, anchor='ra')
    ty = y0 + 96
    for ln in lines:
        d.text((x0 + 32, ty), ln, font=tf, fill=WHITE); ty += 60
    d.text((x0 + 32, ty + 8), sub, font=font('mono', 22, font_dir), fill=hue)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('slugs', nargs='*', help='courses to draw (default: all)')
    ap.add_argument('--font-dir', help='folder holding InterTight-ExtraBold.ttf and JetBrainsMono-SemiBold.ttf, if you have them')
    args = ap.parse_args()
    root = os.path.join(HERE, 'courses')
    slugs = args.slugs or sorted(d for d in os.listdir(root) if os.path.isfile(os.path.join(root, d, 'course.json')))
    lib = os.path.join(HERE, 'static', 'og')
    os.makedirs(lib, exist_ok=True)
    poster('Internal Learning', 'Courses for product teams', 'Library', HUES['sky'], 'pill', '', args.font_dir).save(os.path.join(lib, 'library.png'), optimize=True)
    for slug in slugs:
        course = json.load(open(os.path.join(root, slug, 'course.json'), encoding='utf-8'))
        out = os.path.join(root, slug, 'og')
        os.makedirs(out, exist_ok=True)
        n = len(course['chapters'])
        poster(course['title'], f'{n} chapter{"s" if n != 1 else ""} · Course', 'Course', HUES[course.get('hue', 'lime')], course.get('shape', 'disc'), '', args.font_dir).save(os.path.join(out, 'home.png'), optimize=True)
        for c in course['chapters']:
            part = course['parts'][c['part']]
            poster(c['title'], c['sub'], 'Part ' + part['n'], HUES[part['hue']], c['shape'], '%02d' % c['id'], args.font_dir).save(os.path.join(out, c['slug'] + '.png'), optimize=True)
        print(f'{slug}: {n + 1} images')
    print('library: static/og/library.png')


if __name__ == '__main__':
    main()
