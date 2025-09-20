#!/usr/bin/env python3
"""
Interactive EXIF date watermarker (vibe coding style, font-size via scaling)

Features:
- User inputs a path (file or directory).
- The script scans images (if directory) or uses the single file.
- For each image it extracts EXIF date (DateTimeOriginal / DateTime / DateTimeDigitized).
- Uses the date's YYYY-MM-DD as the watermark text (falls back to file mtime if no EXIF).
- User can set font size (scaling factor), color (hex like #ffffff or name), and position (top-left, center, bottom-right, etc.).
- Outputs images into a subdirectory named: <original-dir>/_watermark
- Interactive prompts; works cross-platform. Does not depend on external fonts anymore.

Dependencies: Pillow
Install: pip install pillow

Save this file and run: python interactive_exif_watermarker.py
"""

from PIL import Image, ImageDraw, ImageFont, ExifTags
import os
import sys
import datetime

# Supported image extensions
EXTS = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp', '.webp'}

# Map human-friendly positions to anchors
POSITIONS = {
    '1': 'top-left',
    '2': 'top-right',
    '3': 'center',
    '4': 'bottom-left',
    '5': 'bottom-right'
}

# Common EXIF tag names to IDs (reverse mapping)
TAG_NAME_TO_ID = {v: k for k, v in ExifTags.TAGS.items()}

DATE_TAGS_TO_TRY = ['DateTimeOriginal', 'DateTime', 'DateTimeDigitized']


def find_images(path):
    path = os.path.abspath(path)
    if os.path.isfile(path):
        return [path]
    images = []
    for root, _, files in os.walk(path):
        for f in files:
            if os.path.splitext(f)[1].lower() in EXTS:
                images.append(os.path.join(root, f))
    return images


def get_exif_date(image_path):
    try:
        img = Image.open(image_path)
        exif = img._getexif() or {}
        # try several tags
        for tagname in DATE_TAGS_TO_TRY:
            tagid = TAG_NAME_TO_ID.get(tagname)
            if tagid and tagid in exif:
                raw = exif[tagid]
                # EXIF datetimes usually look like: "YYYY:MM:DD HH:MM:SS"
                try:
                    date_part = str(raw).split()[0]
                    parts = date_part.split(':')
                    if len(parts) >= 3:
                        yyyy, mm, dd = parts[0], parts[1], parts[2]
                        return f"{yyyy}-{mm}-{dd}"
                except Exception:
                    continue
    except Exception:
        pass
    # fallback to file modification time
    try:
        ts = os.path.getmtime(image_path)
        dt = datetime.datetime.fromtimestamp(ts)
        return dt.strftime('%Y-%m-%d')
    except Exception:
        return None


def parse_color(s):
    s = s.strip()
    if not s:
        return (255, 255, 255, 255)
    # hex
    if s.startswith('#'):
        s = s[1:]
        if len(s) == 6:
            r = int(s[0:2], 16)
            g = int(s[2:4], 16)
            b = int(s[4:6], 16)
            return (r, g, b, 255)
        if len(s) == 3:
            r = int(s[0]*2, 16)
            g = int(s[1]*2, 16)
            b = int(s[2]*2, 16)
            return (r, g, b, 255)
    # try simple names
    named = {
        'white': (255,255,255,255),
        'black': (0,0,0,255),
        'red': (255,0,0,255),
        'green': (0,128,0,255),
        'blue': (0,0,255,255),
        'yellow': (255,255,0,255)
    }
    return named.get(s.lower(), (255,255,255,255))


