#!/usr/bin/env python3
"""
GUI EXIF date watermarker

This module provides a small Tkinter-based GUI to apply date-based watermarks
to images. Features:
- Import single or multiple images via file dialog
- Import an entire folder (recursively)
- Drag-and-drop support when tkinterdnd2 is available (optional)
- Shows a scrollable list of imported images with thumbnails and filenames
- Batch apply watermark (uses EXIF date or file mtime fallback)

Dependencies: Pillow (PIL). Optional: tkinterdnd2 for drag-and-drop.
Install: pip install pillow

Save and run: python a.py
"""

from PIL import Image, ImageDraw, ImageFont, ExifTags, ImageTk
import os
import sys
import datetime
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser

# Supported image extensions
EXTS = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp', '.webp'}

# Map human-friendly positions to anchors
POSITIONS_CN = {
    '左上': 'top-left',
    '中上': 'top-center',
    '右上': 'top-right',
    '左中': 'center-left',
    '居中': 'center',
    '右中': 'center-right',
    '左下': 'bottom-left',
    '中下': 'bottom-center',
    '右下': 'bottom-right'
}

# Common EXIF tag names to IDs (reverse mapping)
TAG_NAME_TO_ID = {v: k for k, v in ExifTags.TAGS.items()}

DATE_TAGS_TO_TRY = ['DateTimeOriginal', 'DateTime', 'DateTimeDigitized']

_FONT_CACHE = {}
_SYSTEM_FONTS_CACHE = None  # list of (display_name, path)

def find_font(font_names):
    """查找系统中可用的字体文件"""
    if sys.platform == "win32":
        font_dir = "C:/Windows/Fonts"
    elif sys.platform == "darwin":
        font_dir = "/System/Library/Fonts"
    else: # linux
        font_dir = "/usr/share/fonts/truetype"

    for font_name in font_names:
        try:
            for root, _, files in os.walk(font_dir):
                for f in files:
                    if f.lower() == font_name.lower():
                        path = os.path.join(root, f)
                        if os.path.exists(path):
                            _FONT_CACHE[font_name] = path
                            return path
        except Exception:
            continue
    return None

def get_best_font(font_size):
    """获取最佳字体，优先中文字体"""
    global _FONT_CACHE
    font_prefs = ['msyh.ttc', 'msyh.ttf', 'simhei.ttf', 'dengxian.ttf', 'arial.ttf']
    
    # Check cache first
    for name in font_prefs:
        if name in _FONT_CACHE:
            return ImageFont.truetype(_FONT_CACHE[name], font_size)

    # Find and cache
    path = find_font(font_prefs)
    if path:
        return ImageFont.truetype(path, font_size)
    
    # Fallback
    return ImageFont.load_default()


def list_system_fonts(limit=300):
    """简易枚举系统字体文件，返回 (名称, 路径) 列表（去重）。"""
    global _SYSTEM_FONTS_CACHE
    if _SYSTEM_FONTS_CACHE is not None:
        return _SYSTEM_FONTS_CACHE
    font_dirs = []
    if sys.platform == 'win32':
        font_dirs.append('C:/Windows/Fonts')
    elif sys.platform == 'darwin':
        font_dirs.extend(['/System/Library/Fonts', '/Library/Fonts'])
    else:
        font_dirs.extend(['/usr/share/fonts', '/usr/local/share/fonts'])
    exts = {'.ttf', '.otf', '.ttc'}
    seen = {}
    results = []
    for d in font_dirs:
        if not os.path.isdir(d):
            continue
        try:
            for root, _, files in os.walk(d):
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in exts:
                        name = os.path.splitext(f)[0]
                        if name not in seen:
                            path = os.path.join(root, f)
                            seen[name] = path
                            results.append((name, path))
                            if len(results) >= limit:
                                raise StopIteration
        except StopIteration:
            break
        except Exception:
            continue
    _SYSTEM_FONTS_CACHE = results
    return results


def find_images(path):
    path = os.path.abspath(path)
    if os.path.isfile(path):
        if os.path.splitext(path)[1].lower() in EXTS:
            return [path]
        return []
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
    s = (s or '').strip()
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
    
    # Horizontal
    if 'left' in pos_key:
        x = margin
    elif 'right' in pos_key:
        x = w - tw - margin
    else: # center
        x = (w - tw) // 2
        
    # Vertical
    if 'top' in pos_key:
        y = margin
    elif 'bottom' in pos_key:
        y = h - th - margin
    else: # center
        y = (h - th) // 2
        
    return (x, y)


