#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_connect_reachable.py — 核查「会话能否被建立」这条链路是否完整

═══════════════════════════════════════════════════════════════════════════
这个检查器为什么存在
═══════════════════════════════════════════════════════════════════════════
真实事故: 为了"更安全"，我把所有自动连接都删了 —— initServices() 空实现、
按钮删除、refresh_state() 改成只读。结果:

    **全工程再没有任何地方建立会话**
    → g_state.service_ok 永远是 false
    → 即使 Fizeau 正常开着，插件也永远只显示引导页

这就是「开启后台也不能调用」的原因。

教训: 光检查"危险调用有没有被删掉"是不够的 ——
      还必须检查**必需的调用没有被误删**。
      这两个方向都要守，否则就会在"防崩"的过程中把功能删没。

═══════════════════════════════════════════════════════════════════════════
本脚本核查的不变量（双向）
═══════════════════════════════════════════════════════════════════════════
  A. 必须存在一条能建立会话的路径（否则插件永远不可用）
  B. 危险调用必须不存在（pgl / 在 update 里 changeTo / 无守卫的 IPC）
  C. 连接失败必须不崩（有守卫、有提前返回）
"""

import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "overlay" / "src"

checks = 0
fails = 0


def ck(cond, label, detail=""):
    global checks, fails
    checks += 1
    if cond:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}")
        if detail:
            print(f"        {detail}")
        fails += 1


def strip_comments(t):
    t = re.sub(r'/\*.*?\*/', '', t, flags=re.S)
    return re.sub(r'//[^\n]*', '', t)


def get_function(text, name):
    """取出函数体（大括号配平，不用返回类型正则）"""
    short = name.rsplit("::", 1)[-1]
    for target in ([name, short] if "::" in name else [name]):
        start = 0
        while True:
            idx = text.find(target + "(", start)
            if idx < 0:
                break
            start = idx + 1
            line_start = text.rfind("\n", 0, idx) + 1
            prefix = text[line_start:idx]
            if any(c in prefix for c in ";}= ") and ";" in prefix:
                continue
            if ";" in prefix or "}" in prefix or "=" in prefix:
                continue
            i = idx + len(target) + 1
            depth_p = 1
            while i < len(text) and depth_p > 0:
                if text[i] == "(":
                    depth_p += 1
                elif text[i] == ")":
                    depth_p -= 1
                i += 1
            if depth_p != 0:
                continue
            j = i
            while j < len(text) and text[j] in " \t\r\n":
                j += 1
            for kw in ("const", "override", "noexcept", "final"):
                if text.startswith(kw, j):
                    j += len(kw)
                    while j < len(text) and text[j] in " \t\r\n":
                        j += 1
            if j >= len(text) or text[j] != "{":
                continue
            depth = 0
            for k in range(j, len(text)):
                if text[k] == "{":
                    depth += 1
                elif text[k] == "}":
                    depth -= 1
                    if depth == 0:
                        return text[j:k + 1]
    return None


def main():
    print("=== 会话可达性 + 安全性 双向核查 ===\n")

    main_cpp = strip_comments((SRC / "main.cpp").read_text(encoding="utf-8"))
    gui_cpp = strip_comments((SRC / "gui.cpp").read_text(encoding="utf-8"))
    ipc_cpp = strip_comments((SRC / "fizeau_ipc.cpp").read_text(encoding="utf-8"))
    allsrc = main_cpp + gui_cpp + ipc_cpp

    # ══════════════════════════════════════════════════════════════════
    # A. 必须存在建立会话的路径
    # ══════════════════════════════════════════════════════════════════
    print("[A. 必须能建立会话（否则 Fizeau 开着也用不了）]")

    init = get_function(main_cpp, "initServices")
    ck(init is not None, "找得到 initServices()")
    init_connects = bool(init and "fzInitialize(" in init)

    # 当前设计: 连接在专门的 connect_fizeau() 里
    cf_a = get_function(gui_cpp, "connect_fizeau")
    cf_connects = bool(cf_a and "fzInitialize(" in cf_a)

    rs = get_function(gui_cpp, "refresh_state")
    ck(rs is not None, "找得到 refresh_state()")
    rs_connects = bool(rs and "fzInitialize(" in rs)

    # 至少有一处能建立会话
    ck(init_connects or rs_connects or cf_connects,
       "至少有一处会调用 fzInitialize() 建立会话",
       "★ 全工程无人建立会话 = 插件永远只显示引导页（这个 bug 真实发生过）")
    print(f"        initServices   连接: {init_connects}")
    print(f"        connect_fizeau 连接: {cf_connects}")
    print(f"        refresh_state  连接: {rs_connects}")

    # connect_fizeau() 必须真的被调用（定义了却没人调 = 等同于没连接）
    if cf_a:
        called = "connect_fizeau()" in gui_cpp.replace(
            "bool connect_fizeau()", "", 1)
        ck(called, "connect_fizeau() 确实被调用（不是死代码）",
           "定义了但没人调用 = 插件永远显示引导页")

    # fzInitialize 的实现必须真的建立会话
    fi = get_function(ipc_cpp, "fzInitialize")
    ck(fi is not None, "找得到 fzInitialize() 实现")
    if fi:
        ck("smGetService(" in fi, "fzInitialize() 内部用 smGetService 建立会话")

    # 界面必须能把 service_ok 置为 true
    ok_set = "g_state.service_ok = true" in gui_cpp
    ck(ok_set, "存在把 service_ok 置为 true 的路径")

    # ══════════════════════════════════════════════════════════════════
    # B. 危险调用必须不存在
    # ══════════════════════════════════════════════════════════════════
    print()
    print("[B. 危险调用必须不存在]")

    ck("pglLaunchProgram(" not in allsrc and "pglInitialize(" not in allsrc,
       "没有 pgl 调用",
       "pgl 是 qlaunch 的服务；从 applet 调用会**挂住**（真机实测点下去卡死）")

    upd = get_function(gui_cpp, "MainGui::update") or get_function(gui_cpp, "update")
    ck(upd is not None, "找得到 MainGui::update()")
    if upd:
        ck("changeTo" not in upd,
           "update() 里没有 changeTo",
           "在 update 里重建页面 = 状态抖动时无限重建（曾导致崩溃）")

    # 每个 IPC 函数都要有守卫
    n_ipc = n_guarded = 0
    for m in re.finditer(
            r'^(?:inline\s+)?(?:Result|void|bool)\s+(\w+)\s*\([^;{]*\)\s*\{',
            ipc_cpp, re.M):
        i = m.end() - 1
        depth = 0
        body = None
        for j in range(i, len(ipc_cpp)):
            if ipc_cpp[j] == "{":
                depth += 1
            elif ipc_cpp[j] == "}":
                depth -= 1
                if depth == 0:
                    body = ipc_cpp[i:j + 1]
                    break
        if body and "serviceDispatch" in body:
            n_ipc += 1
            if "session_ready()" in body:
                n_guarded += 1
    ck(n_ipc > 0 and n_guarded == n_ipc,
       f"全部 {n_ipc} 个 IPC 函数都有会话守卫（实际 {n_guarded}）")

    # ══════════════════════════════════════════════════════════════════
    # C. 失败必须不崩
    # ══════════════════════════════════════════════════════════════════
    print()
    print("[C. 连接失败必须安全退出]")

    # 连接现在在专门的 connect_fizeau() 里
    cf = get_function(gui_cpp, "connect_fizeau")
    ck(cf is not None, "找得到 connect_fizeau()（唯一的连接入口）")
    if cf:
        ck("fzInitialize(" in cf, "connect_fizeau() 里才调用 fzInitialize()")
        ck("R_FAILED(rc)" in cf or "R_FAILED(fzInitialize())" in cf,
           "connect_fizeau() 检查返回值")
        ck("return false" in cf, "失败时返回 false")

    # refresh_state 必须**只读**
    if rs:
        ck("fzInitialize(" not in rs,
           "refresh_state() 不含 fzInitialize()（它被 update 周期调用）",
           "否则等于每帧重连一次")
        ck("service_ok = false" in rs, "refresh_state() 会正确清掉失效状态")

    if fi:
        ck("g_session = {}" in fi, "fzInitialize() 失败时清零句柄")
        ck("g_initialized = false" in fi, "fzInitialize() 失败时清除 initialized 标志")

    # 引导页零交互
    cui = get_function(gui_cpp, "MainGui::createUI")
    if cui:
        gs = cui.find("if (!g_state.service_ok)")
        guide = ""
        if gs >= 0:
            brace = cui.find("{", gs)
            if brace >= 0:
                depth = 0
                for k in range(brace, len(cui)):
                    if cui[k] == "{":
                        depth += 1
                    elif cui[k] == "}":
                        depth -= 1
                        if depth == 0:
                            guide = cui[brace:k + 1]
                            break
        ck("setClickListener" not in guide,
           "引导页零按钮、零回调")

    print()
    print("=" * 64)
    if fails:
        print(f"结果: ★ {fails} 项不满足")
        return 1
    print("结果: 会话可达 + 危险调用已清除 + 失败安全")
    print()
    print("      · Fizeau 开着  → 初始化时建立会话，界面正常可用")
    print("      · Fizeau 没开  → 连接失败，显示纯提示页，不崩不卡死")
    return 0


if __name__ == "__main__":
    sys.exit(main())
