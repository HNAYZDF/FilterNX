#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_registry_check.py — 自测 check_registry.py

构造一个与真机现场一致的"损坏"注册表：
    - [超能滤镜.ovl] 段残留，custom_version=6.0.0（旧部署写进去的）
    - [Chaoneng.ovl] 段的文件 NACP 是 1.0.0

预期: check_registry.py 应报出冲突，而不是"通过"。
这验证检查器真的能抓住"菜单显示 6.0.0 / 插件内 1.0.0"这类问题。
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
DIST_OVL = ROOT / "dist" / "switch" / ".overlays" / "Chaoneng.ovl"
CHECKER = ROOT / "tools" / "check_registry.py"

passed = failed = 0


def check(cond, label):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        print(f"  FAIL  {label}")


def run_checker(sd: Path):
    r = subprocess.run([sys.executable, str(CHECKER), str(sd)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def main():
    if not DIST_OVL.is_file():
        print(f"[skip] 找不到 {DIST_OVL}（需先运行 package.sh）")
        return 0

    print("=== check_registry.py 自测 ===\n")

    # 从产物里读出真实版本号，后面构造"一致"的注册表时用它。
    #
    # ⚠ 不能硬编码: 曾经写死 1.0.0，后来产物升到 1.0.1，
    #   于是自测把"正确的注册表"误判成冲突 —— 假失败。
    #   检查器本身是对的，是测试数据过时了。
    sys.path.insert(0, str(ROOT / "tools"))
    from nacp_layout import find_nacp, get_version  # noqa: E402
    _b = DIST_OVL.read_bytes()
    _off, _, _ = find_nacp(_b)
    real_ver = get_version(_b, _off) if _off is not None else ""
    if not real_ver:
        print("[skip] 无法从产物读出版本号")
        return 0
    print(f"  产物版本: {real_ver}\n")

    tmp = Path(tempfile.mkdtemp(prefix="fnx_reg_test_"))
    try:
        ovl_dir = tmp / "switch" / ".overlays"
        ini_dir = tmp / "config" / "ultrahand"
        ovl_dir.mkdir(parents=True)
        ini_dir.mkdir(parents=True)

        # ── 场景 1: 现场那样的损坏状态 ──
        print("[场景 1: 旧段残留 custom_version=6.0.0（现场状态）]")
        shutil.copy(DIST_OVL, ovl_dir / "Chaoneng.ovl")
        (ini_dir / "overlays.ini").write_text(
            "[ovlmenu.ovl]\n"
            "priority=20\n"
            "\n"
            "[超能滤镜.ovl]\n"
            "custom_name=超能滤镜\n"
            "custom_version=6.0.0\n"
            "\n"
            "[Chaoneng.ovl]\n"
            "custom_name=超能滤镜\n"
            f"custom_version={real_ver}\n"
            "hide=false\n",
            encoding="utf-8")

        rc, out = run_checker(tmp)
        check(rc != 0, "检出旧文件名残留段（退出码非 0）")
        check("超能滤镜.ovl" in out, "输出里点名了 [超能滤镜.ovl]")
        check("压过 NACP" in out or "custom_version" in out,
              "说明了 custom_* 会压过 NACP")

        # ── 场景 2: 干净状态 ──
        print("\n[场景 2: 干净状态（只有正确段）]")
        (ini_dir / "overlays.ini").write_text(
            "[ovlmenu.ovl]\n"
            "priority=20\n"
            "\n"
            "[Chaoneng.ovl]\n"
            "custom_name=超能滤镜\n"
            f"custom_version={real_ver}\n"
            "hide=false\n",
            encoding="utf-8")

        rc, out = run_checker(tmp)
        check(rc == 0, "干净状态通过（退出码 0）")
        check("没有旧文件名残留段" in out, "报告无残留段")

        # ── 场景 3: 冲突但无残留段（注册表版本与 NACP 不符）──
        print("\n[场景 3: 注册表 custom_version 与 NACP 冲突]")
        (ini_dir / "overlays.ini").write_text(
            "[Chaoneng.ovl]\n"
            "custom_name=超能滤镜\n"
            "custom_version=9.9.9\n",
            encoding="utf-8")

        rc, out = run_checker(tmp)
        check(rc != 0, "检出版本冲突（退出码非 0）")
        check("9.9.9" in out, "输出里点出了冲突的版本值")

        # ── 场景 4: 注册表不存在（应视为正常）──
        print("\n[场景 4: 注册表不存在]")
        (ini_dir / "overlays.ini").unlink()
        rc, out = run_checker(tmp)
        check(rc == 0, "注册表缺失不算错误")

        # ── 场景 5: 只有 NACP、没有 custom_*（应通过）──
        print("\n[场景 5: 段存在但 custom_* 为空（菜单用 NACP，正常）]")
        (ini_dir / "overlays.ini").write_text(
            "[Chaoneng.ovl]\n"
            "custom_name=\n"
            "custom_version=\n"
            "hide=false\n",
            encoding="utf-8")
        rc, out = run_checker(tmp)
        check(rc == 0, "custom_* 为空时通过（菜单读 NACP）")

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print("=" * 56)
    print(f"检查项: {passed + failed}   失败: {failed}")
    print("结果: " + ("全部通过" if failed == 0 else "存在失败"))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
