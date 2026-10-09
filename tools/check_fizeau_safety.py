#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_fizeau_off_safe.py — 「Fizeau 未运行时插件不崩」安全性核查

═══════════════════════════════════════════════════════════════════════════
这个检查器的定位（很关键，否则它会一直误报）
═══════════════════════════════════════════════════════════════════════════
它只负责**安全**，不负责规定「能不能连接」。

⚠ 历史教训: 前一版按当时的设计断言「initServices 里不许有 Fizeau 调用」、
  「refresh_state 不许调 fzInitialize」。后来设计变了 —— 那些调用其实是
  **必需**的（删掉会导致插件彻底失效）—— 于是这些断言全部变成误报。

  **检查器不该规定设计，只该守住安全属性。**
  「必须有路径能连接」由 check_connect_reachable.py 从另一个方向守。

═══════════════════════════════════════════════════════════════════════════
它守的安全属性
═══════════════════════════════════════════════════════════════════════════
  1. 每个 IPC 函数内部都有会话守卫（拿不到会话就返回错误，不发请求）
  2. fzInitialize() 的调用都检查返回值
  3. fzInitialize() 失败时清零句柄与标志（否则守卫形同虚设）
  4. 引导页零按钮、零回调（按钮里的 pgl 调用曾导致卡死）
  5. update() 里没有 changeTo（会重建页面 → 抖动时无限重建）
  6. 没有 pgl 调用（qlaunch 的服务，applet 调用会挂住）
  7. 可用性检查不依赖 AMS 扩展
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
    """按大括号配平取函数体（不用返回类型正则 —— 那上面反复出错）"""
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
            if ";" in prefix or "}" in prefix or "=" in prefix:
                continue
            i = idx + len(target) + 1
            dp = 1
            while i < len(text) and dp > 0:
                if text[i] == "(":
                    dp += 1
                elif text[i] == ")":
                    dp -= 1
                i += 1
            if dp != 0:
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
    print("=== 「Fizeau 未运行」安全性核查 ===\n")

    main_cpp = strip_comments((SRC / "main.cpp").read_text(encoding="utf-8"))
    gui_cpp = strip_comments((SRC / "gui.cpp").read_text(encoding="utf-8"))
    ipc_cpp = strip_comments((SRC / "fizeau_ipc.cpp").read_text(encoding="utf-8"))
    allsrc = main_cpp + gui_cpp + ipc_cpp

    # ── 1. 每个 IPC 函数都有会话守卫 ──
    print("[1. 每个 IPC 函数内部都有会话守卫]")
    n_ipc = n_guarded = 0
    unguarded = []
    for m in re.finditer(
            r'^(?:inline\s+)?(?:Result|void|bool)\s+(\w+)\s*\([^;{]*\)\s*\{',
            ipc_cpp, re.M):
        fname = m.group(1)
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
            else:
                unguarded.append(fname)
    ck(n_ipc > 0, f"找到 {n_ipc} 个 IPC 函数")
    ck(n_guarded == n_ipc,
       f"全部都有 session_ready() 守卫（实际 {n_guarded}/{n_ipc}）",
       f"缺守卫: {unguarded} —— 会话不存在时会拿空句柄发请求")

    # ── 2. 「没运行就不连」是核心保证 ──
    print()
    print("[2. 服务没运行时，零 IPC —— 这是本插件的核心保证]")

    probe = ROOT / "overlay" / "src" / "fnx_probe.hpp"
    ck(probe.is_file(), "存在注册探测 fnx_probe.hpp")
    if probe.is_file():
        pt = probe.read_text(encoding="utf-8")
        ck("smRegisterService(" in pt and "smUnregisterService(" in pt,
           "探测用 smRegisterService（成功则立刻撤销）",
           "注册命令只写 sm 名字表，不建立客户端会话 —— "
           "参考 sys-clk overlay 的 sysclkIpcRunning()")
        ck("smSessionReady()" in pt,
           "先确认 sm 会话有效",
           "否则会把「sm 没起来」误判成「服务在运行」")

    # createUI 的完整函数体
    cui_f = get_function(gui_cpp, "MainGui::createUI")
    ck(cui_f is not None, "找得到 MainGui::createUI()")
    if cui_f:
        ck("isFizeauRunning()" in cui_f, "用探测结果决定显示哪一页")
        guarded = re.search(
            r'if\s*\(\s*running\s*\)\s*\{[^}]*?connect_fizeau\(\)',
            cui_f, re.S) is not None
        ck(guarded,
           "connect_fizeau() 只在 if (running) 里调用",
           "★ 服务没运行时不发任何 IPC —— 这就是「检测没启动提示，"
           "启动不该崩溃」")

        # 调用次数必须恰好一次（多于一次说明可能还有别处无条件调用）
        #
        # ⚠ 不用变长 look-behind —— Python 的 re 不支持，会抛
        #   "look-behind requires fixed-width pattern"。
        #   改为数调用次数，配合上面"必须在 if (running) 里"就已足够。
        n_calls = len(re.findall(r'connect_fizeau\s*\(\s*\)', cui_f))
        # 减去函数定义那一处（如果有）
        n_calls -= len(re.findall(r'bool\s+connect_fizeau\s*\(\s*\)', cui_f))
        ck(n_calls == 1,
           f"connect_fizeau() 在 createUI 里恰好被调用 1 次（实际 {n_calls}）",
           "多于 1 次说明可能还有别处无条件调用 —— 那正是要避免的")

    cf = get_function(gui_cpp, "connect_fizeau")
    ck(cf is not None, "找得到 connect_fizeau()")
    if cf:
        ck("fzInitialize(" in cf and "R_FAILED" in cf,
           "connect_fizeau() 发起连接并检查返回值")

    rs_f = get_function(gui_cpp, "refresh_state")
    if rs_f:
        ck("fzInitialize(" not in rs_f,
           "refresh_state() 不含连接（它在 update() 里被周期调用）")

    ck("fnxLog" in main_cpp and "fnxLog" in gui_cpp,
       "main.cpp 与 gui.cpp 都写逐步日志")

    # ── 3. fzInitialize 失败时必须清理 ──
    print()
    print("[3. fzInitialize() 失败时清理状态]")
    fi = get_function(ipc_cpp, "fzInitialize")
    ck(fi is not None, "找得到 fzInitialize() 实现")
    if fi:
        ck("g_session = {}" in fi, "失败时清零句柄",
           "不清零的话 session_ready() 可能仍返回 true，守卫形同虚设")
        ck("g_initialized = false" in fi, "失败时清除 initialized 标志")
        ck("smGetService(" in fi, "用 smGetService 建立会话")

    guard = get_function(ipc_cpp, "session_ready")
    ck(guard is not None, "找得到 session_ready()")
    if guard:
        ck("g_initialized" in guard and "serviceIsActive" in guard,
           "守卫同时看标志位与服务有效性",
           "只看标志位不够: 服务可能在运行中被杀掉")

    # ── 4. 引导页零交互 ──
    print()
    print("[4. 引导页零按钮、零回调]")
    cui = get_function(gui_cpp, "MainGui::createUI")
    ck(cui is not None, "找得到 MainGui::createUI()")
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
        ck(bool(guide), "找得到引导页分支")
        ck("setClickListener" not in guide, "引导页没有按钮回调",
           "回调里的 pgl 调用曾导致**点下去卡死**")
        ck("fzInitialize" not in guide and "serviceDispatch" not in guide,
           "引导页里没有 IPC 调用")

    # ── 5. update() 里没有 changeTo ──
    print()
    print("[5. update() 里不重建页面]")
    upd = get_function(gui_cpp, "MainGui::update") or \
          get_function(gui_cpp, "update")
    ck(upd is not None, "找得到 MainGui::update()")
    if upd:
        ck("changeTo" not in upd, "不含 changeTo",
           "在 update 里重建页面 = 状态抖动时无限重建")
        ck(re.search(r'if\s*\(\s*!g_state\.service_ok\s*\)\s*\n?\s*return', upd)
           is not None,
           "未连接时直接 return")

    # ── 6. 没有 pgl ──
    print()
    print("[6. 没有 pgl 调用]")
    ck("pglLaunchProgram(" not in allsrc and "pglInitialize(" not in allsrc,
       "代码里没有 pgl",
       "pgl 是 qlaunch 的服务；从 applet 调用会**挂住**（真机实测卡死）")

    # ── 7. 可用性检查不依赖 AMS 扩展 ──
    print()
    print("[7. 可用性检查只用最基础路径]")
    avail = get_function(ipc_cpp, "fzIsAvailable")
    if avail:
        ck("tipcDispatch" not in avail and "smGetServiceSessionTipc" not in avail,
           "不使用 TIPC / AMS 扩展")

    print()
    print("=" * 62)
    if fails:
        print(f"结果: ★ {fails} 项安全性不满足")
        return 1
    print("结果: 安全性核查通过")
    print()
    print("      · 每个 IPC 函数有守卫（拿不到会话就返回错误）")
    print("      · 连接失败时清理状态，不会用空句柄发请求")
    print("      · 引导页零交互（pgl 已移除，不会再卡死）")
    print("      · update() 不重建页面")
    return 0


if __name__ == "__main__":
    sys.exit(main())
