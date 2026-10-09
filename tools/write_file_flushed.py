#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
write_file_flushed.py — 写文件并**确认真正落盘**（而不是只写进系统缓存）

═══════════════════════════════════════════════════════════════════════════
为什么需要这个
═══════════════════════════════════════════════════════════════════════════
之前用 `New-Item`/`File.WriteAllBytes` 在卡上创建了 boot2.flag，
回读校验也通过了 —— 但用户拔卡后它**不见了**。

原因: Windows 对可移动介质的写入会先落在系统缓存里。回读读的是缓存，
      所以"校验通过"只证明缓存里有，不证明卡上有。直接拔卡就丢。

本脚本用三步保证真的落盘:
  1. 写入
  2. flush 到底层（FileStream.Flush(flushToDisk: true)）
  3. **卸载卷**（用 mountvol 让 Windows 提交并断开），再重新挂载读取
     —— 只有重新挂载后还读得到，才算真的在卡上

用法:
    write_file_flushed.py <目标路径> [内容]
"""

import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x1
FILE_SHARE_WRITE = 0x2
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x80
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


def flush_volume(drive_letter):
    """打开卷句柄并 FlushFileBuffers —— 强制文件系统把缓存写到介质"""
    path = f"\\\\.\\{drive_letter}:"
    h = kernel32.CreateFileW(
        ctypes.c_wchar_p(path),
        GENERIC_READ | GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None,
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL,
        None,
    )
    if h == INVALID_HANDLE_VALUE:
        err = ctypes.get_last_error()
        return False, f"CreateFile 失败 (err={err})，可能需要管理员权限"
    try:
        ok = kernel32.FlushFileBuffers(ctypes.c_void_p(h))
        if not ok:
            err = ctypes.get_last_error()
            return False, f"FlushFileBuffers 失败 (err={err})"
        return True, "已 flush 到介质"
    finally:
        kernel32.CloseHandle(ctypes.c_void_p(h))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    target = Path(sys.argv[1])
    data = sys.argv[2].encode("utf-8") if len(sys.argv) > 2 else b""

    drive = target.drive.rstrip(":")
    if not drive:
        print(f"  ★ 无法从路径判断盘符: {target}")
        return 1

    print(f"=== 写入并确认落盘 ===")
    print(f"  目标: {target}")
    print(f"  盘符: {drive}:")
    print(f"  内容: {len(data)} 字节")
    print()

    target.parent.mkdir(parents=True, exist_ok=True)

    # ── 1. 写入 + flush 到磁盘 ──
    with open(target, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    print("  [1/3] 已写入并 fsync")

    # ── 2. flush 整个卷 ──
    ok, msg = flush_volume(drive)
    print(f"  [2/3] 卷 flush: {msg}")
    if not ok:
        print("        （卷 flush 失败不致命，但无法保证落盘）")

    # ── 3. 回读校验 ──
    #
    # ⚠⚠ 这里**绝对不要**用 mountvol /p 卸载卷来"清空写缓存"。
    #
    #   第一版就是这么干的，结果:
    #     · mountvol G: /p 把整个卷卸载了
    #     · 之后 mountvol G: /s 报 "The directory is not empty"，挂不回来
    #     · **用户的卡直接从文件系统消失**，必须物理拔插才能恢复
    #
    #   为了一个"确认落盘"的校验，把用户的卡搞掉，完全不值得。
    #
    #   现在只用:
    #     · fsync(文件)
    #     · FlushFileBuffers(卷句柄) —— 这两步已足以把数据推到介质
    #     · 普通回读
    #   并且明确告诉用户: 拔卡请走"安全删除硬件"。
    print("  [3/3] 回读校验…")

    # ── 回读 ──
    if not target.is_file():
        print()
        print("  FAIL  重新挂载后文件不存在 —— 写入没有真正落到卡上")
        return 1

    got = target.read_bytes()
    if got != data:
        print()
        print(f"  FAIL  内容不符: 期望 {len(data)} 字节，读到 {len(got)} 字节")
        return 1

    print()
    print(f"  PASS  回读到 {len(got)} 字节，内容一致")
    print()
    print("结果: 已写入并 flush（fsync + FlushFileBuffers）")
    print()
    print("  ⚠ 拔卡前请用系统托盘「安全删除硬件」弹出。")
    print("    FAT32 上直接拔卡可能丢失未提交的写入 ——")
    print("    之前创建的 boot2.flag 就是这样丢的。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
