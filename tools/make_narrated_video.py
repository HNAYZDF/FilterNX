#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_narrated_video.py — 生成带中文旁白的介绍视频

═══════════════════════════════════════════════════════════════════════════
配音来源与版权
═══════════════════════════════════════════════════════════════════════════
使用 **Edge TTS**（微软公开神经语音，如 zh-CN-XiaoxiaoNeural）:
  · 免费、无需 API Key
  · 合成音，**不是任何真人的声纹**，不存在冒用他人身份的问题
  · 一般使用条款下可用于个人/非商业内容

（备选: Windows 自带 SAPI 的 Microsoft Huihui Desktop，完全离线，
  但机械感较强。）

═══════════════════════════════════════════════════════════════════════════
时序处理
═══════════════════════════════════════════════════════════════════════════
先合成每段旁白 → 量出真实时长 → **按旁白时长决定画面停留时间**。
这样不会出现"话说一半画面就切走"或"画面停着没人说话"。

每段末尾留 0.6 秒余量（说完喘口气再切）。

用法:
    make_narrated_video.py [输出mp4]
"""

import asyncio
import math
import re
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import imageio.v2 as imageio
import imageio_ffmpeg
import numpy as np

# 复用无旁白版的绘制逻辑，避免两份实现不一致
sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_video as mv  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "video" / "_narr"

# 中文旁白声线。XiaoxiaoNeural 是微软的通用女声，自然度较好。
# 换声线只需改这里（例如 zh-CN-YunxiNeural 男声 / zh-CN-XiaoyiNeural）。
VOICE = "zh-CN-XiaoxiaoNeural"

# 语速微调（百分比）。+10% 让 49 秒的内容不至于拖太久。
RATE = "+8%"

# 每段旁白说完后的停顿（秒）
TAIL_PAD = 0.6

# 分镜旁白。与 make_video.SCENES 的页面部分对应。
NARRATION = [
    ("intro",
     "超能滤镜，大气层全中文画面滤镜插件。"),
    ("what",
     "给任天堂 Switch 用的一套画面滤镜。三十种中文预设，选好按下，"
     "画面立刻变化，不用重启，也不用退出游戏。"),
    ("problem",
     "是不是觉得屏幕太刺眼，夜里玩游戏眼睛发酸？"
     "或者想要电影感、复古感，让画面更有味道？"),
    ("main",
     "打开插件，第一眼就能看到当前画面状态。"
     "滤镜开关、当前效果、作用档位，清清楚楚。"),
    ("presets",
     "三十种滤镜分成七类。护眼有四个色温档，风格里有鲜艳、复古、冷色、暖色，"
     "电影类做青橙分离，调光类用来压低亮度，单色和色觉辅助也都齐了。"),
    ("instant",
     "全程按下即生效。走的是 Fizeau 的色彩管线，不占游戏性能，"
     "所有游戏通用。"),
    ("dim",
     "OLED 用户注意：先把系统亮度调到最亮，再用调光预设降低观感亮度，"
     "这样能避开低亮度下的频闪。"),
    ("about",
     "插件作者 hnayzdf。有问题欢迎加入交流群，"
     "一群、二群、三群都可以找到我。"),
    ("outro",
     "安装很简单：解压后把 switch 文件夹合并到内存卡根目录，"
     "打开 Ultrahand 菜单就能看到超能滤镜。"),
]


async def synth(text, out_path):
    import edge_tts
    c = edge_tts.Communicate(text, VOICE, rate=RATE)
    await c.save(str(out_path))


def wav_duration(path):
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def ffmpeg_exe():
    return imageio_ffmpeg.get_ffmpeg_exe()


def to_wav(src, dst, sr=48000):
    """用 ffmpeg 把任意音频转成指定采样率的单声道 WAV（便于拼接）"""
    subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error",
                    "-i", str(src), "-ac", "1", "-ar", str(sr),
                    "-f", "wav", str(dst)], check=True)


def read_wav_mono(path):
    """读单声道 16bit WAV，返回 (int16 数组, 采样率)"""
    with wave.open(str(path), "rb") as w:
        if w.getnchannels() != 1:
            raise RuntimeError(f"{path} 不是单声道")
        sr = w.getframerate()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return data, sr


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        (ROOT / "video" / f"超能滤镜-介绍-中文旁白-v{mv.version()}.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)

    print("=== 1/4 合成中文旁白（Edge TTS）===")
    print(f"  声线: {VOICE}   语速: {RATE}")
    seg_files = []
    for key, text in NARRATION:
        mp3 = WORK / f"{key}.mp3"
        wav = WORK / f"{key}.wav"
        if not mp3.exists():
            asyncio.run(synth(text, mp3))
        to_wav(mp3, wav)
        d = wav_duration(wav)
        seg_files.append((key, wav, d))
        print(f"  {key:10} {d:5.2f}s  {text[:24]}…")

    print()
    print("=== 2/4 拼接音轨 ===")
    sr = 48000
    chunks = []
    scene_durs = []
    for key, wav, d in seg_files:
        data, _ = read_wav_mono(wav)
        chunks.append(data)
        chunks.append(np.zeros(int(sr * TAIL_PAD), dtype=np.int16))
        scene_durs.append(d + TAIL_PAD)

    track = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.int16)
    total_audio = len(track) / sr
    print(f"  总时长: {total_audio:.2f}s  采样率: {sr}")

    # 峰值归一化到 -3dBFS，避免爆音
    peak = int(np.abs(track).max()) if track.size else 0
    if peak > 0:
        target = int(32767 * 0.70)
        track = (track.astype(np.float32) * (target / peak)).astype(np.int16)
        print(f"  峰值归一化: {peak} -> {int(np.abs(track).max())}")

    track_wav = WORK / "narration.wav"
    with wave.open(str(track_wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(track.tobytes())

    print()
    print("=== 3/4 按旁白时长渲染画面 ===")
    # 把 make_video.SCENES 的时长替换成实测旁白时长
    scenes = []
    for (name, _old, title, body, page), d in zip(mv.SCENES, scene_durs):
        scenes.append((name, d, title, body, page))
    mv.SCENES = scenes

    tmp_video = WORK / "silent.mp4"
    fps = mv.FPS
    writer = imageio.get_writer(
        str(tmp_video), fps=fps, codec="libx264", quality=8,
        macro_block_size=1,
        ffmpeg_params=["-preset", "medium", "-crf", "20"])
    try:
        n_total = 0
        for si, scene in enumerate(scenes):
            name, dur, *_ = scene
            n = max(1, int(round(dur * fps)))
            print(f"  [{si+1}/{len(scenes)}] {name:10} {dur:5.2f}s ({n} 帧)")
            for k in range(n):
                writer.append_data(np.asarray(mv.draw_scene_frame(scene, k / fps, dur)))
            n_total += n
        print(f"  共 {n_total} 帧")
    finally:
        writer.close()

    print()
    print("=== 4/4 合成音视频 ===")
    subprocess.run([
        ffmpeg_exe(), "-y", "-loglevel", "error",
        "-i", str(tmp_video),
        "-i", str(track_wav),
        "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
        "-shortest", str(out),
    ], check=True)

    size = out.stat().st_size
    print(f"  [OK] {out}")
    print(f"       时长 {total_audio:.1f}s   大小 {size/1024/1024:.2f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