def generate_watermarked_image(src_path_or_img, text, font_size, color_rgba, pos_key,
                               opacity=1.0, box_padding=6, make_box=True, resize_options=None,
                               rotation=0, pos_override=None, return_bbox=False):
    """
    Generates a watermarked image in memory.
    Returns a PIL Image object or None on failure.
    """
    try:
        if isinstance(src_path_or_img, Image.Image):
            im = src_path_or_img.copy()
        else:
            im = Image.open(src_path_or_img)

        # 调整尺寸
        if resize_options:
            w, h = im.size
            mode = resize_options.get('mode')
            value = resize_options.get('value')
            if mode == 'width' and value and value > 0:
                new_w = value
                new_h = int(h * (new_w / w))
                im = im.resize((new_w, new_h), Image.LANCZOS)
            elif mode == 'height' and value and value > 0:
                new_h = value
                new_w = int(w * (new_h / h))
                im = im.resize((new_w, new_h), Image.LANCZOS)
            elif mode == 'percent' and value and 0 < value <= 500:
                new_w = int(w * value / 100)
                new_h = int(h * value / 100)
                im = im.resize((new_w, new_h), Image.LANCZOS)

        im = im.convert('RGBA')
    except Exception as e:
        print(f"  ! failed to open or resize: {e}")
        return None

    # 根据透明度调整颜色
    r, g, b, a = color_rgba
    final_color = (r, g, b, int(a * opacity))

    txt_layer = Image.new('RGBA', im.size, (255,255,255,0))

    # 使用 get_best_font 获取支持中文的字体
    try:
        # 允许外部设置 self.selected_font_path 通过线程安全方式传入
        if isinstance(font_size, tuple):  # 兼容未来扩展
            font_size = font_size[0]
        font_path_override = getattr(sys.modules.get(__name__), '_RUNTIME_SELECTED_FONT', None)
        if font_path_override and os.path.isfile(font_path_override):
            font = ImageFont.truetype(font_path_override, font_size)
        else:
            font = get_best_font(font_size)
    except Exception:
        font = ImageFont.load_default()

    # 直接在目标尺寸的图层上绘制文字以获取正确的bbox
    draw = ImageDraw.Draw(txt_layer)
    # Pillow 10.0.0+ has textbbox, older versions have textsize
    if hasattr(draw, 'textbbox'):
        bbox = draw.textbbox((0,0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        text_size = (text_width, text_height)
    else:
        text_size = draw.textsize(text, font=font)

    # 4. 位置计算或使用覆盖坐标
    if pos_override is not None:
        # 直接使用传入坐标
        x, y = pos_override
    else:
        x, y = compute_position(im.size, text_size, pos_key)

    # 为旋转创建单独水印层（只包含水印内容）; 支持描边/阴影：使用环境变量方式携带参数（临时简单）
    stroke_conf = getattr(sys.modules.get(__name__), '_RUNTIME_STROKE_CONF', None)
    shadow_conf = getattr(sys.modules.get(__name__), '_RUNTIME_SHADOW_CONF', None)
    wm_w = text_size[0] + (box_padding*2 if make_box else 0)
    wm_h = text_size[1] + (box_padding*2 if make_box else 0)
    watermark_layer = Image.new('RGBA', (wm_w, wm_h), (255,255,255,0))
    wdraw = ImageDraw.Draw(watermark_layer)
    if make_box:
        box_color = (0,0,0, int(150 * opacity))
        wdraw.rectangle((0,0, wm_w, wm_h), fill=box_color)
    # 阴影
    text_origin = (box_padding if make_box else 0, box_padding if make_box else 0)
    if shadow_conf and shadow_conf.get('enable'):
        sx = shadow_conf.get('dx', 2)
        sy = shadow_conf.get('dy', 2)
        scolor = shadow_conf.get('color', (0,0,0,128))
        wdraw.text((text_origin[0]+sx, text_origin[1]+sy), text, font=font, fill=scolor)
    # 描边
    if stroke_conf and stroke_conf.get('enable'):
        sw = max(1, int(stroke_conf.get('width', 1)))
        scolor = stroke_conf.get('color', (0,0,0,255))
        # 8方向描边
        for dx in range(-sw, sw+1):
            for dy in range(-sw, sw+1):
                if dx == 0 and dy == 0:
                    continue
                wdraw.text((text_origin[0]+dx, text_origin[1]+dy), text, font=font, fill=scolor)
    # 主文字
    wdraw.text(text_origin, text, font=font, fill=final_color)

    rot = (rotation or 0) % 360
    if rot != 0:
        watermark_layer = watermark_layer.rotate(rot, expand=True, resample=Image.BICUBIC)
    rot_w, rot_h = watermark_layer.size

    # 如果使用覆盖坐标，假定 x,y 是旋转后水印左上放置点
    if pos_override is None:
        # 需要重新依据旋转后尺寸调整位置（之前位置是按未旋转 text_size 算的）
        # 为简化，这里重新计算 anchor 再平移差值: 重新调用 compute_position 使用旋转后尺寸
        x, y = compute_position(im.size, (rot_w, rot_h), pos_key)
    # 边界裁剪保证在图内
    x = max(0, min(im.size[0] - rot_w, x))
    y = max(0, min(im.size[1] - rot_h, y))

    txt_layer.alpha_composite(watermark_layer, (x, y))

    final_img = Image.alpha_composite(im, txt_layer)
    if return_bbox:
        return final_img, (x, y, x + rot_w, y + rot_h)
    return final_img


def draw_watermark(src_path, dst_path, text, font_size, color_rgba, pos_key,
                   opacity=1.0, box_padding=6, make_box=True, output_format='JPEG',
                   jpeg_quality=95, resize_options=None, rotation=0, pos_override=None):

    final_img = generate_watermarked_image(src_path, text, font_size, color_rgba, pos_key,
                                           opacity, box_padding, make_box, resize_options,
                                           rotation=rotation, pos_override=pos_override)
    if not final_img:
        return False

    # ensure dst dir exists
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    try:
        if output_format == 'JPEG':
            final_img.convert('RGB').save(dst_path, 'jpeg', quality=jpeg_quality)
        else: # PNG
            final_img.save(dst_path, 'png')
        return True
    except Exception as e:
        print(f"  ! failed to save {dst_path}: {e}")
        return False


class ThumbnailList(tk.Frame):
    """Scrollable list of thumbnails with filenames.

    增加 on_select 回调：点击缩略图或其文字行时触发，传递文件路径。
    """

    def __init__(self, master, thumb_size=(120, 90), on_select=None, *args, **kwargs):
        # 我们自己处理 on_select，而不让 Tk 误认为是控件配置项
        self.on_select = on_select
        super().__init__(master, *args, **kwargs)
        self.canvas = tk.Canvas(self, borderwidth=0)
        self.frame = tk.Frame(self.canvas)
        self.vsb = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)

        self.vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.create_window((0,0), window=self.frame, anchor="nw")
        self.frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        self.items = []  # list of (path, thumbnail PhotoImage, frame)
        self.thumb_size = thumb_size
        self._selected_frame = None
        # 记录默认背景色用于取消选中
        self._default_bg = self.cget('bg')

    def clear(self):
        for _, _, fr in self.items:
            fr.destroy()
        self.items.clear()

    def add(self, path):
        # create thumbnail
        try:
            im = Image.open(path)
            im.thumbnail(self.thumb_size)
            thumb = ImageTk.PhotoImage(im)
        except Exception:
            thumb = None

        fr = tk.Frame(self.frame, bd=1, relief='solid', padx=4, pady=2)
        lbl_img = tk.Label(fr, image=thumb)
        lbl_img.image = thumb  # keep ref
        lbl_img.pack(side='left')
        lbl_text = tk.Label(fr, text=os.path.basename(path), anchor='w')
        lbl_text.pack(side='left', fill='x', expand=True, padx=6)

        fr.pack(fill='x', padx=4, pady=4)
        self.items.append((path, thumb, fr))

        # 绑定点击以触发选择
        def _on_click(event, p=path, frame=fr):
            # 取消之前的高亮
            if self._selected_frame and self._selected_frame.winfo_exists():
                try:
                    self._selected_frame.config(bg=self._default_bg)
                except Exception:
                    pass
            # 设置当前高亮
            try:
                frame.config(bg='#cce5ff')
            except Exception:
                pass
            self._selected_frame = frame
            if callable(self.on_select):
                self.on_select(p)

        for w in (fr, lbl_img, lbl_text):
            w.bind('<Button-1>', _on_click)

    def get_all_paths(self):
        return [p for p, _, _ in self.items]


class ScrollableFrame(tk.Frame):
    """简单的垂直可滚动容器，用于放置较多的控件区域。"""
    def __init__(self, master, height=360, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.canvas = tk.Canvas(self, highlightthickness=0, height=height)
        self.vbar = tk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas)
        # 记录窗口 id 以便动态调节宽度
        self._win_id = self.canvas.create_window((0, 0), window=self.inner, anchor='nw')
        self.inner.bind(
            '<Configure>',
            lambda e: (
                self.canvas.configure(scrollregion=self.canvas.bbox('all')),
                # 保持内部宽度和画布一致，避免出现内部不足宽度导致看起来“不整齐”
                self.canvas.itemconfig(self._win_id, width=self.canvas.winfo_width())
            )
        )
        # 画布尺寸改变时同步内部宽度
        self.canvas.bind(
            '<Configure>',
            lambda e: self.canvas.itemconfig(self._win_id, width=e.width)
        )
        self.canvas.configure(yscrollcommand=self.vbar.set)
        self.canvas.pack(side='left', fill='both', expand=True)
        self.vbar.pack(side='right', fill='y')

        # 鼠标滚轮支持（Windows <MouseWheel>，Linux <Button-4/5>）
        self.canvas.bind_all('<MouseWheel>', self._on_mousewheel)
        self.canvas.bind_all('<Button-4>', lambda e: self._scroll(-1))
        self.canvas.bind_all('<Button-5>', lambda e: self._scroll(1))

    def _scroll(self, delta):
        self.canvas.yview_scroll(delta, 'units')

    def _on_mousewheel(self, event):
        # Windows 正值向上，使用 -event.delta//120
        if self.canvas.winfo_height() < self.inner.winfo_height():
            self.canvas.yview_scroll(int(-event.delta/120), 'units')


class App:
    def __init__(self, root):
        self.root = root
        root.title('本地图片水印工具')
        root.geometry('1350x850')  # 增大默认窗口尺寸，给预览更多空间

        # --- 主要布局 ---
        main_pane = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True)

        # 左侧：图片列表
        list_frame = tk.Frame(main_pane)
        self.toolbar = tk.Frame(list_frame)
        self.toolbar.pack(side='top', fill='x', padx=2, pady=2)
        
        btn_add = tk.Button(self.toolbar, text='添加图片', command=self.on_add_files)
        btn_add.pack(side='left', padx=4, pady=4)
        btn_add_folder = tk.Button(self.toolbar, text='添加文件夹', command=self.on_add_folder)
        btn_add_folder.pack(side='left', padx=4, pady=4)
        btn_clear = tk.Button(self.toolbar, text='清空列表', command=self.on_clear)
        btn_clear.pack(side='left', padx=4, pady=4)

        self.thumbnail_list = ThumbnailList(list_frame, on_select=self.on_image_selected)
        self.thumbnail_list.pack(fill='both', expand=True)
        main_pane.add(list_frame, weight=1)

        # 右侧：预览和设置
        right_pane = tk.Frame(main_pane)
        main_pane.add(right_pane, weight=3)

        # --- 预览区域 ---
        preview_frame = tk.LabelFrame(right_pane, text="实时预览", padx=5, pady=5)
        preview_frame.pack(side='top', fill='both', expand=True, padx=8, pady=4)
        self.preview_label = tk.Label(preview_frame)
        self.preview_label.pack(fill='both', expand=True)
        
        # --- 控制面板（可滚动） ---
        controls_scroll = ScrollableFrame(right_pane, height=360)
        controls_scroll.pack(side='bottom', fill='x')
        controls_frame = controls_scroll.inner

        # --- 水印内容与样式 ---
        style_frame = tk.LabelFrame(controls_frame, text="水印内容与样式", padx=5, pady=5)
        style_frame.pack(side='top', fill='x', padx=8, pady=4)

        # ---- 水印类型选择 ----
        type_frame = tk.Frame(style_frame)
        type_frame.grid(row=0, column=0, columnspan=3, sticky='w')
        tk.Label(type_frame, text='类型:').pack(side='left')
        self.wm_type_var = tk.StringVar(value='text')
        tk.Radiobutton(type_frame, text='文本', variable=self.wm_type_var, value='text', command=self.on_wm_type_change).pack(side='left')
        tk.Radiobutton(type_frame, text='图片', variable=self.wm_type_var, value='image', command=self.on_wm_type_change).pack(side='left', padx=6)

        # 自定义文本
        tk.Label(style_frame, text="水印文本:").grid(row=1, column=0, sticky='w', pady=2)
        self.text_var = tk.StringVar(value="")
        self.text_entry = tk.Entry(style_frame, textvariable=self.text_var, width=40)
        self.text_entry.grid(row=1, column=1, padx=5, sticky='ew')
        tk.Label(style_frame, text="(留空则使用图片日期)").grid(row=1, column=2, sticky='w', padx=5)

        # 字体大小
        tk.Label(style_frame, text='字体大小:').grid(row=2, column=0, sticky='w', pady=2)
        self.font_size_var = tk.StringVar(value='32')
        tk.Entry(style_frame, width=8, textvariable=self.font_size_var).grid(row=2, column=1, padx=5, sticky='w')

        # 字体选择（可选）
        tk.Label(style_frame, text='字体:').grid(row=3, column=0, sticky='w', pady=2)
        self.font_family_var = tk.StringVar(value='(自动)')
        self.font_combo = ttk.Combobox(style_frame, textvariable=self.font_family_var, width=28, values=['(加载中...)'])
        self.font_combo.grid(row=3, column=1, columnspan=2, sticky='ew', padx=5)
        self.font_combo.bind('<<ComboboxSelected>>', lambda e: self.schedule_update_preview())

        # 颜色
        tk.Label(style_frame, text='颜色:').grid(row=4, column=0, sticky='w', pady=2)
        color_frame = tk.Frame(style_frame)
        color_frame.grid(row=4, column=1, columnspan=2, sticky='ew')
        self.color_var = tk.StringVar(value='#ffffff')
        tk.Entry(color_frame, width=8, textvariable=self.color_var).pack(side='left')
        tk.Button(color_frame, text="...", width=2, command=self.on_pick_color).pack(side='left', padx=(0, 4))

        # 位置（增加自定义拖拽）
        tk.Label(style_frame, text='位置:').grid(row=5, column=0, sticky='w', pady=2)
        self.pos_var = tk.StringVar(value='右下')
        pos_values = list(POSITIONS_CN.keys()) + ['自定义']
        self.pos_combo = ttk.Combobox(style_frame, textvariable=self.pos_var, values=pos_values, width=12)
        self.pos_combo.grid(row=5, column=1, padx=5, sticky='w')

        # 背景框
        self.box_var = tk.IntVar(value=1)
        tk.Checkbutton(style_frame, text='背景框', variable=self.box_var).grid(row=5, column=1, padx=(120, 0), sticky='w')

        # 透明度
        tk.Label(style_frame, text="透明度:").grid(row=6, column=0, sticky='w', pady=2)
        self.opacity_var = tk.DoubleVar(value=0.7) # 0.0 to 1.0
        tk.Scale(style_frame, from_=0, to=1, resolution=0.05, orient='horizontal', variable=self.opacity_var).grid(row=6, column=1, columnspan=2, padx=5, sticky='ew')

        # 旋转
        tk.Label(style_frame, text='旋转(°):').grid(row=7, column=0, sticky='w', pady=2)
        self.rotation_var = tk.IntVar(value=0)
        tk.Scale(style_frame, from_=0, to=359, orient='horizontal', variable=self.rotation_var, length=180).grid(row=7, column=1, columnspan=2, sticky='ew', padx=5)

        # 描边设置
        stroke_frame = tk.LabelFrame(style_frame, text='描边/阴影', padx=4, pady=4)
        stroke_frame.grid(row=8, column=0, columnspan=3, sticky='ew', pady=4)
        self.stroke_enable_var = tk.IntVar(value=0)
        tk.Checkbutton(stroke_frame, text='描边', variable=self.stroke_enable_var, command=self.schedule_update_preview).grid(row=0, column=0, sticky='w')
        tk.Label(stroke_frame, text='宽:').grid(row=0, column=1, sticky='w')
        self.stroke_width_var = tk.IntVar(value=2)
        tk.Entry(stroke_frame, textvariable=self.stroke_width_var, width=4).grid(row=0, column=2, sticky='w')
        tk.Label(stroke_frame, text='颜色:').grid(row=0, column=3, sticky='w')
        self.stroke_color_var = tk.StringVar(value='#000000')
        tk.Entry(stroke_frame, textvariable=self.stroke_color_var, width=8).grid(row=0, column=4, sticky='w')

        self.shadow_enable_var = tk.IntVar(value=0)
        tk.Checkbutton(stroke_frame, text='阴影', variable=self.shadow_enable_var, command=self.schedule_update_preview).grid(row=1, column=0, sticky='w', pady=(4,0))
        tk.Label(stroke_frame, text='dx,dy:').grid(row=1, column=1, sticky='w', pady=(4,0))
        self.shadow_dx_var = tk.IntVar(value=2)
        self.shadow_dy_var = tk.IntVar(value=2)
        tk.Entry(stroke_frame, textvariable=self.shadow_dx_var, width=4).grid(row=1, column=2, sticky='w', pady=(4,0))
        tk.Entry(stroke_frame, textvariable=self.shadow_dy_var, width=4).grid(row=1, column=3, sticky='w', pady=(4,0))
        tk.Label(stroke_frame, text='颜色:').grid(row=1, column=4, sticky='w', pady=(4,0))
        self.shadow_color_var = tk.StringVar(value='#000000')
        tk.Entry(stroke_frame, textvariable=self.shadow_color_var, width=8).grid(row=1, column=5, sticky='w', pady=(4,0))

        # 图片水印设置框
        self.image_frame = tk.LabelFrame(style_frame, text='图片水印', padx=4, pady=4)
        self.image_frame.grid(row=9, column=0, columnspan=3, sticky='ew', pady=4)
        self.image_wm_path = tk.StringVar(value='')
        tk.Button(self.image_frame, text='选择图片...', command=self.on_choose_image_wm).grid(row=0, column=0, sticky='w')
        self.image_wm_label = tk.Label(self.image_frame, text='(未选择)', anchor='w')
        self.image_wm_label.grid(row=0, column=1, sticky='w', padx=4)
        tk.Label(self.image_frame, text='缩放%:').grid(row=1, column=0, sticky='w', pady=(4,0))
        self.image_scale_var = tk.IntVar(value=100)
        tk.Scale(self.image_frame, from_=10, to=300, orient='horizontal', variable=self.image_scale_var, length=180, command=lambda e: self.schedule_update_preview()).grid(row=1, column=1, sticky='w', pady=(4,0))
        tk.Label(self.image_frame, text='透明度:').grid(row=2, column=0, sticky='w', pady=(4,0))
        self.image_opacity_var = tk.DoubleVar(value=0.8)
        tk.Scale(self.image_frame, from_=0, to=1, resolution=0.05, orient='horizontal', variable=self.image_opacity_var, length=180, command=lambda e: self.schedule_update_preview()).grid(row=2, column=1, sticky='w', pady=(4,0))
        # 初始隐藏图片框（文本模式）
        self.image_frame.grid_remove()

        style_frame.columnconfigure(1, weight=1)

        # --- 模板 / 配置管理 ---
        template_frame = tk.LabelFrame(controls_frame, text='水印模板', padx=5, pady=5)
        template_frame.pack(side='top', fill='x', padx=8, pady=4)
        tk.Label(template_frame, text='模板名称:').grid(row=0, column=0, sticky='w')
        self.template_name_var = tk.StringVar(value='默认模板')
        tk.Entry(template_frame, textvariable=self.template_name_var, width=20).grid(row=0, column=1, sticky='w', padx=4)
        tk.Button(template_frame, text='保存/更新', command=self.on_save_template).grid(row=0, column=2, padx=4)
        tk.Button(template_frame, text='删除', command=self.on_delete_template).grid(row=0, column=3, padx=4)
        tk.Label(template_frame, text='已保存:').grid(row=1, column=0, sticky='w', pady=4)
        self.template_list_var = tk.StringVar(value='')
        self.template_combo = ttk.Combobox(template_frame, textvariable=self.template_list_var, values=[], width=18)
        self.template_combo.grid(row=1, column=1, sticky='w', padx=4)
        tk.Button(template_frame, text='加载', command=self.on_load_template).grid(row=1, column=2, padx=4)
        template_frame.columnconfigure(1, weight=1)

        # --- 导出设置 ---
        export_frame = tk.LabelFrame(controls_frame, text="导出设置", padx=5, pady=5)
        export_frame.pack(side='top', fill='x', padx=8, pady=4)

        # 导出路径
        self.output_dir_var = tk.StringVar(value="")
        tk.Label(export_frame, text="输出文件夹:").grid(row=0, column=0, sticky='w', pady=2)
        tk.Entry(export_frame, textvariable=self.output_dir_var, width=50).grid(row=0, column=1, padx=5, sticky='ew')
        tk.Button(export_frame, text="浏览...", command=self.on_select_output_dir).grid(row=0, column=2)

        # 命名规则
        naming_frame = tk.Frame(export_frame)
        naming_frame.grid(row=1, column=1, sticky='w', pady=2)
        self.naming_var = tk.StringVar(value="keep")
        tk.Radiobutton(naming_frame, text="保留原名", variable=self.naming_var, value="keep").pack(side='left')
        tk.Radiobutton(naming_frame, text="前缀:", variable=self.naming_var, value="prefix").pack(side='left', padx=(10,0))
        self.prefix_var = tk.StringVar(value="wm_")
        tk.Entry(naming_frame, textvariable=self.prefix_var, width=8).pack(side='left')
        tk.Radiobutton(naming_frame, text="后缀:", variable=self.naming_var, value="suffix").pack(side='left', padx=(10,0))
        self.suffix_var = tk.StringVar(value="_wm")
        tk.Entry(naming_frame, textvariable=self.suffix_var, width=8).pack(side='left')

        # 输出格式
        format_frame = tk.Frame(export_frame)
        format_frame.grid(row=2, column=1, sticky='w', pady=2)
        self.format_var = tk.StringVar(value="JPEG")
        tk.Label(format_frame, text="输出格式:").pack(side='left')
        format_combo = ttk.Combobox(format_frame, textvariable=self.format_var, values=['JPEG', 'PNG'], width=8)
        format_combo.pack(side='left', padx=5)
        format_combo.bind("<<ComboboxSelected>>", self.on_format_change)

        # JPEG质量
        self.quality_frame = tk.Frame(format_frame)
        tk.Label(self.quality_frame, text="质量:").pack(side='left', padx=(10,0))
        self.quality_var = tk.IntVar(value=95)
        tk.Scale(self.quality_frame, from_=1, to=100, orient='horizontal', variable=self.quality_var, length=120).pack(side='left')
        self.quality_frame.pack(side='left') # 默认显示

        # 调整尺寸
        resize_frame = tk.LabelFrame(export_frame, text="调整尺寸 (可选, 应用于导出)", padx=5, pady=5)
        resize_frame.grid(row=3, column=0, columnspan=3, sticky='ew', pady=5)
        
        self.resize_mode_var = tk.StringVar(value="none")
        tk.Radiobutton(resize_frame, text="不调整", variable=self.resize_mode_var, value="none").grid(row=0, column=0)
        
        tk.Radiobutton(resize_frame, text="按宽度:", variable=self.resize_mode_var, value="width").grid(row=0, column=1)
        self.resize_width_var = tk.IntVar(value=1920)
        tk.Entry(resize_frame, textvariable=self.resize_width_var, width=6).grid(row=0, column=2)
        
        tk.Radiobutton(resize_frame, text="按高度:", variable=self.resize_mode_var, value="height").grid(row=0, column=3)
        self.resize_height_var = tk.IntVar(value=1080)
        tk.Entry(resize_frame, textvariable=self.resize_height_var, width=6).grid(row=0, column=4)

        tk.Radiobutton(resize_frame, text="按百分比:", variable=self.resize_mode_var, value="percent").grid(row=0, column=5)
        self.resize_percent_var = tk.IntVar(value=100)
        tk.Entry(resize_frame, textvariable=self.resize_percent_var, width=5).grid(row=0, column=6)
        tk.Label(resize_frame, text="%").grid(row=0, column=7)

        export_frame.columnconfigure(1, weight=1)

        # --- 底部状态栏和按钮 ---
        bottom = tk.Frame(controls_frame)
        bottom.pack(side='bottom', fill='x', padx=8, pady=4)
        self.status = tk.Label(bottom, text='就绪', anchor='w')
        self.status.pack(side='left', fill='x', expand=True, padx=6, pady=6)
        btn_apply = tk.Button(bottom, text='应用水印并导出', command=self.on_apply)
        btn_apply.pack(side='right', padx=8, pady=6)

        # --- 变量追踪和初始化 ---
        self.current_image_path = None
        self.original_preview_image = None # 当前用于预览叠加水印的基础缩放图
        self.full_image = None  # 原图（或裁剪/限制后）
        self._after_id = None
        self._preview_area_size = (0, 0)
        self._need_rescale_preview = False

        # 预览区域尺寸变化时重新缩放
        self.preview_label.bind('<Configure>', self.on_preview_resize)

        # 绑定变量变化到预览更新
        for var in [self.text_var, self.font_size_var, self.color_var, self.pos_var, self.opacity_var, self.box_var, self.rotation_var,
                    self.font_family_var, self.stroke_width_var, self.stroke_color_var, self.shadow_dx_var, self.shadow_dy_var,
                    self.shadow_color_var, self.image_scale_var, self.image_opacity_var, self.image_wm_path]:
            var.trace_add('write', self.schedule_update_preview)
        self.wm_type_var.trace_add('write', self.schedule_update_preview)
        self.stroke_enable_var.trace_add('write', self.schedule_update_preview)
        self.shadow_enable_var.trace_add('write', self.schedule_update_preview)

        # 自定义拖拽支持变量
        self.custom_pos_rel = None  # 自定义位置归一化值
        self.custom_pos_span = False  # True: 按可用空间 (W-wm_w) 归一化
        self._wm_bbox = None  # 预览中最后水印 bbox
        self.preview_label.bind('<Button-1>', self.on_preview_mouse_down)
        self.preview_label.bind('<B1-Motion>', self.on_preview_mouse_move)
        self.preview_label.bind('<ButtonRelease-1>', self.on_preview_mouse_up)
        self.preview_label.bind('<Motion>', self._update_preview_cursor)

        # 模板目录
        self.templates_dir = os.path.join(os.path.expanduser('~'), '.image_watermark_templates')
        os.makedirs(self.templates_dir, exist_ok=True)
        self.load_templates_list()
        self.load_last_settings()  # 启动时尝试加载最近一次

        # 关闭事件保存 last
        self.root.protocol('WM_DELETE_WINDOW', self.on_close)

        # 异步加载字体列表（简单直接放主线程：字体数不多时 OK）
        try:
            fonts = list_system_fonts()
            names = ['(自动)'] + [n for n, _ in fonts]
            self.font_combo['values'] = names
        except Exception:
            self.font_combo['values'] = ['(自动)']

        # 注册拖拽（如果 root 或控件支持 tkinterdnd2 接口）
        self._dnd_available = False
        if hasattr(self.root, 'drop_target_register'):
            try:
                from tkinterdnd2 import DND_FILES  # type: ignore
                targets = [self.thumbnail_list.canvas, self.preview_label]
                for w in targets:
                    try:
                        w.drop_target_register(DND_FILES)
                        w.dnd_bind('<<Drop>>', self.on_dnd_files)
                    except Exception:
                        pass
                self._dnd_available = True
                self.status.config(text='拖拽功能已启用 (可将图片或文件夹拖到左侧列表或预览)')
            except Exception:
                self._dnd_available = False

    def schedule_update_preview(self, *args):
        if self._after_id:
            self.root.after_cancel(self._after_id)
        self._after_id = self.root.after(200, self.update_preview) # 200ms延迟

    def update_preview(self):
        if not self.current_image_path or not self.original_preview_image:
            return

        # 若窗口尺寸变化导致需要重新缩放基础预览图
        if self._need_rescale_preview and self.full_image is not None:
            self.rescale_preview_base()
            self._need_rescale_preview = False

        try:
            font_size = int(self.font_size_var.get())
        except (ValueError, TypeError):
            font_size = 32
        
        color = parse_color(self.color_var.get())
        pos = POSITIONS_CN.get(self.pos_var.get(), 'bottom-right')
        make_box = bool(self.box_var.get())
        rotation = int(self.rotation_var.get()) if self.rotation_var.get() is not None else 0

        wm_type = self.wm_type_var.get()
        final_img = None
        bbox = None
        if wm_type == 'text':
            opacity = self.opacity_var.get()
            custom_text = self.text_var.get().strip()
            watermark_text = custom_text
            if not watermark_text:
                date_text = get_exif_date(self.current_image_path)
                watermark_text = date_text or "无日期"
            # 设置运行期字体路径
            global _RUNTIME_SELECTED_FONT
            _RUNTIME_SELECTED_FONT = None
            if self.font_family_var.get() not in ('', '(自动)'):
                fam = self.font_family_var.get()
                for n, p in list_system_fonts():
                    if n == fam:
                        _RUNTIME_SELECTED_FONT = p
                        break
            # Stroke & shadow runtime conf
            global _RUNTIME_STROKE_CONF, _RUNTIME_SHADOW_CONF
            _RUNTIME_STROKE_CONF = {
                'enable': bool(self.stroke_enable_var.get()),
                'width': self.stroke_width_var.get(),
                'color': parse_color(self.stroke_color_var.get())
            }
            _RUNTIME_SHADOW_CONF = {
                'enable': bool(self.shadow_enable_var.get()),
                'dx': self.shadow_dx_var.get(),
                'dy': self.shadow_dy_var.get(),
                'color': parse_color(self.shadow_color_var.get())
            }
            pos_override = None
            if self.pos_var.get() == '自定义':
                if self.custom_pos_rel is None:
                    self.custom_pos_rel = (0.5, 0.5)
                temp_img, bbox_temp = generate_watermarked_image(
                    self.original_preview_image, watermark_text, font_size, color, 'center',
                    opacity=opacity, make_box=make_box, resize_options=None, rotation=rotation,
                    pos_override=None, return_bbox=True
                )
                wm_w = bbox_temp[2] - bbox_temp[0]
                wm_h = bbox_temp[3] - bbox_temp[1]
                img_w, img_h = self.original_preview_image.size
                if self.custom_pos_span and img_w > wm_w and img_h > wm_h:
                    avail_w = max(1, img_w - wm_w)
                    avail_h = max(1, img_h - wm_h)
                    x = int(self.custom_pos_rel[0] * avail_w)
                    y = int(self.custom_pos_rel[1] * avail_h)
                else:
                    x = int(self.custom_pos_rel[0] * img_w)
                    y = int(self.custom_pos_rel[1] * img_h)
                x = max(0, min(img_w - wm_w, x))
                y = max(0, min(img_h - wm_h, y))
                pos_override = (x, y)
                final_img, bbox = generate_watermarked_image(
                    self.original_preview_image, watermark_text, font_size, color, 'center',
                    opacity=opacity, make_box=make_box, resize_options=None, rotation=rotation,
                    pos_override=pos_override, return_bbox=True
                )
            else:
                final_img, bbox = generate_watermarked_image(
                    self.original_preview_image, watermark_text, font_size, color, pos,
                    opacity=opacity, make_box=make_box, resize_options=None, rotation=rotation,
                    pos_override=None, return_bbox=True
                )
            self._wm_bbox = bbox  # 记录最新 bbox 供拖拽
        else:  # image watermark
            wmpath = self.image_wm_path.get()
            if not wmpath or not os.path.isfile(wmpath):
                return
            try:
                base = self.original_preview_image.convert('RGBA')
                wm = Image.open(wmpath).convert('RGBA')
                scale = self.image_scale_var.get() / 100.0
                if scale != 1.0:
                    new_w = max(1, int(wm.width * scale))
                    new_h = max(1, int(wm.height * scale))
                    wm = wm.resize((new_w, new_h), Image.LANCZOS)
                if rotation % 360 != 0:
                    wm = wm.rotate(rotation % 360, expand=True, resample=Image.BICUBIC)
                # opacity
                if 0 <= self.image_opacity_var.get() < 1:
                    alpha = wm.split()[-1]
                    alpha = alpha.point(lambda a: int(a * self.image_opacity_var.get()))
                    wm.putalpha(alpha)
                wm_w, wm_h = wm.size
                if self.pos_var.get() == '自定义':
                    if self.custom_pos_rel is None:
                        self.custom_pos_rel = (0.5, 0.5)
                    img_w, img_h = base.size
                    if self.custom_pos_span and img_w > wm_w and img_h > wm_h:
                        avail_w = max(1, img_w - wm_w)
                        avail_h = max(1, img_h - wm_h)
                        x = int(self.custom_pos_rel[0] * avail_w)
                        y = int(self.custom_pos_rel[1] * avail_h)
                    else:  # 兼容旧模板（按整图归一化）
                        x = int(self.custom_pos_rel[0] * img_w)
                        y = int(self.custom_pos_rel[1] * img_h)
                    x = max(0, min(img_w - wm_w, x))
                    y = max(0, min(img_h - wm_h, y))
                else:
                    x, y = compute_position(base.size, wm.size, pos)
                layer = Image.new('RGBA', base.size, (255,255,255,0))
                layer.alpha_composite(wm, (x, y))
                final_img = Image.alpha_composite(base, layer)
                bbox = (x, y, x+wm_w, y+wm_h)
                self._wm_bbox = bbox  # 记录最新 bbox 供拖拽
            except Exception as e:
                self.status.config(text=f'预览失败: {e}')
                return

        if final_img:
            if self.pos_var.get() == '自定义' and self._wm_bbox:
                try:
                    d = ImageDraw.Draw(final_img)
                    x1, y1, x2, y2 = self._wm_bbox
                    d.rectangle([x1, y1, x2-1, y2-1], outline=(255,0,0,200), width=1)
                except Exception:
                    pass
            photo = ImageTk.PhotoImage(final_img)
            self.preview_label.config(image=photo)
            self.preview_label.image = photo # keep ref

    # 鼠标进入预览区域时改变光标便于提示（仅在自定义模式下且在水印上方）
    def _update_preview_cursor(self, event):
        if not self._wm_bbox or self.pos_var.get() != '自定义':
            self.preview_label.config(cursor='')
            return
        x1, y1, x2, y2 = self._wm_bbox
        if x1 <= event.x <= x2 and y1 <= event.y <= y2:
            self.preview_label.config(cursor='fleur')
        else:
            self.preview_label.config(cursor='')

    def on_image_selected(self, path):
        self.current_image_path = path
        try:
            with Image.open(path) as im:
                # 可考虑限制超大图片，避免内存占用过多
                MAX_DIM = 5000
                w, h = im.size
                if max(w, h) > MAX_DIM:
                    scale = MAX_DIM / max(w, h)
                    im = im.resize((int(w*scale), int(h*scale)), Image.LANCZOS)
                self.full_image = im.copy()
            # 根据当前预览区域尺寸生成基础缩放图
            self.rescale_preview_base()
            self.update_preview()
        except Exception as e:
            self.preview_label.config(image=None, text=f"无法加载图片:\n{e}")
            self.original_preview_image = None
            self.full_image = None
            self.current_image_path = None

    def on_preview_resize(self, event):
        # 记录新的大小，若变化显著则标记需要重新缩放
        new_size = (event.width, event.height)
        if new_size[0] <= 5 or new_size[1] <= 5:
            return
        old_w, old_h = self._preview_area_size
        self._preview_area_size = new_size
        # 如果面积变化超过 5% 认为需要刷新缩放
        if old_w == 0 or old_h == 0:
            self._need_rescale_preview = True
        else:
            area_old = old_w * old_h
            area_new = new_size[0] * new_size[1]
            if area_new > 0 and abs(area_new - area_old)/area_old > 0.05:
                self._need_rescale_preview = True
        if self._need_rescale_preview:
            self.schedule_update_preview()

    def rescale_preview_base(self):
        if self.full_image is None:
            return
        area_w, area_h = self._preview_area_size
        if area_w < 20 or area_h < 20:
            area_w, area_h = 1000, 700  # 初始默认
        # 预留少许边距
        max_w = max(50, area_w - 16)
        max_h = max(50, area_h - 16)
        img = self.full_image.copy()
        img.thumbnail((max_w, max_h), Image.LANCZOS)
        self.original_preview_image = img

    def on_pick_color(self):
        color_code = colorchooser.askcolor(title="选择颜色")
        if color_code and color_code[1]:
            self.color_var.set(color_code[1])

    def on_format_change(self, event=None):
        """根据所选格式显示/隐藏JPEG质量滑块"""
        if self.format_var.get() == 'JPEG':
            self.quality_frame.pack(side='left')
        else:
            self.quality_frame.pack_forget()

    def on_select_output_dir(self):
        folder = filedialog.askdirectory(title='选择输出文件夹')
        if folder:
            self.output_dir_var.set(folder)

    def on_add_files(self):
        paths = filedialog.askopenfilenames(title='选择图片', filetypes=[('Images','*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp')])
        for p in paths:
            if os.path.splitext(p)[1].lower() in EXTS:
                self.thumbnail_list.add(p)
        self.status.config(text=f'已导入 {len(self.thumbnail_list.items)} 张图片')
        if paths and not self.current_image_path:
            self.on_image_selected(paths[0])

    def on_add_folder(self):
        folder = filedialog.askdirectory(title='选择文件夹')
        if not folder:
            return
        imgs = find_images(folder)
        for p in imgs:
            self.thumbnail_list.add(p)
        self.status.config(text=f'已导入 {len(self.thumbnail_list.items)} 张图片')
        if imgs and not self.current_image_path:
            self.on_image_selected(imgs[0])

    def on_clear(self):
        self.thumbnail_list.clear()
        self.preview_label.config(image=None, text="")
        self.original_preview_image = None
        self.current_image_path = None
        self.status.config(text='就绪')

    def on_apply(self):
        paths = self.thumbnail_list.get_all_paths()
        if not paths:
            messagebox.showinfo('提示', '请先导入图片')
            return

        out_dir = self.output_dir_var.get()
        if not out_dir:
            messagebox.showerror('错误', '请先指定一个输出文件夹。')
            return

        # 安全检查：禁止输出到任何源文件所在的目录
        src_dirs = {os.path.dirname(p) for p in paths}
        if os.path.abspath(out_dir) in {os.path.abspath(d) for d in src_dirs}:
            messagebox.showerror('错误', '为防止覆盖原文件，不能将文件导出到源文件夹。请选择其他文件夹。')
            return

        try:
            font_size = int(self.font_size_var.get())
        except Exception:
            font_size = 32
        color = parse_color(self.color_var.get())
        pos = POSITIONS_CN.get(self.pos_var.get(), 'bottom-right')
        make_box = bool(self.box_var.get())
        opacity = self.opacity_var.get()
        custom_text = self.text_var.get().strip()
        naming_rule = self.naming_var.get()
        prefix = self.prefix_var.get()
        suffix = self.suffix_var.get()
        out_format = self.format_var.get()
        jpeg_quality = self.quality_var.get()
        rotation = int(self.rotation_var.get()) if self.rotation_var.get() is not None else 0
        wm_type = self.wm_type_var.get()
        # 文字相关 runtime conf（导出时设置全局以复用函数）
        global _RUNTIME_SELECTED_FONT, _RUNTIME_STROKE_CONF, _RUNTIME_SHADOW_CONF
        if wm_type == 'text':
            _RUNTIME_SELECTED_FONT = None
            if self.font_family_var.get() not in ('', '(自动)'):
                fam = self.font_family_var.get()
                for n, p in list_system_fonts():
                    if n == fam:
                        _RUNTIME_SELECTED_FONT = p
                        break
            _RUNTIME_STROKE_CONF = {
                'enable': bool(self.stroke_enable_var.get()),
                'width': self.stroke_width_var.get(),
                'color': parse_color(self.stroke_color_var.get())
            }
            _RUNTIME_SHADOW_CONF = {
                'enable': bool(self.shadow_enable_var.get()),
                'dx': self.shadow_dx_var.get(),
                'dy': self.shadow_dy_var.get(),
                'color': parse_color(self.shadow_color_var.get())
            }
        else:
            _RUNTIME_SELECTED_FONT = None
            _RUNTIME_STROKE_CONF = None
            _RUNTIME_SHADOW_CONF = None

        # 调整尺寸选项
        resize_options = None
        resize_mode = self.resize_mode_var.get()
        if resize_mode != 'none':
            resize_options = {'mode': resize_mode}
            if resize_mode == 'width':
                resize_options['value'] = self.resize_width_var.get()
            elif resize_mode == 'height':
                resize_options['value'] = self.resize_height_var.get()
            elif resize_mode == 'percent':
                resize_options['value'] = self.resize_percent_var.get()

        total = len(paths)
        self.status.config(text=f'开始处理 {total} 张图片...')
        self.root.update_idletasks()

        succeeded = 0
        for i, p in enumerate(paths, 1):
            self.status.config(text=f'[{i}/{total}] 处理: {os.path.basename(p)}')
            self.root.update_idletasks()

            watermark_text = custom_text
            if not watermark_text:
                date_text = get_exif_date(p)
                if not date_text:
                    # skip if can't determine date
                    self.status.config(text=f'[{i}/{total}] 跳过（无日期）: {os.path.basename(p)}')
                    continue
                watermark_text = date_text

            # 根据命名规则生成新文件名
            base_name = os.path.basename(p)
            name, ext = os.path.splitext(base_name)
            if naming_rule == 'prefix':
                new_name = f"{prefix}{name}"
            elif naming_rule == 'suffix':
                new_name = f"{name}{suffix}"
            else: # keep
                new_name = name

            # 设置输出格式对应的扩展名
            new_ext = '.jpg' if out_format == 'JPEG' else '.png'
            dst_path = os.path.join(out_dir, f"{new_name}{new_ext}")

            os.makedirs(out_dir, exist_ok=True)

            pos_override = None
            if self.pos_var.get() == '自定义' and self.custom_pos_rel is not None:
                # 将自定义位置应用到当前图片，使用 span 归一化避免预览/导出差异
                try:
                    with Image.open(p) as im_for_size:
                        iw, ih = im_for_size.size
                        # 生成一次水印尺寸用于计算可用空间
                        tmp_img, tmp_bbox = generate_watermarked_image(
                            p, watermark_text, font_size, color, 'center', opacity=opacity,
                            make_box=make_box, resize_options=None, rotation=rotation,
                            pos_override=None, return_bbox=True
                        )
                        wm_w = tmp_bbox[2] - tmp_bbox[0]
                        wm_h = tmp_bbox[3] - tmp_bbox[1]
                        if self.custom_pos_span:
                            avail_w = max(1, iw - wm_w)
                            avail_h = max(1, ih - wm_h)
                            x = int(self.custom_pos_rel[0] * avail_w)
                            y = int(self.custom_pos_rel[1] * avail_h)
                        else:  # 兼容旧模板
                            x = int(self.custom_pos_rel[0] * iw)
                            y = int(self.custom_pos_rel[1] * ih)
                        x = max(0, min(iw - wm_w, x))
                        y = max(0, min(ih - wm_h, y))
                        pos_override = (x, y)
                except Exception:
                    pos_override = None

            if wm_type == 'text':
                ok = draw_watermark(p, dst_path, watermark_text, font_size, color, pos,
                                    opacity=opacity, make_box=make_box, output_format=out_format,
                                    jpeg_quality=jpeg_quality, resize_options=resize_options,
                                    rotation=rotation, pos_override=pos_override)
            else:
                # 图片水印处理
                ok = self.export_image_watermark(p, dst_path, pos, rotation, pos_override, out_format,
                                                 jpeg_quality, resize_options)
            if ok:
                succeeded += 1

        self.status.config(text=f'完成：{succeeded}/{total} 张已保存到 "{out_dir}"')
        messagebox.showinfo('完成', f'完成：{succeeded}/{total} 张已保存')

    # ---------- 预览拖拽事件 ----------
    def on_preview_mouse_down(self, event):
        if not self._wm_bbox:
            return
        x1, y1, x2, y2 = self._wm_bbox
        inside = x1 <= event.x <= x2 and y1 <= event.y <= y2
        if inside and self.pos_var.get() != '自定义':
            try:
                img_w, img_h = self.original_preview_image.size
                w = x2 - x1
                h = y2 - y1
                avail_w = max(1, img_w - w)
                avail_h = max(1, img_h - h)
                self.custom_pos_rel = (x1 / avail_w if avail_w else 0.0,
                                       y1 / avail_h if avail_h else 0.0)
                self.custom_pos_span = True
                self.pos_var.set('自定义')
            except Exception:
                pass
            self.update_preview()
        if inside and self.pos_var.get() == '自定义':
            self._dragging = True
            self._drag_offset = (event.x - x1, event.y - y1)
        else:
            self._dragging = False

    def on_preview_mouse_move(self, event):
        if getattr(self, '_dragging', False) and self.original_preview_image is not None:
            img_w, img_h = self.original_preview_image.size
            x = event.x - self._drag_offset[0]
            y = event.y - self._drag_offset[1]
            # 边界限制（需要当前水印宽高）
            if self._wm_bbox:
                w = self._wm_bbox[2] - self._wm_bbox[0]
                h = self._wm_bbox[3] - self._wm_bbox[1]
                x = max(0, min(img_w - w, x))
                y = max(0, min(img_h - h, y))
            # 保存归一化位置（按可用空间）
            avail_w = max(1, img_w - w)
            avail_h = max(1, img_h - h)
            self.custom_pos_rel = (x / avail_w if avail_w else 0.0, y / avail_h if avail_h else 0.0)
            self.custom_pos_span = True
            self.update_preview()

    def on_preview_mouse_up(self, event):
        if getattr(self, '_dragging', False):
            self._dragging = False

    # ---------- 模板功能 ----------
    def get_current_settings(self):
        return {
            'text': self.text_var.get(),
            'wm_type': self.wm_type_var.get(),
            'font_size': self.font_size_var.get(),
            'font_family': self.font_family_var.get(),
            'color': self.color_var.get(),
            'pos': self.pos_var.get(),
            'box': self.box_var.get(),
            'opacity': self.opacity_var.get(),
            'naming': self.naming_var.get(),
            'prefix': self.prefix_var.get(),
            'suffix': self.suffix_var.get(),
            'format': self.format_var.get(),
            'quality': self.quality_var.get(),
            'resize_mode': self.resize_mode_var.get(),
            'resize_width': self.resize_width_var.get(),
            'resize_height': self.resize_height_var.get(),
            'resize_percent': self.resize_percent_var.get(),
            'rotation': self.rotation_var.get(),
            'custom_pos_rel': self.custom_pos_rel,
            'custom_pos_span': self.custom_pos_span,
            'stroke_enable': self.stroke_enable_var.get(),
            'stroke_width': self.stroke_width_var.get(),
            'stroke_color': self.stroke_color_var.get(),
            'shadow_enable': self.shadow_enable_var.get(),
            'shadow_dx': self.shadow_dx_var.get(),
            'shadow_dy': self.shadow_dy_var.get(),
            'shadow_color': self.shadow_color_var.get(),
            'image_wm_path': self.image_wm_path.get(),
            'image_scale': self.image_scale_var.get(),
            'image_opacity': self.image_opacity_var.get(),
        }

    def apply_settings(self, data):
        try:
            self.text_var.set(data.get('text', ''))
            self.wm_type_var.set(data.get('wm_type', 'text'))
            self.font_size_var.set(data.get('font_size', '32'))
            self.font_family_var.set(data.get('font_family', '(自动)'))
            self.color_var.set(data.get('color', '#ffffff'))
            self.pos_var.set(data.get('pos', '右下'))
            self.box_var.set(int(data.get('box', 1)))
            self.opacity_var.set(float(data.get('opacity', 0.7)))
            self.naming_var.set(data.get('naming', 'keep'))
            self.prefix_var.set(data.get('prefix', 'wm_'))
            self.suffix_var.set(data.get('suffix', '_wm'))
            self.format_var.set(data.get('format', 'JPEG'))
            self.quality_var.set(int(data.get('quality', 95)))
            self.resize_mode_var.set(data.get('resize_mode', 'none'))
            self.resize_width_var.set(int(data.get('resize_width', 1920)))
            self.resize_height_var.set(int(data.get('resize_height', 1080)))
            self.resize_percent_var.set(int(data.get('resize_percent', 100)))
            self.rotation_var.set(int(data.get('rotation', 0)))
            self.custom_pos_rel = data.get('custom_pos_rel')
            self.custom_pos_span = bool(data.get('custom_pos_span', False))
            # 如果旧模板存在自定义位置但没有 span 标记，进行一次转换尝试
            if self.custom_pos_rel and not data.get('custom_pos_span', False):
                try:
                    # 需要当前预览图与一次水印尺寸估计
                    if self.original_preview_image is not None:
                        wm_type = data.get('wm_type', 'text')
                        rotation = int(data.get('rotation', 0))
                        if wm_type == 'text':
                            # 估算文字水印尺寸
                            font_size = int(data.get('font_size', 32))
                            color = parse_color(data.get('color', '#ffffff'))
                            tmp_text = data.get('text') or '示例'
                            temp_img, bbox_temp = generate_watermarked_image(
                                self.original_preview_image, tmp_text, font_size, color, 'center',
                                opacity=float(data.get('opacity', 0.7)), make_box=bool(data.get('box',1)),
                                resize_options=None, rotation=rotation, pos_override=None, return_bbox=True
                            )
                            wm_w = bbox_temp[2]-bbox_temp[0]
                            wm_h = bbox_temp[3]-bbox_temp[1]
                        else:
                            # 图片水印尺寸
                            wmpath = data.get('image_wm_path','')
                            if wmpath and os.path.isfile(wmpath):
                                wm = Image.open(wmpath).convert('RGBA')
                                scale = int(data.get('image_scale',100))/100.0
                                if scale!=1.0:
                                    wm = wm.resize((max(1,int(wm.width*scale)), max(1,int(wm.height*scale))), Image.LANCZOS)
                                if rotation % 360 != 0:
                                    wm = wm.rotate(rotation%360, expand=True, resample=Image.BICUBIC)
                                wm_w, wm_h = wm.size
                            else:
                                wm_w = wm_h = 50  # fallback
                        img_w, img_h = self.original_preview_image.size
                        # 旧的 custom_pos_rel 假设为 (x/img_w, y/img_h)
                        old_x = self.custom_pos_rel[0] * img_w
                        old_y = self.custom_pos_rel[1] * img_h
                        avail_w = max(1, img_w - wm_w)
                        avail_h = max(1, img_h - wm_h)
                        if avail_w>0 and avail_h>0:
                            span_x = min(1.0, max(0.0, old_x / avail_w))
                            span_y = min(1.0, max(0.0, old_y / avail_h))
                            self.custom_pos_rel = (span_x, span_y)
                            self.custom_pos_span = True
                except Exception:
                    pass
            self.stroke_enable_var.set(int(data.get('stroke_enable', 0)))
            self.stroke_width_var.set(int(data.get('stroke_width', 2)))
            self.stroke_color_var.set(data.get('stroke_color', '#000000'))
            self.shadow_enable_var.set(int(data.get('shadow_enable', 0)))
            self.shadow_dx_var.set(int(data.get('shadow_dx', 2)))
            self.shadow_dy_var.set(int(data.get('shadow_dy', 2)))
            self.shadow_color_var.set(data.get('shadow_color', '#000000'))
            self.image_wm_path.set(data.get('image_wm_path', ''))
            self.image_scale_var.set(int(data.get('image_scale', 100)))
            self.image_opacity_var.set(float(data.get('image_opacity', 0.8)))
            self.update_preview()
            self.on_wm_type_change()
        except Exception as e:
            messagebox.showerror('错误', f'应用模板失败: {e}')

    def template_path(self, name):
        safe = name.replace('/', '_').replace('\\', '_')
        return os.path.join(self.templates_dir, f'{safe}.json')

    def on_save_template(self):
        name = self.template_name_var.get().strip() or '未命名'
        path = self.template_path(name)
        data = self.get_current_settings()
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.load_templates_list()
            self.template_list_var.set(name)
            messagebox.showinfo('成功', f'模板 "{name}" 已保存')
        except Exception as e:
            messagebox.showerror('错误', f'保存模板失败: {e}')

    def on_load_template(self):
        name = self.template_list_var.get().strip()
        if not name:
            return
        path = self.template_path(name)
        if not os.path.exists(path):
            messagebox.showerror('错误', '模板不存在')
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.apply_settings(data)
        except Exception as e:
            messagebox.showerror('错误', f'加载模板失败: {e}')

    def on_delete_template(self):
        name = self.template_list_var.get().strip()
        if not name:
            return
        path = self.template_path(name)
        if os.path.exists(path):
            try:
                os.remove(path)
                self.load_templates_list()
                self.template_list_var.set('')
                messagebox.showinfo('删除', f'模板 "{name}" 已删除')
            except Exception as e:
                messagebox.showerror('错误', f'删除失败: {e}')

    def load_templates_list(self):
        try:
            files = [f[:-5] for f in os.listdir(self.templates_dir) if f.endswith('.json') and f != 'last.json']
            self.template_combo['values'] = files
        except Exception:
            self.template_combo['values'] = []

    def save_last_settings(self):
        path = os.path.join(self.templates_dir, 'last.json')
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.get_current_settings(), f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def load_last_settings(self):
        path = os.path.join(self.templates_dir, 'last.json')
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.apply_settings(data)
            except Exception:
                pass

    def on_close(self):
        self.save_last_settings()
        self.root.destroy()

    # -------- 新增功能：水印类型切换 --------
    def on_wm_type_change(self):
        if self.wm_type_var.get() == 'image':
            self.image_frame.grid()
            self.text_entry.configure(state='disabled')
        else:
            self.image_frame.grid_remove()
            self.text_entry.configure(state='normal')
        self.schedule_update_preview()

    def on_choose_image_wm(self):
        path = filedialog.askopenfilename(title='选择图片水印', filetypes=[('Images','*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp')])
        if path:
            self.image_wm_path.set(path)
            self.image_wm_label.config(text=os.path.basename(path))

    def export_image_watermark(self, src_path, dst_path, pos_key, rotation, pos_override, out_format, jpeg_quality, resize_options):
        try:
            with Image.open(src_path) as base:
                if resize_options:
                    w, h = base.size
                    mode = resize_options.get('mode')
                    value = resize_options.get('value')
                    if mode == 'width' and value and value > 0:
                        new_w = value
                        new_h = int(h * (new_w / w))
                        base = base.resize((new_w, new_h), Image.LANCZOS)
                    elif mode == 'height' and value and value > 0:
                        new_h = value
                        new_w = int(w * (new_h / h))
                        base = base.resize((new_w, new_h), Image.LANCZOS)
                    elif mode == 'percent' and value and 0 < value <= 500:
                        new_w = int(w * value / 100)
                        new_h = int(h * value / 100)
                        base = base.resize((new_w, new_h), Image.LANCZOS)
                base = base.convert('RGBA')
                wmpath = self.image_wm_path.get()
                if not wmpath or not os.path.isfile(wmpath):
                    return False
                wm = Image.open(wmpath).convert('RGBA')
                scale = self.image_scale_var.get() / 100.0
                if scale != 1.0:
                    new_w = max(1, int(wm.width * scale))
                    new_h = max(1, int(wm.height * scale))
                    wm = wm.resize((new_w, new_h), Image.LANCZOS)
                if rotation % 360 != 0:
                    wm = wm.rotate(rotation % 360, expand=True, resample=Image.BICUBIC)
                if 0 <= self.image_opacity_var.get() < 1:
                    alpha = wm.split()[-1]
                    alpha = alpha.point(lambda a: int(a * self.image_opacity_var.get()))
                    wm.putalpha(alpha)
                wm_w, wm_h = wm.size
                if pos_override is not None:
                    x, y = pos_override
                else:
                    x, y = compute_position(base.size, (wm_w, wm_h), pos_key)
                layer = Image.new('RGBA', base.size, (255,255,255,0))
                layer.alpha_composite(wm, (x, y))
                final_img = Image.alpha_composite(base, layer)
                os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                if out_format == 'JPEG':
                    final_img.convert('RGB').save(dst_path, 'jpeg', quality=jpeg_quality)
                else:
                    final_img.save(dst_path, 'png')
                return True
        except Exception as e:
            print('图片水印导出失败:', e)
        return False

    # -------- 拖拽回调 (文件/目录) --------
    def on_dnd_files(self, event):
        data = event.data
        # Windows 可能包含大括号包裹路径，多个文件以空格分隔；带空格路径会用{}包裹
        paths = []
        cur = ''
        in_brace = False
        for ch in data:
            if ch == '{':
                in_brace = True
                if cur:
                    paths.append(cur)
                    cur = ''
                continue
            if ch == '}':
                in_brace = False
                if cur:
                    paths.append(cur)
                    cur = ''
                continue
            if ch == ' ' and not in_brace:
                if cur:
                    paths.append(cur)
                    cur = ''
            else:
                cur += ch
        if cur:
            paths.append(cur)
        added = 0
        for p in paths:
            if os.path.isdir(p):
                for img in find_images(p):
                    self.thumbnail_list.add(img)
                    added += 1
            elif os.path.isfile(p) and os.path.splitext(p)[1].lower() in EXTS:
                self.thumbnail_list.add(p)
                added += 1
        if added:
            self.status.config(text=f'拖拽导入 {added} 个文件')
            if not self.current_image_path and self.thumbnail_list.items:
                self.on_image_selected(self.thumbnail_list.items[0][0])


def main():
    # 优先使用 TkinterDnD 的 Tk 以支持拖拽
    try:
        from tkinterdnd2 import TkinterDnD  # type: ignore
        root = TkinterDnD.Tk()
    except Exception:
        root = tk.Tk()
    app = App(root)
    root.mainloop()


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('程序异常退出:', e)