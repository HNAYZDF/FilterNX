#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_ipc_guards.py — 确保每个 IPC 函数都有会话守卫（防止崩溃回归）

═══════════════════════════════════════════════════════════════════════════
这个检查为什么必须存在
═══════════════════════════════════════════════════════════════════════════
真实故障: 机器上没装 / 没运行 Fizeau 时，一打开插件，**整个特斯拉菜单崩掉**。

根因是所有 IPC 函数都直接用 g_session 发请求，**没检查会话是否建立**:

    Result fzGetIsActive(bool *out) {
        u8 tmp = 0;
        auto rc = serviceDispatchOut(&g_session, 0, tmp);   // ← 空句柄，崩
    }

fzInitialize() 失败时 g_session 是全零（无效句柄）。

⚠ 这类 bug 的可怕之处: **在没有 Fizeau 的机器上才复现**。
   开发机上装了 Fizeau，跑一百次都不会崩。
   所以它只能靠**静态检查**守住，不能靠"我测试过了"。

本脚本逐函数扫描 fizeau_ipc.cpp:
  1. 列出所有会发 IPC 的函数（含 serviceDispatch* 调用）
  2. 每个这样的函数体内**必须**出现 session_ready() 检查
  3. 检查 __ 会话失败时的错误码不是 0（返回 0 会被当成成功）
  4. 检查 fzInitialize 失败时会清零句柄（否则守卫形同虚设）
"""

import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
CPP = ROOT / "overlay" / "src" / "fizeau_ipc.cpp"
HPP = ROOT / "overlay" / "src" / "fizeau_ipc.hpp"

checks = 0
fails = 0


def ck(cond, label, detail=""):
    global checks, fails
    checks += 1
    if cond:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}" + (f"\n        {detail}" if detail else ""))
        fails += 1


def strip_comments(text):
    """去掉 // 行注释与 /* */ 块注释。

    ⚠ 必须先剥注释再解析函数 —— 否则注释里出现的**示例代码**会被当成真函数。
      本文件注释里正好有一段反例:
          //     Result fzGetIsActive(bool *out) {
          //         auto rc = serviceDispatchOut(&g_session, 0, tmp);   // ← 空句柄！
      第一版解析器把这段注释当成了真函数，于是"某些函数没守卫"、
      而真正的 session_ready 反而没被切出来 —— 结论全错。
    """
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    text = re.sub(r'//[^\n]*', '', text)
    return text


def split_functions(text):
    """粗略地把 .cpp 切成 {函数名: 函数体}

    够用即可: 本项目里函数都是顶层 `Result fnx(...) { ... }` 形式，
    用大括号配平来切分。传入前请先 strip_comments()。
    """
    out = {}
    for m in re.finditer(
            r'^(?:inline\s+)?(?:Result|void|bool)\s+(\w+)\s*\([^;{]*\)\s*\{',
            text, re.M):
        name = m.group(1)
        i = m.end() - 1          # 指向 '{'
        depth = 0
        for j in range(i, len(text)):
            if text[j] == '{':
                depth += 1
            elif text[j] == '}':
                depth -= 1
                if depth == 0:
                    out[name] = text[i:j + 1]
                    break
    return out


def main():
    print("=== IPC 会话守卫检查（防崩溃回归）===\n")

    if not CPP.is_file():
        print(f"  找不到 {CPP}")
        return 1
    text = CPP.read_text(encoding="utf-8")
    # 先剥注释再切函数 —— 否则注释里的示例代码会被当成真函数
    code = strip_comments(text)
    funcs = split_functions(code)

    # ── 1. 找出所有会发 IPC 的函数 ──
    print("[会发 IPC 的函数]")
    ipc_funcs = {}
    for name, body in funcs.items():
        # 排除守卫函数自身与初始化/关闭
        if name in ("session_ready", "fzInitialize", "fzExit", "fzIsSessionReady"):
            continue
        if re.search(r'\bserviceDispatch(In|Out|InOut)\s*\(', body):
            ipc_funcs[name] = body

    if not ipc_funcs:
        ck(False, "找得到 IPC 函数", "一个都没找到 —— 正则可能失效了")
    for name in sorted(ipc_funcs):
        print(f"        · {name}")

    # ── 2. 每个都必须有守卫 ──
    print("\n[每个 IPC 函数都必须先检查会话]")
    for name, body in sorted(ipc_funcs.items()):
        has_guard = "session_ready()" in body
        # 守卫必须在第一条 serviceDispatch 之前
        first_dispatch = body.find("serviceDispatch")
        guard_pos = body.find("session_ready()")
        before = guard_pos >= 0 and guard_pos < first_dispatch
        ck(before,
           f"{name} 在发请求前检查 session_ready()",
           "缺少守卫 —— 没有 Fizeau 时会拿空句柄发 IPC，导致菜单崩溃")

    # ── 3. 失败错误码不能是 0 ──
    print("\n[无会话时返回的错误码]")
    m = re.search(r'RC_NO_SESSION\s*=\s*([^;]+);', text)
    if not m:
        ck(False, "定义了 RC_NO_SESSION", "找不到定义")
    else:
        expr = m.group(1).strip()
        print(f"        RC_NO_SESSION = {expr}")
        # 必须是 MAKERESULT(...) 而不是字面 0
        ck(expr != "0" and "MAKERESULT" in expr,
           "RC_NO_SESSION 是非零且可辨认的错误码",
           "若为 0，调用方会以为操作成功 —— 界面显示已生效而实际什么都没做，"
           "比崩溃更难查")

    # ── 4. fzInitialize 失败时必须清零句柄 ──
    print("\n[fzInitialize 失败时的清理]")
    init = funcs.get("fzInitialize", "")
    ck("g_session = {}" in init,
       "fzInitialize 失败时清零句柄",
       "不清零的话 session_ready() 可能仍返回 true，守卫形同虚设")
    ck("g_initialized = false" in init,
       "fzInitialize 失败时清除 initialized 标志")

    # ── 5. 头文件里声明了 fzIsSessionReady ──
    print("\n[接口声明]")
    hpp = HPP.read_text(encoding="utf-8")
    ck("fzIsSessionReady" in hpp, "头文件声明了 fzIsSessionReady()")
    ck("fzIsSessionReady" in text, "实现里定义了 fzIsSessionReady()")

    # ── 6. 守卫函数自身要同时看 initialized 与 serviceIsActive ──
    print("\n[守卫函数本身]")
    guard = funcs.get("session_ready", "")
    ck("g_initialized" in guard and "serviceIsActive" in guard,
       "session_ready() 同时检查 initialized 标志与服务有效性",
       "只看标志位不够: 服务可能在运行中被杀掉，此时句柄已失效")

    print("\n" + "=" * 60)
    print(f"检查项: {checks}   失败: {fails}")
    print("结果: " + ("所有 IPC 函数都有会话守卫" if fails == 0
                     else "★ 存在无守卫的 IPC 函数 —— 无 Fizeau 时会崩溃"))
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
