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
                               opacity=1.0, box_padding=6, make_box=True, resize_options=None):
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

    # 4. 位置计算
    x, y = compute_position(im.size, text_size, pos_key)

    # 可选背景框
    if make_box:
        box_color = (0,0,0, int(150 * opacity))
        box_coords = (x - box_padding, y - box_padding, x + text_size[0] + box_padding, y + text_size[1] + box_padding)
        box_draw = ImageDraw.Draw(txt_layer) # Re-draw on the actual layer
        box_draw.rectangle(box_coords, fill=box_color)

    # 5. 粘贴文字
    draw.text((x, y), text, font=font, fill=final_color)

    # 合成
    final_img = Image.alpha_composite(im, txt_layer)
    return final_img


def draw_watermark(src_path, dst_path, text, font_size, color_rgba, pos_key,
                   opacity=1.0, box_padding=6, make_box=True, output_format='JPEG',
                   jpeg_quality=95, resize_options=None):
    
    final_img = generate_watermarked_image(src_path, text, font_size, color_rgba, pos_key,
                                           opacity, box_padding, make_box, resize_options)
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


class App:
    def __init__(self, root):
        self.root = root
        root.title('本地图片水印工具')
        root.geometry('1200x750')

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
        
        # --- 控制面板 ---
        controls_frame = tk.Frame(right_pane)
        controls_frame.pack(side='bottom', fill='x')

        # --- 水印内容与样式 ---
        style_frame = tk.LabelFrame(controls_frame, text="水印内容与样式", padx=5, pady=5)
        style_frame.pack(side='top', fill='x', padx=8, pady=4)

        # 自定义文本
        tk.Label(style_frame, text="水印文本:").grid(row=0, column=0, sticky='w', pady=2)
        self.text_var = tk.StringVar(value="")
        tk.Entry(style_frame, textvariable=self.text_var, width=40).grid(row=0, column=1, padx=5, sticky='ew')
        tk.Label(style_frame, text="(留空则使用图片日期)").grid(row=0, column=2, sticky='w', padx=5)

        # 字体大小
        tk.Label(style_frame, text='字体大小:').grid(row=1, column=0, sticky='w', pady=2)
        self.font_size_var = tk.StringVar(value='32')
        tk.Entry(style_frame, width=8, textvariable=self.font_size_var).grid(row=1, column=1, padx=5, sticky='w')

        # 颜色
        tk.Label(style_frame, text='颜色:').grid(row=2, column=0, sticky='w', pady=2)
        color_frame = tk.Frame(style_frame)
        color_frame.grid(row=2, column=1, columnspan=2, sticky='ew')
        self.color_var = tk.StringVar(value='#ffffff')
        tk.Entry(color_frame, width=8, textvariable=self.color_var).pack(side='left')
        tk.Button(color_frame, text="...", width=2, command=self.on_pick_color).pack(side='left', padx=(0, 4))

        # 位置
        tk.Label(style_frame, text='位置:').grid(row=3, column=0, sticky='w', pady=2)
        self.pos_var = tk.StringVar(value='右下')
        ttk.Combobox(style_frame, textvariable=self.pos_var, values=list(POSITIONS_CN.keys()), width=12).grid(row=3, column=1, padx=5, sticky='w')

        # 背景框
        self.box_var = tk.IntVar(value=1)
        tk.Checkbutton(style_frame, text='背景框', variable=self.box_var).grid(row=3, column=1, padx=(120, 0), sticky='w')

        # 透明度
        tk.Label(style_frame, text="透明度:").grid(row=4, column=0, sticky='w', pady=2)
        self.opacity_var = tk.DoubleVar(value=0.7) # 0.0 to 1.0
        tk.Scale(style_frame, from_=0, to=1, resolution=0.05, orient='horizontal', variable=self.opacity_var).grid(row=4, column=1, columnspan=2, padx=5, sticky='ew')

        style_frame.columnconfigure(1, weight=1)

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
        self.original_preview_image = None # 存储原始预览图
        self._after_id = None

        # 绑定变量变化到预览更新
        for var in [self.text_var, self.font_size_var, self.color_var, self.pos_var, self.opacity_var, self.box_var]:
            var.trace_add('write', self.schedule_update_preview)

        # optional drag-and-drop support
        self._dnd_available = False
        try:
            from tkinterdnd2 import DND_FILES, TkinterDnD
            # if available, re-create root as TkinterDnD.Tk
            # Note: this is only beneficial if running directly; ignore if not possible.
            self._dnd_available = True
        except Exception:
            # no dnd support
            self._dnd_available = False

    def schedule_update_preview(self, *args):
        if self._after_id:
            self.root.after_cancel(self._after_id)
        self._after_id = self.root.after(200, self.update_preview) # 200ms延迟

    def update_preview(self):
        if not self.current_image_path or not self.original_preview_image:
            return

        try:
            font_size = int(self.font_size_var.get())
        except (ValueError, TypeError):
            font_size = 32
        
        color = parse_color(self.color_var.get())
        pos = POSITIONS_CN.get(self.pos_var.get(), 'bottom-right')
        make_box = bool(self.box_var.get())
        opacity = self.opacity_var.get()
        custom_text = self.text_var.get().strip()

        watermark_text = custom_text
        if not watermark_text:
            date_text = get_exif_date(self.current_image_path)
            watermark_text = date_text or "无日期"

        # 使用内存中的原始预览图生成水印，避免重复读取文件
        final_img = generate_watermarked_image(
            self.original_preview_image, watermark_text, font_size, color, pos,
            opacity=opacity, make_box=make_box, resize_options=None # 预览不应用导出尺寸
        )

        if final_img:
            photo = ImageTk.PhotoImage(final_img)
            self.preview_label.config(image=photo)
            self.preview_label.image = photo # keep ref

    def on_image_selected(self, path):
        self.current_image_path = path
        
        # 加载图片并创建适合预览区域的缩略图
        try:
            img = Image.open(path)
            
            # 为了性能，如果图片太大，先缩小到预览框大致尺寸
            preview_w = self.preview_label.winfo_width()
            preview_h = self.preview_label.winfo_height()
            if preview_w < 10 or preview_h < 10: # 窗口初次加载时可能为0
                preview_w, preview_h = 800, 600 # 默认值

            img.thumbnail((preview_w, preview_h), Image.LANCZOS)
            
            self.original_preview_image = img # 存储这个缩小的版本
            self.update_preview() # 立即更新预览
        except Exception as e:
            self.preview_label.config(image=None, text=f"无法加载图片:\n{e}")
            self.original_preview_image = None
            self.current_image_path = None

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

            ok = draw_watermark(p, dst_path, watermark_text, font_size, color, pos,
                                opacity=opacity, make_box=make_box, output_format=out_format,
                                jpeg_quality=jpeg_quality, resize_options=resize_options)
            if ok:
                succeeded += 1

        self.status.config(text=f'完成：{succeeded}/{total} 张已保存到 "{out_dir}"')
        messagebox.showinfo('完成', f'完成：{succeeded}/{total} 张已保存')


def main():
    root = tk.Tk()
    app = App(root)
    root.mainloop()


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('程序异常退出:', e)