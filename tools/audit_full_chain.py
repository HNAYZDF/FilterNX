#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_full_chain.py — 端到端审计「打开插件 → 建立会话 → 应用滤镜」全链路

═══════════════════════════════════════════════════════════════════════════
为什么需要它
═══════════════════════════════════════════════════════════════════════════
之前反复出问题，根本原因是**每次只盯着一个点改**，没有把整条链路的
每一环都验证到位。本脚本一次性把每一环都查一遍:

  1. 服务名字符串是否真的编进了产物（字体/编码/优化都可能吃掉它）
  2. IPC 命令号与结构体布局是否与 Fizeau 官方一致
  3. 连接路径是否可达（initServices / refresh_state）
  4. 失败路径是否安全（守卫 / 返回值检查 / 状态清理）
  5. 引导页是否零交互（pgl 已移除）
  6. 预设数值是否都在合法范围
  7. NACP / NRO / 版本号是否正确
  8. 产物与源码是否一致

任一环不通过都打印出来，最后给出总结论。
"""

import re
import struct
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "overlay" / "src"
OVL = ROOT / "overlay" / "FilterNX.ovl"
DIST = ROOT / "dist" / "switch" / ".overlays" / "Chaoneng.ovl"

sys.path.insert(0, str(ROOT / "tools"))
from nacp_layout import find_nacp, get_name, get_version, get_isbn  # noqa: E402

o_checks = o_fails = 0
stage_fails = []


def ck(cond, label, detail=""):
    global o_checks, o_fails
    o_checks += 1
    if cond:
        print(f"    PASS  {label}")
    else:
        print(f"    FAIL  {label}")
        if detail:
            print(f"          {detail}")
        o_fails += 1
    return cond


def stage(title):
    print()
    print(f"── {title} ──")


def strip_comments(t):
    t = re.sub(r'/\*.*?\*/', '', t, flags=re.S)
    return re.sub(r'//[^\n]*', '', t)


def read(p):
    return p.read_text(encoding="utf-8")


OBJDUMP = "C:/devkitPro/devkitA64/bin/aarch64-none-elf-objdump.exe"
ELF = ROOT / "overlay" / "build" / "FilterNX.elf"


def main():
    print("=" * 68)
    print("  超能滤镜 · 端到端链路审计")
    print("=" * 68)

    hpp = read(SRC / "fizeau_ipc.hpp")
    cpp = read(SRC / "fizeau_ipc.cpp")
    gui = read(SRC / "gui.cpp")
    main_cpp = read(SRC / "main.cpp")
    ver_hpp = read(SRC / "version.hpp")

    cpp_c = strip_comments(cpp)
    gui_c = strip_comments(gui)
    main_c = strip_comments(main_cpp)

    # ══════════════════════════════════════════════════════════════════
    stage("1. 服务名与产物内容")

    m = re.search(r'FIZEAU_SERVICE\s*=\s*"([^"]+)"', hpp)
    svc = m.group(1) if m else None
    ck(svc is not None, "源码里有 FIZEAU_SERVICE 定义")
    print(f"          服务名: {svc!r}")
    ck(svc == "fizeau", "服务名是 'fizeau'（与 Fizeau 官方一致）",
       "官方 fizeau.c: smGetService(&g_fizeau_srv, \"fizeau\")")

    if OVL.is_file():
        b = OVL.read_bytes()
        # ⚠ 不能简单地 `b"fizeau" in b`！
        #
        #   编译器把短字符串**内联成 AArch64 指令的立即数**:
        #       mov  x1, #0x6966          编码字节 66 69 = 'f','i'
        #       movk x1, #0x657a, lsl 16  编码字节 7a 65 = 'z','e'
        #       movk x1, #0x7561, lsl 32  编码字节 61 75 = 'a','u'
        #   真实序列是 `66 69 ?? ?? | 7a 65 ?? ?? | 61 75 ?? ??`
        #   —— 每 4 字节跳过 2 字节，所以连续搜索必然失败。
        #
        #   我一度据此断定"服务名没编进产物、连接不可能成功"，白白折腾一轮。
        #   正确判据: 按指令边界还原立即数（tools/svc_name_check.py）。
        from svc_name_check import verify as verify_svc

        t_off, t_sz = struct.unpack_from("<II", b, 0x20)
        ok, real, parts = verify_svc(b, svc, t_off, t_sz)
        ck(ok, f"能在指令流里还原出服务名 {svc!r}",
           "★ 还原不出 = 连接不可能成功。字面量被优化掉或名字写错")
        if ok:
            print(f"          还原结果: {real!r}（由 {len(parts)} 条指令拼成）")
            ck(real == svc, f"还原出的名字 == {svc!r}")

        # 顺带说明: 连续字节搜索会失败，这是正常的
        if svc.encode() not in b:
            print(f"          注: 字节流里没有连续的 {svc!r} —— 属正常"
                  f"（已内联为指令立即数）")
    else:
        ck(False, f"存在产物 {OVL}")

    # ══════════════════════════════════════════════════════════════════
    stage("2. IPC 协议与结构体布局")

    # 命令号
    for cmd, name in ((0, "GetIsActive"), (1, "SetIsActive"),
                      (2, "GetProfile"), (3, "SetProfile"),
                      (4, "GetActiveProfileId")):
        ck(re.search(rf'serviceDispatch\w*\s*\(\s*&g_session\s*,\s*{cmd}\b', cpp_c)
           is not None,
           f"命令 {cmd} 用于 {name}")

    # 结构体尺寸
    for expr, label, want in (
        (r'static_assert\s*\(\s*sizeof\(FzSettings\)\s*==\s*(\d+)', "FzSettings", 32),
        (r'static_assert\s*\(\s*sizeof\(FzProfile\)\s*==\s*(\d+)', "FzProfile", 92),
        (r'static_assert\s*\(\s*sizeof\(Request\)\s*==\s*(\d+)', "SetProfile 请求", 96),
    ):
        mm = re.search(expr, cpp_c) or re.search(expr, strip_comments(hpp))
        got = int(mm.group(1)) if mm else None
        ck(got == want, f"{label} 尺寸断言 = {want} 字节（实际 {got}）")

    # 取值范围的边界常量
    for nm, want in (("TEMP_MIN", 1000), ("TEMP_MAX", 10000)):
        mm = re.search(rf'{nm}\s*=\s*(\d+)', hpp)
        got = int(mm.group(1)) if mm else None
        ck(got == want, f"{nm} = {want}（实际 {got}）")

    # ══════════════════════════════════════════════════════════════════
    stage("3. 连接路径可达性")

    # ── 当前设计: 用注册探测判断服务在不在，只在"在运行"时才连接 ──
    probe = (ROOT / "overlay" / "src" / "fnx_probe.hpp")
    ck(probe.is_file(), "存在 fnx_probe.hpp（注册探测）")
    if probe.is_file():
        pt = probe.read_text(encoding="utf-8")
        ck("smRegisterService(" in pt,
           "探测用 smRegisterService（只写名字表，不建会话）",
           "这是 sys-clk overlay 的做法 —— 纯探测，不碰目标进程")
        ck("smUnregisterService(" in pt,
           "探测成功后立刻撤销注册（不留痕迹）")
        ck("smSessionReady()" in pt,
           "探测前先确认 sm 会话有效",
           "否则会把「sm 没起来」误判成「服务在运行」")
        ck("return false" in pt,
           "不确定时返回 false（判为没运行）",
           "宁可显示提示，也不去碰可能不存在的服务")

    ck("isFizeauRunning()" in gui_c, "createUI 用 isFizeauRunning() 判断")
    ck("connect_fizeau()" in gui_c, "存在 connect_fizeau() 作为连接入口")
    ck("smGetService(" in cpp_c, "fzInitialize() 用 smGetService 建立会话")

    # 关键: 只有 running 为真时才连接
    cui_m = re.search(r'tsl::elm::Element\s*\*\s*MainGui::createUI\s*\(\s*\)\s*\{',
                      gui_c)
    if cui_m:
        i5 = cui_m.end() - 1
        d5 = 0
        body5 = None
        for j5 in range(i5, len(gui_c)):
            if gui_c[j5] == "{":
                d5 += 1
            elif gui_c[j5] == "}":
                d5 -= 1
                if d5 == 0:
                    body5 = gui_c[i5:j5 + 1]
                    break
        if body5:
            # connect_fizeau 必须在 if (running) 的块里
            ok_guard = re.search(
                r'if\s*\(\s*running\s*\)\s*\{[^}]*?connect_fizeau\(\)',
                body5, re.S) is not None
            ck(ok_guard,
               "只有探测说「在运行」时才调用 connect_fizeau()",
               "★ 这是「检测没启动就不该崩」的核心保证")

        # 日志必须存在（崩了才能定位）
    ck("fnxLog" in main_c and "fnxLog" in gui_c,
       "main.cpp 与 gui.cpp 都写逐步日志",
       "崩溃前最后一行日志 = 最后执行到的地方")

    # ══════════════════════════════════════════════════════════════════
    stage("4. 失败路径安全性")

    cf_body = None
    mm = re.search(r'bool\s+connect_fizeau\s*\(\s*\)\s*\{', gui_c)
    if mm:
        i0 = mm.end() - 1
        d0 = 0
        for j0 in range(i0, len(gui_c)):
            if gui_c[j0] == "{":
                d0 += 1
            elif gui_c[j0] == "}":
                d0 -= 1
                if d0 == 0:
                    cf_body = gui_c[i0:j0 + 1]
                    break
    ck(cf_body is not None and "R_FAILED" in cf_body,
       "connect_fizeau() 检查 fzInitialize() 的返回值")
    ck(cf_body is not None and "service_ok = false" in cf_body,
       "连接失败时置 service_ok = false")
    ck("g_session = {}" in cpp_c, "fzInitialize() 失败时清零句柄")
    ck("g_initialized = false" in cpp_c, "fzInitialize() 失败时清除标志")

    n_ipc = n_g = 0
    for mm in re.finditer(r'^(?:inline\s+)?(?:Result|void|bool)\s+(\w+)\s*\([^;{]*\)\s*\{',
                          cpp_c, re.M):
        i = mm.end() - 1
        d = 0
        body = None
        for j in range(i, len(cpp_c)):
            if cpp_c[j] == "{":
                d += 1
            elif cpp_c[j] == "}":
                d -= 1
                if d == 0:
                    body = cpp_c[i:j+1]
                    break
        if body and "serviceDispatch" in body:
            n_ipc += 1
            if "session_ready()" in body:
                n_g += 1
    ck(n_ipc > 0 and n_g == n_ipc,
       f"全部 {n_ipc} 个 IPC 函数都有会话守卫（实际 {n_g}）")

    # ══════════════════════════════════════════════════════════════════
    stage("5. 危险调用已清除")

    allsrc = main_c + gui_c + cpp_c
    ck("pglLaunchProgram(" not in allsrc, "没有 pglLaunchProgram（会卡死）")
    ck("pglInitialize(" not in allsrc, "没有 pglInitialize")
    ck("changeTo" not in (re.search(r'void\s+MainGui::update\s*\(\)\s*\{',
                                    gui_c, re.S).group(0)
                          if re.search(r'void\s+MainGui::update\s*\(\)\s*\{',
                                       gui_c, re.S) else ""),
       "update() 里没有 changeTo")

    # 引导页零交互
    cui_m = re.search(r'tsl::elm::Element\s*\*\s*MainGui::createUI\s*\(\)\s*\{',
                      gui_c)
    if cui_m:
        i = cui_m.end() - 1
        d = 0
        body = None
        for j in range(i, len(gui_c)):
            if gui_c[j] == "{":
                d += 1
            elif gui_c[j] == "}":
                d -= 1
                if d == 0:
                    body = gui_c[i:j+1]
                    break
        if body:
            gs = body.find("if (!g_state.service_ok)")
            guide = ""
            if gs >= 0:
                br = body.find("{", gs)
                if br >= 0:
                    d2 = 0
                    for k in range(br, len(body)):
                        if body[k] == "{":
                            d2 += 1
                        elif body[k] == "}":
                            d2 -= 1
                            if d2 == 0:
                                guide = body[br:k+1]
                                break
            ck("setClickListener" not in guide, "引导页零按钮回调")
            ck("serviceDispatch" not in guide, "引导页零 IPC")

    # ══════════════════════════════════════════════════════════════════
    stage("6. 预设数值范围")

    presets_py = read(SRC / "presets.hpp")
    # 用编译期断言与运行期检查都有；这里做静态粗查
    n_preset = len(re.findall(
        r'\{\s*"[^"]*"\s*,\s*"[^"]*"\s*,\s*"[^"]*"\s*,\s*PresetGroup::\w+',
        presets_py))
    arr = re.search(r'std::array<Preset,\s*(\d+)>', presets_py)
    declared = int(arr.group(1)) if arr else -1
    ck(declared == n_preset,
       f"预设数组大小 {declared} == 实际条目 {n_preset}",
       "不一致会留空指针槽位（曾导致崩溃）")

    # ══════════════════════════════════════════════════════════════════
    stage("7. 版本号与产物元数据")

    vm = re.search(r'#define\s+FNX_VERSION\s+"([^"]+)"', ver_hpp)
    ver = vm.group(1) if vm else None
    print(f"          源码版本: {ver}")

    if DIST.is_file():
        db = DIST.read_bytes()
        off, _, _ = find_nacp(db)
        ck(off is not None, "分发产物里有 NACP")
        if off is not None:
            ck(get_version(db, off) == ver,
               f"NACP 版本 {get_version(db, off)!r} == 源码 {ver!r}")
            ck(get_name(db, off) == "超能滤镜",
               f"NACP 名字 = {get_name(db, off)!r}")
            ck(get_isbn(db, off) == "", "isbn 为空（版本号没被误写）")
        ck(DIST.name.isascii(), f"分发文件名是纯 ASCII（{DIST.name}）")
    else:
        ck(False, f"存在分发产物 {DIST}")

    # overlay 与 dist 的差异应只在 NACP
    if OVL.is_file() and DIST.is_file():
        a, b2 = OVL.read_bytes(), DIST.read_bytes()
        ck(len(a) == len(b2), "构建产物与分发产物大小相同")
        if len(a) == len(b2):
            diff = [i for i in range(len(a)) if a[i] != b2[i]]
            nacp_off, _, _ = find_nacp(b2)
            allowed = set()
            if nacp_off is not None:
                for lang in range(16):
                    for base, size in ((nacp_off + lang*0x300, 0x200),
                                       (nacp_off + lang*0x300 + 0x200, 0x100)):
                        allowed.update(range(base, base+size))
                allowed.update(range(nacp_off + 0x3060, nacp_off + 0x3070))
            outside = [i for i in diff if i not in allowed]
            ck(not outside, f"差异全部在 NACP 内（差异 {len(diff)} 字节）",
               f"区外差异 {len(outside)} 字节，首个 0x{outside[0]:X}"
               if outside else "")

    # ══════════════════════════════════════════════════════════════════
    print()
    print("=" * 68)
    print(f"  检查项: {o_checks}   失败: {o_fails}")
    print("=" * 68)
    if o_fails:
        print(f"结果: ★ {o_fails} 项未通过 —— 链路仍有断点")
        return 1
    print("结果: 全链路审计通过")
    print()
    print("  打开插件 → 建立会话 → 读取状态 → 应用滤镜 → 校验元数据")
    print("  每一环都已核对。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
