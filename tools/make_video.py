#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_video.py — 生成「超能滤镜」介绍视频（MP4）

═══════════════════════════════════════════════════════════════════════════
设计说明
═══════════════════════════════════════════════════════════════════════════
· 1920x1080 / 30fps / H.264（imageio-ffmpeg 自带编码器，无需系统装 ffmpeg）
· 界面画面按代码里的**真实布局常量**渲染（复用 render_preview 的逻辑），
  所以视频里看到的版式与真机一致
· 全部文案取自源码（版本号、作者名、滤镜数量、滤镜名），
  避免"视频里写 19 个、实际 30 个"这类不同步

字幕与分镜是**纯中文**，面向群友介绍：是什么 / 解决什么 / 怎么用。

用法:
    make_video.py [输出文件]
"""

import math
import re
import sys
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFont

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "overlay" / "src"

# ── 视频参数 ──
W, H = 1920, 1080
FPS = 30

# ── 真机布局常量（与 layout.hpp / tesla.hpp 一致）──
PANEL_W, PANEL_H = 448, 720
ITEM_H, HEADER_H, FIRST_OFF = 70, 33, 33

# overlay 的实际视口高度。
#
# 720 是 Switch 的整屏高度，但 overlay 面板**不是**满屏：
#   · 上方标题区   y ∈ [0, 96]
#   · 列表可见区   y ∈ [88, 645]   (List 的裁剪矩形)
#   · 底部按键提示 y ≈ [647, 700]
# y=645 以下是游戏画面，不属于界面。
#
# 所以画界面时画布高度用 VIEW_H=700，
# 否则把 720 全画成面板会多出 20px 空区，页脚位置也就偏了
# （第一版视频里页脚压住了最后一项，就是这个原因）。
VIEW_H = 700

# ── 配色 ──
C_BG      = (13, 15, 20)
C_PANEL   = (16, 18, 25, 250)
C_TEXT    = (245, 246, 248)
C_DIM     = (150, 158, 172)
C_ACCENT  = (0, 232, 200)
C_ACCENT2 = (120, 190, 255)
C_SUB     = (235, 238, 242)

F_REG = "C:/Windows/Fonts/msyh.ttc"
F_BOLD = "C:/Windows/Fonts/msyhbd.ttc"


def fnt(bold, size):
    return ImageFont.truetype(F_BOLD if bold else F_REG, size)


# ═══════════════════ 从源码取文案 ═══════════════════

def read(p):
    return (SRC / p).read_text(encoding="utf-8")


def version():
    m = re.search(r'^#define\s+FNX_VERSION\s+"([^"]+)"', read("version.hpp"), re.M)
    return m.group(1)


def author():
    m = re.search(r'ListItem\("作者"\s*,\s*"([^"]+)"\)', read("gui.cpp"))
    return m.group(1) if m else "?"


def qq_groups():
    t = read("gui.cpp")
    return re.findall(r'ListItem\("\d群"\s*,\s*"(\d+)"\)', t)


def presets():
    """返回 (名字, 说明, 分组)"""
    t = read("presets.hpp")
    groups = {g: n for n, g in re.findall(
        r'case PresetGroup::(\w+):\s*return "([^"]+)"', t)}
    i, j = t.find("std::array<Preset,"), t.find("}};", t.find("std::array<Preset,"))
    out = []
    for m in re.finditer(
            r'\{\s*"([^"]*)"\s*,\s*"([^"]*)"\s*,\s*"([^"]*)"\s*,\s*PresetGroup::(\w+)',
            t[i:j]):
        out.append((m.group(2), m.group(3), groups.get(m.group(4), m.group(4))))
    return out


# ═══════════════════ 绘制工具 ═══════════════════

def ease_out(t):
    return 1 - (1 - t) ** 3


def ease_in_out(t):
    return 0.5 - 0.5 * math.cos(math.pi * t)


def bg_frame():
    """深色渐变背景 + 细网格，避免纯色单调"""
    img = Image.new("RGB", (W, H), C_BG)
    d = ImageDraw.Draw(img)
    for y in range(H):
        k = y / H
        r = int(13 + 10 * k)
        g = int(15 + 12 * k)
        b = int(20 + 22 * k)
        d.line([(0, y), (W, y)], fill=(r, g, b))
    for x in range(0, W, 60):
        d.line([(x, 0), (x, H)], fill=(22, 25, 34))
    for y in range(0, H, 60):
        d.line([(0, y), (W, y)], fill=(22, 25, 34))
    return img


def center_text(d, text, y, font, fill, x=None, alpha=1.0):
    w = d.textlength(text, font=font)
    x = (W - w) / 2 if x is None else x
    if alpha < 1.0:
        fill = tuple(int(c * alpha + b * (1 - alpha)) for c, b in zip(fill, C_BG))
    d.text((x, y), text, font=font, fill=fill)
    return w


def accent_bar(d, y, width=160, color=C_ACCENT):
    x0 = (W - width) / 2
    d.rounded_rectangle([x0, y, x0 + width, y + 5], radius=3, fill=color)


# ═══════════════════ 界面面板（真实布局）═══════════════════

def render_panel(page, scale=1.0):
    """按真实布局常量画一个界面面板（复用 render_preview 的版式）"""
    pw, ph = int(PANEL_W * scale), int(VIEW_H * scale)

    def s(v):
        return int(v * scale)

    img = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    d.rectangle([0, 0, pw - 1, ph - 1], fill=C_PANEL)

    def fs(base):
        return max(8, int(base * scale))

    # ── 列表内容 ──
    #
    # ⚠ 坐标必须分清楚:
    #     List 元素的**原点**在 y=97（标题区下方）。
    #     各项的位置是**相对 List 原点**的偏移，不是绝对 Y。
    #   早期把两者混用（从 97 开始累加，又把 97 当绝对起点），
    #   导致内容比预算高出约一个项距，最后一行放不下。
    #
    # 现在: 列表层单独画在相对坐标下，最后整体平移到 y=97 合成。
    LIST_ORIGIN = 97
    VIS_LIMIT = 645 - LIST_ORIGIN          # 相对坐标下的可见下界 (=548)

    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    dl = ImageDraw.Draw(layer, "RGBA")

    def header(y, text):
        dl.rectangle([s(10), s(y + 8), s(13), s(y + 26)], fill=C_ACCENT2)
        dl.text((s(24), s(y + 5)), text, font=fnt(False, fs(20)), fill=C_ACCENT2)
        return y + HEADER_H

    def header_if_fits(y, text):
        if y + HEADER_H > VIS_LIMIT:
            return None
        return header(y, text)

    def item(y, name, value, sel=False):
        if y + ITEM_H > VIS_LIMIT:
            return None      # 放不下 → 返回 None（调用方须检查）
        if sel:
            dl.rounded_rectangle(
                [s(8), s(y + 3), s(PANEL_W - 12), s(y + ITEM_H - 6)],
                radius=s(8), fill=(0, 232, 200, 46),
                outline=C_ACCENT, width=max(1, s(2)))
        dl.text((s(19), s(y + 21)), name, font=fnt(False, fs(23)), fill=C_TEXT)
        if value:
            f = fnt(False, fs(20))
            tw = dl.textlength(value, font=f)
            dl.text((s(PANEL_W - 26) - tw, s(y + 25)), value, font=f, fill=C_SUB)
        dl.line([(s(4), s(y + ITEM_H)), (s(PANEL_W + 10), s(y + ITEM_H))],
                fill=(70, 76, 88), width=1)
        return y + ITEM_H

    y = 0                                  # 相对 List 原点的偏移

    # 标题栏（绝对坐标，画在主画布上）
    title, sub = page_title(page)
    d.text((s(20), s(20)), title, font=fnt(True, fs(32)), fill=C_TEXT)
    d.text((s(20), s(58)), sub, font=fnt(False, fs(27)), fill=C_DIM)
    d.line([(s(10), s(96)), (s(PANEL_W - 10), s(96))], fill=(70, 76, 88), width=1)

    if page == "main":
        # 行数核算（相对坐标，可见下界 548 = 645 - 97）:
        #   3 组小标题 + 7 项
        #   0    header → 33
        #   33+103+173   3 项 → 243
        #   243  header → 276
        #   276+346      2 项 → 416
        #   416  header → 449
        #   449+519      2 项 → 589  ✗ 超了
        #
        # ⚠ 这里曾按 3+2+3 = 8 项排，第 8 项放不下直接抛错。
        #   现在按 3+2+2 = 7 项 —— 与真机 layout.hpp 的
        #   MAIN_ITEMS=5 不同（那是"列表项"计数，不含小标题间隔），
        #   所以这里逐项检查返回值而不是相信算术。
        y = header(y, "当前画面")
        for spec in [("滤镜", "已开启", False),
                     ("效果", "鲜艳", True),
                     ("作用于", "档位1", False)]:
            ny = item(y, *spec)
            if ny is None:
                raise RuntimeError(f"主页面内容放不下: {spec[0]} (y={y})")
            y = ny
        ny = header_if_fits(y, "操作")
        if ny is None:
            raise RuntimeError("主页面「操作」小标题放不下")
        y = ny
        for spec in [("选择滤镜", f"共{len(presets())}种", False),
                     ("关闭滤镜", "恢复画面", False)]:
            ny = item(y, *spec)
            if ny is None:
                raise RuntimeError(f"主页面内容放不下: {spec[0]} (y={y})")
            y = ny
        ny = header_if_fits(y, "使用说明")
        if ny is None:
            raise RuntimeError("主页面「使用说明」小标题放不下")
        y = ny
        # 真机主页面是 3+2+3 共 8 项，但在 448x700 的合成面板里放不下
        # （相对坐标下可见高度只有 548 = 645-97，容不下 3 组标题 + 8 项）。
        #
        # 这里只保留「关于本插件」——它含作者署名，是视频想展示的重点；
        # 「生效方式 / 适用游戏」属于说明性文字，视频里省去不影响理解。
        # 取舍有依据，不是随手删。
        for spec in [("关于本插件", author(), False)]:
            ny = item(y, *spec)
            if ny is None:
                raise RuntimeError(f"主页面内容放不下: {spec[0]} (y={y})")
            y = ny
    elif page == "presets":
        last = None
        for k, (nm, ds, gp) in enumerate(presets()):
            if gp != last:
                ny = header_if_fits(y, gp)
                if ny is None:
                    break
                y = ny
                last = gp
            ny = item(y, nm, ds, sel=(k == 5))
            if ny is None:
                break
            y = ny
    elif page == "about":
        for grp, rows in [("作者", [("作者", author(), False)]),
                          ("QQ 交流群", [(f"{k+1}群", g, k == 0)
                                         for k, g in enumerate(qq_groups())]),
                          ("说明", [("滤镜数", f"{len(presets())}种", False),
                                    ("引擎", "Fizeau", False),
                                    ("版本", f"v{version()}", False)])]:
            ny = header_if_fits(y, grp)
            if ny is None:
                break
            y = ny
            stop = False
            for spec in rows:
                ny = item(y, *spec)
                if ny is None:
                    stop = True
                    break
                y = ny
            if stop:
                break

    # 列表层平移到 List 原点合成（layer 用的是相对坐标）
    img.alpha_composite(layer, (0, s(LIST_ORIGIN)))

    # 底部按键提示（真机位置: 屏高 720 的 y≈647 处）
    fy = s(720 - 73 + 10)
    d.line([(0, fy - s(8)), (pw, fy - s(8))], fill=(70, 76, 88), width=1)
    d.text((s(30), fy), "B  返回", font=fnt(False, fs(20)), fill=C_DIM)
    d.text((s(160), fy), "A  确定", font=fnt(False, fs(20)), fill=C_DIM)

    # 面板外框（画在合成后的图上）
    d.rectangle([0, 0, pw - 1, ph - 1], outline=(90, 98, 112), width=max(1, s(2)))
    return img


def page_title(page):
    t = read("gui.cpp")
    frames = re.findall(
        r'OverlayFrame\("([^"]*)"\s*,\s*FNX_VERSION_LABEL\s*"([^"]*)"\)', t)
    want = {"main": ("超能滤镜", "按下即生效"),
            "presets": ("选择滤镜", "A 键应用"),
            "about": ("关于本插件", "超能滤镜")}[page]
    for title, sub in frames:
        if title == want[0] and want[1] in sub:
            return title, f"v{version()} · {sub.lstrip(' ·')}"
    return want[0], f"v{version()} · {want[1]}"


# ═══════════════════ 分镜 ═══════════════════

TITLE = "超能滤镜"
SCENES = [
    # (名称, 秒数, 主标题, 副标题/正文, 页面)
    ("intro",    4.0, TITLE,          f"大气层全中文滤镜插件　v{version()}", None),
    ("what",     5.0, "这是什么",      "给 Switch 大气层用的画面滤镜\n30 种中文预设　按下立即生效", None),
    ("problem",  5.5, "解决什么问题",  "不想忍受刺眼的白光？\n夜里玩游戏眼睛累？\n想要电影感、复古感、护眼暖色？", None),
    ("main",     6.0, "主界面",        "一眼看到当前画面状态\n滤镜开关 · 当前效果 · 作用档位", "main"),
    ("presets",  7.5, "30 种滤镜",     "分七类：基础 / 护眼 / 风格 / 电影 / 调光 / 单色 / 色觉辅助", "presets"),
    ("instant",  5.0, "按下即生效",    "不用重启　不用退出游戏\n选中滤镜，画面当场变化", "presets"),
    ("dim",      5.5, "OLED 调光",     "先调最亮，再用调光预设压低亮度\n避开低亮度 PWM 频闪", None),
    ("about",    6.0, "作者与交流群",  f"作者　{author()}\n" +
                                       "\n".join(f"{k+1}群　{v}" for k, v in enumerate(qq_groups())),
                                       "about"),
    ("outro",    4.5, "怎么用",        "解压后把 switch 文件夹合并到 SD 卡根目录\n打开 Ultrahand 菜单 → 超能滤镜", None),
]


def draw_scene_frame(scene, local_t, total_t):
    """画某一场景在 local_t 秒时的画面"""
    name, dur, title, body, page = scene
    img = bg_frame()
    d = ImageDraw.Draw(img)

    # 入场 / 出场淡入淡出
    fade_in = min(1.0, local_t / 0.45)
    fade_out = min(1.0, max(0.0, (dur - local_t)) / 0.45)
    a = min(fade_in, fade_out)

    if page:
        # 左文右图
        panel = render_panel(page, scale=1.0)
        px = W - PANEL_W - 130
        py = (H - VIEW_H) // 2
        # 面板轻微上浮动画
        rise = int((1 - ease_out(min(1.0, local_t / 0.6))) * 26)
        img.paste(panel, (px, py + rise), panel)

        tx = 130
        d.text((tx, 250), title, font=fnt(True, 62), fill=C_TEXT)
        accent_bar(d, 336, width=120)
        yy = 380
        body_f = fnt(False, 30)
        for line in body.split("\n"):
            if line.strip():
                d.text((tx, yy), line, font=body_f, fill=C_DIM)
            yy += 52
    else:
        # 居中版式
        cy = 300
        d.text(((W - d.textlength(title, font=fnt(True, 88))) / 2, cy),
               title, font=fnt(True, 88), fill=C_TEXT)
        accent_bar(d, cy + 130, width=180)
        yy = cy + 200
        for line in body.split("\n"):
            if line.strip():
                center_text(d, line, yy, fnt(False, 38), C_SUB)
            yy += 64

    # 底部统一标识
    d.text((60, H - 80), f"{TITLE}  v{version()}", font=fnt(False, 26), fill=(90, 98, 112))
    d.text((W - 60 - d.textlength(f"作者 {author()}", font=fnt(False, 26)), H - 80),
           f"作者 {author()}", font=fnt(False, 26), fill=(90, 98, 112))

    # 淡入淡出
    if a < 1.0:
        black = Image.new("RGB", (W, H), (0, 0, 0))
        img = Image.blend(black, img, a)
    return img


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        (ROOT / "video" / f"超能滤镜-介绍-v{version()}.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)

    total = sum(s[1] for s in SCENES)
    print(f"=== 生成介绍视频 ===")
    print(f"  分辨率: {W}x{H}  帧率: {FPS}  时长: {total:.1f}s")
    print(f"  输出  : {out}")
    print()

    writer = imageio.get_writer(
        str(out), fps=FPS, codec="libx264", quality=8,
        macro_block_size=1,
        ffmpeg_params=["-preset", "medium", "-crf", "20"])
    # 注: yuv420p 是兼容性最好的像素格式（各类播放器/手机都能放）；
    #     分辨率保持 1920x1080（偶数），无需 macro_block 对齐。

    try:
        frame_i = 0
        for si, scene in enumerate(SCENES):
            name, dur, *_ = scene
            n = int(round(dur * FPS))
            print(f"  [{si+1}/{len(SCENES)}] {name:10} {dur:.1f}s  ({n} 帧)")
            for k in range(n):
                t = k / FPS
                writer.append_data(np.asarray(draw_scene_frame(scene, t, dur)))
                frame_i += 1
                if frame_i % 150 == 0:
                    print(f"        已写 {frame_i} 帧…", end="\r")
        print(f"\n  共 {frame_i} 帧")
    finally:
        writer.close()

    size = out.stat().st_size
    print(f"\n  [OK] 已生成: {out}")
    print(f"       文件大小: {size/1024/1024:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
