#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_preview.py — 按真实布局常量渲染界面效果图

═══════════════════════════════════════════════════════════════════════════
这不是"示意图"，而是按代码里的实际常量与文案算出来的预览
═══════════════════════════════════════════════════════════════════════════
数值全部取自 overlay/src/layout.hpp（真机实测得来）:
    VISIBLE_HEIGHT    = 557   List 裁剪矩形高度
    ITEM_HEIGHT       = 70    ListItem 高
    HEADER_HEIGHT     = 33    CategoryHeader 高
    FIRST_ITEM_OFFSET = 33    首项前偏移

字号取自 tesla.hpp:
    标题栏 32 / 副标题 27 / 列表项名字 23 / 列表项取值 20

文案取自:
    gui.cpp（界面文字）/ presets.hpp（30 个预设）

⚠ 局限（必须说清）:
    · 真机的字体是主机系统共享字体，形状与微软雅黑不同，
      这里只是**版式与文字**的等价预览，不是像素级还原
    · 绘制细节（圆角、透明度、配色）按 libultrahand 的 Tesla 主题近似
    · 精确的字形宽度只有真机能给（stb_truetype + 系统字体）

用法:
    render_preview.py [输出目录]
"""

import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "overlay" / "src"

# ── 真实布局常量（与 layout.hpp 一致）──
VISIBLE_HEIGHT = 557
ITEM_HEIGHT = 70
HEADER_HEIGHT = 33
FIRST_ITEM_OFFSET = 33

# List 的实际裁剪矩形（tesla.hpp List::draw）:
#     enableScissoring(0, 88, FramebufferWidth, FramebufferHeight - 73 - 97 + 2 + 5)
# 720 下即 y ∈ [88, 645]。列表内容起点是 97，但**裁剪从 88 开始**，
# 所以"真正可见"的下边界是 645，而不是 97+557=654。
#
# 预览必须按真实裁剪值画，否则会画出真机上看不到的内容 ——
# 第一版预览就因此把页脚画到了列表项上面，看起来像布局冲突。
SCISSOR_TOP = 88
SCISSOR_BOTTOM = 720 - 73 - 97 + 2 + 5      # = 645

# ── 面板尺寸 ──
# nx-ovlloader 的 overlay 是 448x720（correctFrameSize 判定的"正确尺寸"）
PANEL_W = 448
PANEL_H = 720
SCALE = 2                      # 2 倍超采样，输出更清晰

# ── 配色（近似 Tesla 默认主题）──
COL_BG        = (14, 16, 22, 235)
COL_FRAME     = (120, 125, 135)
COL_TEXT      = (245, 245, 245)
COL_VALUE     = (225, 228, 232)
COL_HEADER    = (150, 200, 255)
COL_SEP       = (70, 76, 88)
COL_SEL_BG    = (0, 240, 210, 60)
COL_SEL_FRAME = (0, 240, 210)
COL_FOOTER    = (170, 178, 190)

# ── 字号（tesla.hpp 的实际取值）──
FS_TITLE = 32
FS_SUBTITLE = 27
FS_ITEM = 23
FS_VALUE = 20
FS_HEADER = 20
FS_FOOTER = 20

FONT_REG = "C:/Windows/Fonts/msyh.ttc"
FONT_BOLD = "C:/Windows/Fonts/msyhbd.ttc"


def font(bold, size):
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REG, size * SCALE)


# ── 从源码里取文案 ──

def read(path):
    return (SRC / path).read_text(encoding="utf-8")


def extract_presets():
    """从 presets.hpp 抽出 (名字, 说明, 分组) 列表，保持顺序"""
    t = read("presets.hpp")
    groups = {g: name for name, g in re.findall(
        r'case PresetGroup::(\w+):\s*return "([^"]+)"', t)}
    i = t.find("std::array<Preset,")
    j = t.find("}};", i)
    body = t[i:j]
    out = []
    for m in re.finditer(
            r'\{\s*"([^"]*)"\s*,\s*"([^"]*)"\s*,\s*"([^"]*)"\s*,\s*PresetGroup::(\w+)',
            body):
        out.append((m.group(2), m.group(3), m.group(4)))
    return out, groups


def version():
    t = read("version.hpp")
    m = re.search(r'^#define\s+FNX_VERSION\s+"([^"]+)"', t, re.M)
    return "v" + m.group(1)


def overlay_frame(title_fragment, subtitle_hint=None):
    """从 gui.cpp 里取出某个 OverlayFrame 的标题与副标题。

    ⚠ 两个坑（都踩过）:
      1. 不要硬编码文案 —— 预览脚本曾写死"关于"，源码改成"关于本插件"
         后图没跟着变，预览与真机不一致。
      2. 同名框架有两个 —— MainGui 里有
             OverlayFrame("超能滤镜", " · 未连接")      ← 服务不可用时的引导页
             OverlayFrame("超能滤镜", " · 按下即生效")  ← 正常主页面
         只按标题匹配会取到第一个（未连接那个）。
         所以用 subtitle_hint 区分。
    """
    t = read("gui.cpp")
    for m in re.finditer(
            r'OverlayFrame\("([^"]*)"\s*,\s*FNX_VERSION_LABEL\s*"([^"]*)"\)', t):
        title, sub = m.group(1), m.group(2)
        if title_fragment not in title:
            continue
        if subtitle_hint and subtitle_hint not in sub:
            continue
        return title, f"{version()} · {sub.lstrip(' ·')}"
    return title_fragment, version()


def author_name():
    """从 gui.cpp 里取出作者名（"作者", "xxx" 那一行）"""
    t = read("gui.cpp")
    m = re.search(r'ListItem\("作者"\s*,\s*"([^"]+)"\)', t)
    return m.group(1) if m else "?"


# ── 绘制 ──

def new_page():
    """返回 (整页图, 背景画笔, 列表层图, 列表层画笔)

    列表内容单独画在一层上，之后按真实裁剪矩形裁掉，
    再叠到背景上 —— 这样预览不会显示真机看不到的内容。
    """
    img = Image.new("RGBA", (PANEL_W * SCALE, PANEL_H * SCALE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    d.rounded_rectangle([0, 0, PANEL_W * SCALE - 1, PANEL_H * SCALE - 1],
                        radius=0, fill=COL_BG)

    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    dl = ImageDraw.Draw(layer, "RGBA")
    return img, d, layer, dl


def compose(img, d, layer):
    """把列表层按真实裁剪矩形裁好后叠到背景上，再画页脚"""
    top = SCISSOR_TOP * SCALE
    bottom = SCISSOR_BOTTOM * SCALE
    clipped = Image.new("RGBA", img.size, (0, 0, 0, 0))
    clipped.paste(layer.crop((0, top, img.size[0], bottom)), (0, top))
    img.alpha_composite(clipped)
    draw_footer(d)
    return img


def draw_title(d, title, subtitle):
    d.text((20 * SCALE, 20 * SCALE), title, font=font(True, FS_TITLE), fill=COL_TEXT)
    d.text((20 * SCALE, 58 * SCALE), subtitle, font=font(False, FS_SUBTITLE),
           fill=COL_FOOTER)
    # 标题区下方的分隔条
    d.line([(10 * SCALE, 96 * SCALE), ((PANEL_W - 10) * SCALE, 96 * SCALE)],
           fill=COL_SEP, width=1 * SCALE)


def draw_header(d, y, text):
    """CategoryHeader: 高度 33，左侧有竖条"""
    d.rectangle([10 * SCALE, (y + 8) * SCALE, 13 * SCALE, (y + 26) * SCALE],
                fill=COL_HEADER)
    d.text((24 * SCALE, (y + 5) * SCALE), text, font=font(False, FS_HEADER),
           fill=COL_HEADER)
    return y + HEADER_HEIGHT


def draw_item(d, y, name, value, selected=False):
    """ListItem: 高度 70；名字字号 23 起点 x=19，取值字号 20 右对齐"""
    if selected:
        d.rounded_rectangle(
            [8 * SCALE, (y + 3) * SCALE, (PANEL_W - 12) * SCALE, (y + ITEM_HEIGHT - 6) * SCALE],
            radius=8 * SCALE, fill=COL_SEL_BG,
            outline=COL_SEL_FRAME, width=2 * SCALE)

    d.text((19 * SCALE, (y + 21) * SCALE), name, font=font(False, FS_ITEM),
           fill=COL_TEXT)

    if value:
        f = font(False, FS_VALUE)
        w = d.textlength(value, font=f)
        d.text(((PANEL_W - 26) * SCALE - w, (y + 25) * SCALE), value, font=f,
               fill=COL_VALUE)

    # 分隔线
    d.line([(4 * SCALE, (y + ITEM_HEIGHT) * SCALE),
            ((PANEL_W + 10) * SCALE, (y + ITEM_HEIGHT) * SCALE)],
           fill=COL_SEP, width=1 * SCALE)
    return y + ITEM_HEIGHT


def draw_footer(d):
    y = (PANEL_H - 73 + 6) * SCALE
    d.line([(0, y - 6 * SCALE), (PANEL_W * SCALE, y - 6 * SCALE)],
           fill=COL_SEP, width=1 * SCALE)
    d.text((30 * SCALE, y), "B  返回", font=font(False, FS_FOOTER), fill=COL_FOOTER)
    d.text((160 * SCALE, y), "A  确定", font=font(False, FS_FOOTER), fill=COL_FOOTER)


def clip_to_scissor(img):
    """按 List 的真实裁剪矩形切掉超出部分。

    真机上 List 的内容会被 enableScissoring(..., y=88, h=557) 裁掉，
    所以预览也必须裁 —— 否则会显示出真机看不到的内容，造成误导。
    """
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    top = SCISSOR_TOP * SCALE
    bottom = SCISSOR_BOTTOM * SCALE
    out.paste(img.crop((0, top, img.size[0], bottom)), (0, top))
    # 裁剪区之外保留标题栏与背景，但不含列表内容
    out.paste(img.crop((0, 0, img.size[0], top)), (0, 0))
    out.paste(img.crop((0, bottom, img.size[0], img.size[1])), (0, bottom))
    return out


def build_main_page():
    img, d, layer, dl = new_page()
    # 显式指定副标题提示: MainGui 里有两个 OverlayFrame("超能滤镜", ...)，
    # 第一个是服务不可用时的引导页（· 未连接），这里要的是正常主页面。
    title, sub = overlay_frame("超能滤镜", "按下即生效")
    draw_title(d, title, sub)

    # ⚠ 行数必须与 gui.cpp 的 MainGui::createUI() 一致（3 小标题 + 6 项）:
    #   33 + 3*33 + 6*70 = 552 ≤ 557，整页都在裁剪区内。
    #   曾经这里画 8 项（多画了「生效方式」「适用游戏」），于是预览图底部
    #   被 compose() 按裁剪区切掉 —— 那张图正好把主页面的溢出暴露了出来。
    #   那两行已从 gui.cpp 删除，这里同步删掉，否则预览会继续画出
    #   真机上不存在的行。
    y = 97
    y = draw_header(dl, y, "当前画面")
    y = draw_item(dl, y, "滤镜", "已开启")
    y = draw_item(dl, y, "效果", "鲜艳", selected=True)
    y = draw_item(dl, y, "作用于", "档位1")

    y = draw_header(dl, y, "操作")
    y = draw_item(dl, y, "选择滤镜", "共30种")
    y = draw_item(dl, y, "关闭滤镜", "恢复画面")

    y = draw_header(dl, y, "使用说明")
    y = draw_item(dl, y, "关于本插件", author_name())

    return compose(img, d, layer)


def build_preset_page():
    img, d, layer, dl = new_page()
    title, sub = overlay_frame("选择滤镜")
    draw_title(d, title, sub)

    presets, groups = extract_presets()

    y = 97
    last = None
    for idx, (name, desc, g) in enumerate(presets):
        if g != last:
            if y + HEADER_HEIGHT > SCISSOR_BOTTOM:
                break
            y = draw_header(dl, y, groups.get(g, g))
            last = g
        if y >= SCISSOR_BOTTOM:
            break
        # 让第 6 项处于选中态，展示高亮效果
        y = draw_item(dl, y, name, desc, selected=(idx == 5))

    return compose(img, d, layer)


def build_info_page():
    img, d, layer, dl = new_page()
    title, sub = overlay_frame("关于本插件")
    draw_title(d, title, sub)

    y = 97
    y = draw_header(dl, y, "作者")
    y = draw_item(dl, y, "作者", author_name())

    y = draw_header(dl, y, "QQ 交流群")
    y = draw_item(dl, y, "1群", "259121473", selected=True)
    y = draw_item(dl, y, "2群", "712676771")
    y = draw_item(dl, y, "3群", "71627115")

    y = draw_header(dl, y, "说明")
    y = draw_item(dl, y, "滤镜数", "30种")
    y = draw_item(dl, y, "引擎", "Fizeau")
    y = draw_item(dl, y, "版本", version())

    return compose(img, d, layer)


def main():
    outdir = Path(sys.argv[1]) if len(sys.argv) > 1 else (ROOT / "preview")
    outdir.mkdir(parents=True, exist_ok=True)

    pages = [
        ("01-主页面", build_main_page()),
        ("02-滤镜列表", build_preset_page()),
        ("03-关于", build_info_page()),
    ]

    for name, img in pages:
        # 缩小回 1 倍（超采样降采样，边缘更平滑）
        final = img.resize((PANEL_W, PANEL_H), Image.LANCZOS)
        p = outdir / f"{name}.png"
        final.save(p)
        print(f"  {p}  ({final.size[0]}x{final.size[1]})")

    # 三页并排的总览图
    gap = 12
    total_w = PANEL_W * 3 + gap * 2
    sheet = Image.new("RGB", (total_w, PANEL_H), (24, 26, 32))
    for k, (_, img) in enumerate(pages):
        sheet.paste(img.resize((PANEL_W, PANEL_H), Image.LANCZOS),
                    (k * (PANEL_W + gap), 0))
    sheet_path = outdir / "00-三页总览.png"
    sheet.save(sheet_path)
    print(f"  {sheet_path}  ({sheet.size[0]}x{sheet.size[1]})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
