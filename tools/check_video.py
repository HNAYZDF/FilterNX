#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验生成的视频：能否解码、时长、抽帧检查画面。"""
import sys
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from PIL import Image

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
VID = ROOT / "video" / "超能滤镜-介绍-v1.0.3.mp4"

if not VID.is_file():
    print(f"找不到 {VID}")
    sys.exit(1)

print(f"=== 校验 {VID.name} ===")
print(f"  文件大小: {VID.stat().st_size/1024/1024:.2f} MB")

rdr = imageio.get_reader(str(VID))
meta = rdr.get_meta_data()
print(f"  元数据  : {meta}")
try:
    n = rdr.count_frames()
except Exception:
    n = None
print(f"  帧数    : {n}")

# 抽查若干时间点，保存为图片供肉眼检查
probe_t = [1.0, 3.0, 7.0, 13.0, 20.0, 27.0, 34.0, 40.0, 46.0]
fps = meta.get("fps", 30)
outdir = ROOT / "video" / "frames"
outdir.mkdir(parents=True, exist_ok=True)

print()
print("  抽帧检查:")
for i, t in enumerate(probe_t):
    idx = int(t * fps)
    try:
        fr = rdr.get_data(idx)
        img = Image.fromarray(fr)
        p = outdir / f"t{int(t):02d}s.png"
        img.save(p)
        # 统计非背景像素占比，粗略判断画面不是全黑
        arr = np.asarray(img.convert("L"))
        bright = (arr > 60).mean()
        print(f"    t={t:5.1f}s  形状={fr.shape}  高亮像素占比={bright*100:5.2f}%  -> {p.name}")
    except Exception as e:
        print(f"    t={t:5.1f}s  ★ 抽帧失败: {type(e).__name__}: {e}")

rdr.close()
print()
print("  抽帧已保存到 video/frames/，供肉眼核对")
