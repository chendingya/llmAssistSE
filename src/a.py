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
POSITIONS = {
    'Top-Left': 'top-left',
    'Top-Center': 'top-center',
    'Top-Right': 'top-right',
    'Center-Left': 'center-left',
    'Center': 'center',
    'Center-Right': 'center-right',
    'Bottom-Left': 'bottom-left',
    'Bottom-Center': 'bottom-center',
    'Bottom-Right': 'bottom-right'
}

# Common EXIF tag names to IDs (reverse mapping)
TAG_NAME_TO_ID = {v: k for k, v in ExifTags.TAGS.items()}

DATE_TAGS_TO_TRY = ['DateTimeOriginal', 'DateTime', 'DateTimeDigitized']


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


def draw_watermark(src_path, dst_path, text, font_size, color_rgba, pos_key,
                   opacity=1.0, box_padding=6, make_box=True, output_format='JPEG'):
    try:
        im = Image.open(src_path).convert('RGBA')
    except Exception as e:
        print(f"  ! failed to open {src_path}: {e}")
        return False

    # 根据透明度调整颜色
    r, g, b, a = color_rgba
    final_color = (r, g, b, int(a * opacity))

    txt_layer = Image.new('RGBA', im.size, (255,255,255,0))

    # 1. 用默认字体画小字
    base_font = ImageFont.load_default()
    tmp_img = Image.new("RGBA", (1000, 200), (255,255,255,0))
    tmp_draw = ImageDraw.Draw(tmp_img)
    # 使用调整透明度后的颜色
    tmp_draw.text((0,0), text, font=base_font, fill=final_color)

    # 2. 裁剪文字区域
    bbox = tmp_img.getbbox()
    if not bbox:
        return False
    text_img = tmp_img.crop(bbox)

    # 3. 缩放
    scale = max(1, int(font_size) // 16)  # default font大约16px
    new_size = (max(1,int(text_img.width * scale)), max(1,int(text_img.height * scale)))
    text_img = text_img.resize(new_size, Image.LANCZOS)

    # 4. 位置计算
    x, y = compute_position(im.size, text_img.size, pos_key)

    # 可选背景框
    if make_box:
        # 背景框也应用透明度
        box_color = (0,0,0, int(150 * opacity)) # 150是基础不透明度
        box_coords = (x - box_padding, y - box_padding, x + text_img.width + box_padding, y + text_img.height + box_padding)
        box_layer = Image.new('RGBA', im.size, (255,255,255,0))
        box_draw = ImageDraw.Draw(box_layer)
        box_draw.rectangle(box_coords, fill=box_color)
        txt_layer = Image.alpha_composite(txt_layer, box_layer)

    # 5. 粘贴文字图
    txt_layer.paste(text_img, (x, y), text_img)

    # 合成
    final_img = Image.alpha_composite(im, txt_layer)

    # ensure dst dir exists
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    try:
        if output_format == 'JPEG':
            final_img.convert('RGB').save(dst_path, 'jpeg', quality=95)
        else: # PNG
            final_img.save(dst_path, 'png')
        return True
    except Exception as e:
        print(f"  ! failed to save {dst_path}: {e}")
        return False


class ThumbnailList(tk.Frame):
    """Scrollable list of thumbnails with filenames."""

    def __init__(self, master, thumb_size=(120, 90), *args, **kwargs):
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

    def get_all_paths(self):
        return [p for p, _, _ in self.items]


class App:
    def __init__(self, root):
        self.root = root
        root.title('本地图片水印工具')
        root.geometry('800x600')

        self.toolbar = tk.Frame(root)
        self.toolbar.pack(side='top', fill='x')

        btn_add = tk.Button(self.toolbar, text='添加图片', command=self.on_add_files)
        btn_add.pack(side='left', padx=4, pady=4)
        btn_add_folder = tk.Button(self.toolbar, text='添加文件夹', command=self.on_add_folder)
        btn_add_folder.pack(side='left', padx=4, pady=4)
        btn_clear = tk.Button(self.toolbar, text='清空列表', command=self.on_clear)
        btn_clear.pack(side='left', padx=4, pady=4)

        options = tk.Frame(self.toolbar)
        options.pack(side='right', padx=8)

        tk.Label(options, text='字体大小:').pack(side='left')
        self.font_size_var = tk.StringVar(value='32')
        tk.Entry(options, width=4, textvariable=self.font_size_var).pack(side='left', padx=(0, 4))

        tk.Label(options, text='颜色:').pack(side='left')
        self.color_var = tk.StringVar(value='#ffffff')
        tk.Entry(options, width=8, textvariable=self.color_var).pack(side='left')
        tk.Button(options, text="...", width=2, command=self.on_pick_color).pack(side='left', padx=(0, 4))

        tk.Label(options, text='位置:').pack(side='left')
        self.pos_var = tk.StringVar(value='Bottom-Right')
        ttk.Combobox(options, textvariable=self.pos_var, values=list(POSITIONS.keys()), width=12).pack(side='left', padx=(0, 4))

        self.box_var = tk.IntVar(value=1)
        tk.Checkbutton(options, text='背景框', variable=self.box_var).pack(side='left', padx=4)

        # --- 水印内容与样式 ---
        style_frame = tk.LabelFrame(root, text="水印内容与样式", padx=5, pady=5)
        style_frame.pack(side='top', fill='x', padx=8, pady=4)

        # 自定义文本
        tk.Label(style_frame, text="水印文本:").grid(row=0, column=0, sticky='w', pady=2)
        self.text_var = tk.StringVar(value="")
        tk.Entry(style_frame, textvariable=self.text_var, width=40).grid(row=0, column=1, padx=5, sticky='ew')
        tk.Label(style_frame, text="(留空则使用图片日期)").grid(row=0, column=2, sticky='w', padx=5)

        # 透明度
        tk.Label(style_frame, text="透明度:").grid(row=1, column=0, sticky='w', pady=2)
        self.opacity_var = tk.DoubleVar(value=0.7) # 0.0 to 1.0
        tk.Scale(style_frame, from_=0, to=1, resolution=0.05, orient='horizontal', variable=self.opacity_var).grid(row=1, column=1, padx=5, sticky='ew')

        style_frame.columnconfigure(1, weight=1)

        # --- 导出设置 ---
        export_frame = tk.LabelFrame(root, text="导出设置", padx=5, pady=5)
        export_frame.pack(side='bottom', fill='x', padx=8, pady=4)

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
        ttk.Combobox(format_frame, textvariable=self.format_var, values=['JPEG', 'PNG'], width=8).pack(side='left', padx=5)

        export_frame.columnconfigure(1, weight=1)

        self.thumbnail_list = ThumbnailList(root)
        self.thumbnail_list.pack(fill='both', expand=True)

        bottom = tk.Frame(root)
        bottom.pack(side='bottom', fill='x')
        self.status = tk.Label(bottom, text='就绪', anchor='w')
        self.status.pack(side='left', fill='x', expand=True, padx=6, pady=6)
        btn_apply = tk.Button(bottom, text='应用水印（批量）', command=self.on_apply)
        btn_apply.pack(side='right', padx=8, pady=6)

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

    def on_pick_color(self):
        color_code = colorchooser.askcolor(title="选择颜色")
        if color_code and color_code[1]:
            self.color_var.set(color_code[1])

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

    def on_add_folder(self):
        folder = filedialog.askdirectory(title='选择文件夹')
        if not folder:
            return
        imgs = find_images(folder)
        for p in imgs:
            self.thumbnail_list.add(p)
        self.status.config(text=f'已导入 {len(self.thumbnail_list.items)} 张图片')

    def on_clear(self):
        self.thumbnail_list.clear()
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
        pos = POSITIONS.get(self.pos_var.get(), 'bottom-right')
        make_box = bool(self.box_var.get())
        opacity = self.opacity_var.get()
        custom_text = self.text_var.get().strip()
        naming_rule = self.naming_var.get()
        prefix = self.prefix_var.get()
        suffix = self.suffix_var.get()
        out_format = self.format_var.get()

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
                                opacity=opacity, make_box=make_box, output_format=out_format)
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