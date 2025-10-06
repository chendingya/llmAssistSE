# 图片水印批处理 GUI 工具

一个基于 Python + Tkinter 的图形化批处理水印工具，支持文字与图片水印、拖拽导入、自定义拖拽定位、模板保存、批量导出等功能。可用于为照片快速叠加时间戳、版权或自定义标识。

## 主要特性

| 功能 | 说明 |
|------|------|
| EXIF/文件时间读取 | 自动提取拍摄时间，失败时回退文件修改时间 |
| 文字水印 | 字体大小、颜色、可选背景框、旋转、透明度、描边、阴影 |
| 图片水印 | 外部图片、缩放百分比、旋转、透明度 |
| 位置 | 8 个预设 + 自定义拖拽（实时预览、红框提示） |
| 自定义拖拽 | 采用 span 归一化，导出与预览位置一致 |
| 批量处理 | 支持多文件 / 整个文件夹递归导入 |
| 拖拽导入 | 直接将图片或文件夹拖到缩略图区域或预览区域 |
| 模板系统 | 保存/加载/自动恢复上次参数（存储在用户家目录） |
| 重命名规则 | 保留、前缀、后缀 |
| 输出格式 | JPEG / PNG（JPEG 可调质量） |
| 尺寸调整 | 不缩放 / 指定宽 / 指定高 / 百分比 |
| 多平台 | Windows / macOS（需本地分别打包） |

## 下载 (Release)

前往 GitHub Releases 页面（最新 tag）下载：

- Windows: `WatermarkTool.exe` （双击运行）
- macOS: （若提供）`WatermarkTool.app` / 压缩包，首次运行如被拦截可“右键 -> 打开”

模板文件保存在：
- Windows: `C:\Users\<用户名>\.image_watermark_templates`
- macOS/Linux: `~/.image_watermark_templates`

## 运行（源码方式）

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python src/a.py
```

## 依赖

`Pillow`、`piexif`、`tkinter`（Python 自带）、可选：`tkinterdnd2`（拖拽增强，未安装也能运行）。

## 打包 (PyInstaller)

示例（目录版，包含资源 `_watermark`）:
```bash
pyinstaller --name WatermarkTool --noconsole --add-data "_watermark/*;_watermark" src/a.py
```
单文件：
```bash
pyinstaller --onefile --noconsole -n WatermarkTool src/a.py
```
构建产物在 `dist/` 下。

## 位置一致性说明

自定义拖拽使用 “可用空间 (图片尺寸 - 水印尺寸)” 的 span 归一化，确保预览与导出位置保持一致，即使导出时进行了缩放也能匹配当前预览逻辑（若导出时启用不同尺寸，应在预览前应用相同缩放策略以完全视觉一致）。

## 模板文件结构 (示例)
```json
{
	"text": "2025-10-06",
	"wm_type": "text",
	"font_size": 32,
	"color": "#ffffff",
	"pos": "右下",
	"custom_pos_rel": [0.35, 0.62],
	"custom_pos_span": true,
	"opacity": 0.7,
	"rotation": 0,
	"stroke_enable": 1,
	"shadow_enable": 1
}
```

## 常见问题

| 问题 | 说明 | 解决 |
|------|------|------|
| 拖拽无效 | 未安装 `tkinterdnd2` 或平台不支持 | `pip install tkinterdnd2`，否则使用按钮导入 |
| 预览位置与导出不同 | 旧模板坐标格式 | 重新拖动保存模板；新模板写入 `custom_pos_span` |
| macOS 打不开 | Gatekeeper 拦截 | 右键 -> 打开；或 `xattr -d com.apple.quarantine <App>` |
| 中文字体缺失 | 未找到系统字体 | 选择“(自动)”或安装中文字体 |

## License

见 `LICENSE`。

## 致谢

感谢 Pillow、tkinterdnd2 等开源项目。