def compute_position(img_size, text_size, pos_key, margin=10):
    w, h = img_size
    tw, th = text_size
    pos = POSITIONS.get(pos_key, 'bottom-right')
    if pos == 'top-left':
        return (margin, margin)
    if pos == 'top-right':
        return (w - tw - margin, margin)
    if pos == 'center':
        return ((w - tw) // 2, (h - th) // 2)
    if pos == 'bottom-left':
        return (margin, h - th - margin)
    # bottom-right
    return (w - tw - margin, h - th - margin)


def draw_watermark(src_path, dst_path, text, font_size, color_rgba, pos_key,
                   opacity=180, box_padding=6, make_box=True):
    try:
        im = Image.open(src_path).convert('RGBA')
    except Exception as e:
        print(f"  ! failed to open {src_path}: {e}")
        return False

    txt_layer = Image.new('RGBA', im.size, (255,255,255,0))

    # 1. 用默认字体画小字
    base_font = ImageFont.load_default()
    tmp_img = Image.new("RGBA", (1000, 200), (255,255,255,0))
    tmp_draw = ImageDraw.Draw(tmp_img)
    tmp_draw.text((0,0), text, font=base_font, fill=color_rgba)

    # 2. 裁剪文字区域
    bbox = tmp_img.getbbox()
    if not bbox:
        return False
    text_img = tmp_img.crop(bbox)

    # 3. 缩放
    scale = max(1, font_size // 16)  # default font大约16px
    new_size = (max(1,int(text_img.width * scale)), max(1,int(text_img.height * scale)))
    text_img = text_img.resize(new_size, Image.LANCZOS)

    # 4. 位置计算
    x, y = compute_position(im.size, text_img.size, pos_key)

    # 可选背景框
    if make_box:
        box_color = (0,0,0, int(opacity * 0.6))
        box_coords = (x - box_padding, y - box_padding, x + text_img.width + box_padding, y + text_img.height + box_padding)
        box_layer = Image.new('RGBA', im.size, (255,255,255,0))
        box_draw = ImageDraw.Draw(box_layer)
        box_draw.rectangle(box_coords, fill=box_color)
        txt_layer = Image.alpha_composite(txt_layer, box_layer)

    # 5. 粘贴文字图
    txt_layer.paste(text_img, (x, y), text_img)

    out = Image.alpha_composite(im, txt_layer).convert('RGB')

    # ensure dst dir exists
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    try:
        out.save(dst_path)
        return True
    except Exception as e:
        print(f"  ! failed to save {dst_path}: {e}")
        return False


def interactive():
    print("\nInteractive EXIF Watermarker — vibe coding edition (scaling)\n")
    path = input("Enter an image file path or a directory (default: current dir): ").strip() or '.'
    images = find_images(path)
    if not images:
        print('No images found under the path. Exiting.')
        return
    print(f'Found {len(images)} image(s).')

    # global options
    try:
        font_size = int(input('Font size (px, scaling factor) [default 32]: ').strip() or '32')
    except Exception:
        font_size = 32
    color_in = input('Text color (hex like #ffffff or name, default white): ').strip() or '#ffffff'
    color = parse_color(color_in)

    print('\nPositions:')
    for k,v in POSITIONS.items():
        print(f'  {k}. {v}')
    pos_choice = input('Choose position number (default 5): ').strip() or '5'

    # create output root: if user gave file, use its parent; if directory, use that dir
    if os.path.isfile(path):
        root_dir = os.path.dirname(os.path.abspath(path)) or '.'
    else:
        root_dir = os.path.abspath(path)
    out_root = os.path.join(root_dir, '_watermark')
    os.makedirs(out_root, exist_ok=True)

    print(f"\nOutput directory: {out_root}\n")

    for i, img_path in enumerate(images, 1):
        print(f'[{i}/{len(images)}] {os.path.basename(img_path)}')
        date_text = get_exif_date(img_path)
        if not date_text:
            print('  No EXIF date and mtime fallback failed. Skipping.')
            continue
        # use date as watermark text
        wm_text = date_text

        dst_path = os.path.join(out_root, os.path.basename(img_path))

        ok = draw_watermark(img_path, dst_path, wm_text, font_size, color, pos_choice)
        if ok:
            print('  -> saved:', dst_path)
        else:
            print('  -> failed')

    print('\nDone. Enjoy your watermarked images!')


if __name__ == '__main__':
    try:
        interactive()
    except KeyboardInterrupt:
        print('\nInterrupted — bye!')