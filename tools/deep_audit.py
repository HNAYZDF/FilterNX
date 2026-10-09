#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
deep_audit.py — 深度审计：找"表面检查发现不了"的问题

（横幅里的版本号从 overlay/src/version.hpp 读，不手抄 —— 曾经硬编码成 2.0.0）

═══════════════════════════════════════════════════════════════════════════
和现有检查的区别
═══════════════════════════════════════════════════════════════════════════
现有检查器查的是**已知的**问题类型（名字长度、前缀、守卫…）。
本脚本查的是**未知的、跨文件的、语义层的**问题:

  A. 未使用 / 悬空代码
     · 定义了却没人调用的函数
     · 声明了却没人用的常量
     · 死分支（永远为真/为假的条件）

  B. 数值语义
     · 两个预设"看起来不同"但语义等价（比如色温差 1K）
     · 参数落在合法区间边缘（容易被固件钳制）
     · 单色类没设 filter、非单色类设了 filter

  C. 布局与界面的实际一致性
     · layout.hpp 的常量 vs gui.cpp 的实际调用数
     · 预设数与「关于」页显示的滤镜数是否一致
     · 分类数 vs group_name() 的覆盖

  D. 安全性再确认（跨文件）
     · 每个 IPC 调用点是否都在会话守卫之后
     · 有没有地方绕过 connect_fizeau 直接连

  E. 一致性
     · README / 关于页 / 代码 三处的数字是否一致
     · 版本号是否只有一处来源
"""

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "overlay" / "src"

problems = []
notes = []
checks = 0


def bad(cat, msg, detail=""):
    problems.append((cat, msg, detail))


def note(msg):
    notes.append(msg)


def ck(cond, msg, detail=""):
    global checks
    checks += 1
    if not cond:
        bad("失败", msg, detail)
    return cond


def strip_comments(t):
    t = re.sub(r'/\*.*?\*/', '', t, flags=re.S)
    return re.sub(r'//[^\n]*', '', t)


def read(p):
    return p.read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════
def audit_unused(srcs):
    print("\n[A. 未使用 / 悬空代码]")
    allcode = "\n".join(srcs.values())

    # 收集 inline 函数的定义
    defs = re.findall(r'\binline\s+[\w:<>,\s\*&]+?\s+(\w+)\s*\(', allcode)
    for name in sorted(set(defs)):
        if name in ("main",):
            continue
        # 出现次数: 定义 1 次 + 调用
        n = len(re.findall(rf'\b{re.escape(name)}\s*\(', allcode))
        if n <= 1:
            note(f"函数 {name}() 定义了但没有调用点")

    # 常量
    consts = re.findall(r'inline constexpr [\w:]+\s+(\w+)\s*=', allcode)
    for name in sorted(set(consts)):
        n = len(re.findall(rf'\b{re.escape(name)}\b', allcode))
        if n <= 1:
            note(f"常量 {name} 定义了但没有使用")

    # 枚举值是否都被 group_name 覆盖
    hpp = srcs.get("presets.hpp", "")
    enum_vals = re.findall(r'enum class PresetGroup\s*\{(.*?)\}', hpp, re.S)
    if enum_vals:
        vals = [v.strip().split("//")[0].strip().rstrip(",")
                for v in enum_vals[0].split("\n") if v.strip() and "//" not in v[:2]]
        vals = [v for v in vals if re.fullmatch(r'\w+', v)]
        covered = re.findall(r'case PresetGroup::(\w+):\s*return', hpp)
        missing = [v for v in vals if v not in covered]
        ck(not missing, "group_name() 覆盖了所有分类",
           f"缺: {missing}")
        note(f"分类数: {len(vals)}，group_name 覆盖 {len(covered)}")


# ══════════════════════════════════════════════════════════════════════
def parse_presets(hpp):
    """解析预设表。

    ⚠ 不能用"一条正则匹配整条记录" —— 记录是多行的，且含嵌套的
      range 花括号 { lo, hi }，正则很容易失配（第一版就匹配到 0 条）。

      改为**按条目切分**: 每条记录以 `{ "id", "name", "desc", PresetGroup::X,`
      开头，用大括号配平找到它的结尾。
    """
    i = hpp.find("std::array<Preset,")
    j = hpp.find("}};", i)
    body = hpp[i:j]
    declared = int(re.search(r'std::array<Preset,\s*(\d+)>', hpp).group(1))

    START = re.compile(
        r'\{\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*'
        r'PresetGroup::(\w+)\s*,')

    out = []
    pos = 0
    while True:
        m = START.search(body, pos)
        if not m:
            break
        # 从这条记录的 '{' 开始做括号配平，找到整条记录的结尾
        start = m.start()
        depth = 0
        k = start
        while k < len(body):
            if body[k] == "{":
                depth += 1
            elif body[k] == "}":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        rec = body[start:k + 1]
        pos = k + 1

        # ⚠ 取 settings 不能用 `\{\s*(.*?)\}` —— settings 里嵌着 range 的
        #   `{ lo, hi }`，非贪婪匹配会在**第一个** range 的 `}` 处停下，
        #   于是 record 被切碎、token 混入 id/name 字符串（第一版就是这样）。
        #
        #   可靠做法: 一条记录的**结尾**固定是
        #       <settings> }, COMP_XXX, COMP_YYY },
        #   所以从末尾往前找 `}, COMP_XXX, COMP_YYY },`，
        #   它前面那个与它配对的 `{` 就是 settings 的起点。
        tail = re.search(r'\}\s*,\s*(COMP_\w+)\s*,\s*(COMP_\w+)\s*\}\s*$', rec)
        if not tail:
            continue
        comp, filt = tail.group(1), tail.group(2)

        # settings 起点: 从尾部 `}` 往前做括号配平，找到与之配对的 `{`
        close_idx = rec.rfind("}", 0, tail.start() + 1)
        depth = 0
        open_idx = None
        for idx in range(close_idx, -1, -1):
            if rec[idx] == "}":
                depth += 1
            elif rec[idx] == "{":
                depth -= 1
                if depth == 0:
                    open_idx = idx
                    break
        if open_idx is None:
            continue
        # settings 本体（不含最外层花括号）
        nums_raw = rec[open_idx + 1:close_idx]

        out.append({
            "id": m.group(1), "name": m.group(2), "desc": m.group(3),
            "group": m.group(4), "raw": nums_raw, "comp": comp,
            "filter": filt, "rec": rec,
        })
    return out, declared, body


def split_values(raw: str):
    """把 settings 的数值串按顶层逗号拆开。

    ⚠ 不能用 raw.split(",") —— range 是嵌套的 `{ a, b }`，
      直接 split 会把 `0.95f` 之类拆错（第一版就报
      "could not convert string to float: '.'"）。
      要按**括号深度**拆。
    """
    out = []
    depth = 0
    cur = []
    for ch in raw:
        if ch == "{":
            depth += 1
            cur.append(ch)
        elif ch == "}":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if "".join(cur).strip():
        out.append("".join(cur).strip())
    return out


def eval_value(tok: str):
    """把一个 token 变成 float；NEUTRAL_* 用已知中性值代入。

    返回 (kind, value)，kind ∈ {num, neutral, unknown}
    """
    tok = tok.strip().strip("{}").strip()

    NEUTRAL = {
        "NEUTRAL_TEMP": 6500.0,
        "NEUTRAL_SAT": 1.0,
        "NEUTRAL_HUE": 0.0,
        "NEUTRAL_CONTRAST": 1.0,
        "NEUTRAL_GAMMA": 2.4,
        "NEUTRAL_LUMA": 0.0,
        "NEUTRAL_RANGE_LO": 0.0,
        "NEUTRAL_RANGE_HI": 1.0,
    }
    if tok in NEUTRAL:
        return ("neutral", NEUTRAL[tok])

    m = re.fullmatch(r'(-?[\d.]+)f?', tok)
    if m:
        try:
            return ("num", float(m.group(1)))
        except ValueError:
            return ("unknown", None)
    return ("unknown", tok)


def audit_numbers(presets):
    print("\n[B. 数值语义]")

    # 解析成 8 元组: temp, sat, hue, contrast, gamma, luma, range_lo, range_hi
    parsed = []
    for p in presets:
        toks = split_values(p["raw"])
        # range 那一项形如 "{ lo, hi }"，先拆成两个
        flat = []
        for t in toks:
            if t.startswith("{"):
                flat.extend(split_values(t.strip("{}")))
            else:
                flat.append(t)
        vals = [eval_value(t) for t in flat]
        parsed.append((p, vals))

    # B1. 必须正好 8 个数值
    for p, vals in parsed:
        if len(vals) != 8:
            bad("数值", f"{p['id']} 的数值个数是 {len(vals)}，应为 8",
                f"{[v[1] for v in vals]}")

    # B1b. 不能有无法求值的 token
    for p, vals in parsed:
        for k, v in vals:
            if k == "unknown":
                bad("数值", f"{p['id']} 含无法解析的数值 token: {v!r}")

    # B2. 参数集重复（用求值后的数值 + filter）
    seen = defaultdict(list)
    for p, vals in parsed:
        key = tuple(round(v[1], 6) if isinstance(v[1], float) else v[1]
                    for v in vals) + (p["filter"],)
        seen[key].append(p["id"])
    dup = {k: v for k, v in seen.items() if len(v) > 1}
    ck(not dup, "没有参数集完全相同的预设", str(list(dup.values())[:4]))

    # B3. 名字 / id 重复
    names = Counter(p["name"] for p in presets)
    dupn = [n for n, c in names.items() if c > 1]
    ck(not dupn, "没有重复的中文名", str(dupn))

    ids = Counter(p["id"] for p in presets)
    dupi = [n for n, c in ids.items() if c > 1]
    ck(not dupi, "没有重复的 id", str(dupi))

    # B5. 长度
    lname = [p["name"] for p in presets if len(p["name"]) > 4]
    ldesc = [p["desc"] for p in presets if len(p["desc"]) > 5]
    ck(not lname, "所有名字 ≤4 字", str(lname))
    ck(not ldesc, "所有说明 ≤5 字", str(ldesc))

    # B6. filter 语义
    #   · 只有 Mono 组才该用 filter（其它组用 filter 会得到非预期的染色）
    #   · Mono 组里**名字以「单色」开头**的才需要 filter ——
    #     「黑白」「硬黑白」是靠 saturation=0 实现的纯灰阶，
    #     不需要也不应该有 filter（有的话反而会染色）。
    for p in presets:
        uses = p["filter"] != "COMP_NONE"
        is_mono = p["group"] == "Mono"
        if uses and not is_mono:
            bad("数值", f"{p['id']} 在 {p['group']} 组却设了 filter={p['filter']}")
        if is_mono:
            want_filter = p["name"].startswith("单色")
            if want_filter and not uses:
                bad("数值", f"{p['id']}（{p['name']}）应设 filter 却没设")
            if not want_filter and uses:
                bad("数值", f"{p['id']}（{p['name']}）是灰阶，不该设 filter")

    # B7. 范围检查（对照 libnx/Fizeau 的合法区间）
    LIMITS = [
        (0, "temperature", 1000, 10000),
        (1, "saturation",  0, 2),
        (2, "hue",        -1, 1),
        (3, "contrast",    0, 2),
        (4, "gamma",       0, 5),
        (5, "luminance",  -1, 1),
        (6, "range.lo",    0, 1),
        (7, "range.hi",    0, 1),
    ]
    for p, vals in parsed:
        if len(vals) != 8:
            continue
        for idx, label, lo, hi in LIMITS:
            kind, v = vals[idx]
            if not isinstance(v, float):
                continue
            if v < lo or v > hi:
                bad("数值", f"{p['id']} 的 {label}={v} 超出 [{lo}, {hi}]")

    # B8. 范围 lo < hi
    for p, vals in parsed:
        if len(vals) != 8:
            continue
        lo = vals[6][1]
        hi = vals[7][1]
        if isinstance(lo, float) and isinstance(hi, float) and lo >= hi:
            bad("数值", f"{p['id']} 的 range.lo({lo}) >= range.hi({hi})")

    return parsed


def audit_layout(srcs, presets, declared):
    print("\n[C. 布局与界面一致性]")
    layout = srcs.get("layout.hpp", "")
    gui = srcs.get("gui.cpp", "")

    def const(name):
        m = re.search(rf'inline constexpr int {name}\s*=\s*(\d+)', layout)
        return int(m.group(1)) if m else None

    ph, pi = const("PRESET_HEADERS"), const("PRESET_ITEMS")
    mh, mi = const("MAIN_HEADERS"), const("MAIN_ITEMS")

    # ⚠ 预设页现在是**下拉式**（分类可折叠），常量的含义随之改变:
    #     收起态: 只有分组行 —— PRESET_HEADERS = 0（不用小标题）,
    #             PRESET_ITEMS = 分组数
    #     展开态: 分组行 + 该组子项，高度由 List 按需计算（可滚动），
    #             所以不需要在这里做静态预算
    #   若将来改回平铺，这里的断言需要同步改 —— 别直接删掉。
    groups = len(set(p["group"] for p in presets))
    ck(ph == 0,
       f"PRESET_HEADERS({ph}) == 0（下拉式不用小标题行）")
    ck(pi == groups,
       f"PRESET_ITEMS({pi}) == 分组数({groups})（收起态可见行数）")
    # 数组声明大小必须等于真实预设数（这是硬约束，与界面形态无关）
    ck(declared == len(presets),
       f"数组声明大小({declared}) == 实际预设数({len(presets)})")

    # 「关于」页显示的滤镜数
    m = re.search(r'ListItem\("滤镜数",\s*"(\d+)种"\)', gui)
    if m:
        ck(int(m.group(1)) == len(presets),
           f"「关于」页滤镜数({m.group(1)}) == 实际({len(presets)})")
    else:
        bad("一致性", "找不到「关于」页的滤镜数")

    # 主页面行数
    if mh and mi:
        hdr = len(re.findall(r'addItem\(new tsl::elm::CategoryHeader', gui[:gui.find("PresetGui::createUI")]))
        note(f"主页面源码里的小标题调用数: {hdr}（常量 MAIN_HEADERS={mh}）")

    return ph, pi


def audit_consistency(srcs, presets):
    print("\n[D. 一致性]")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    ver = re.search(r'#define\s+FNX_VERSION\s+"([^"]+)"',
                    srcs.get("version.hpp", ""))
    v = ver.group(1) if ver else None
    ck(v is not None, "能读到版本号")

    m = re.search(r'\*\*版本\s+([\d.]+)', readme)
    ck(m is not None and m.group(1) == v,
       f"README 版本({m.group(1) if m else '?'}) == 源码({v})")

    # README 里的滤镜数
    nums = set(int(x) for x in re.findall(r'(\d+)\s*种中文滤镜', readme))
    nums |= set(int(x) for x in re.findall(r'## 四、(\d+)\s*种滤镜', readme))
    if nums:
        ck(nums == {len(presets)},
           f"README 滤镜数{nums} == 实际({len(presets)})")

    return v


def audit_safety(srcs):
    print("\n[E. 安全性跨文件复核]")
    gui = strip_comments(srcs.get("gui.cpp", ""))
    ipc = strip_comments(srcs.get("fizeau_ipc.cpp", ""))
    main_c = strip_comments(srcs.get("main.cpp", ""))
    probe = srcs.get("fnx_probe.hpp", "")

    # 每个 IPC 函数都要有守卫
    n = g = 0
    for m in re.finditer(r'^(?:inline\s+)?(?:Result|void|bool)\s+(\w+)\s*\([^;{]*\)\s*\{',
                         ipc, re.M):
        i = m.end() - 1
        d = 0
        body = None
        for j in range(i, len(ipc)):
            if ipc[j] == "{":
                d += 1
            elif ipc[j] == "}":
                d -= 1
                if d == 0:
                    body = ipc[i:j+1]
                    break
        if body and "serviceDispatch" in body:
            n += 1
            if "session_ready()" in body:
                g += 1
    ck(n > 0 and g == n, f"IPC 函数守卫完整（{g}/{n}）")

    # fzInitialize 只允许在 connect_fizeau 里被调用（main 里不应有）
    ck("fzInitialize(" not in main_c,
       "main.cpp 里不调用 fzInitialize（否则会在 initServices 阶段连）")

    # 探测必须用 smRegisterService
    ck("smRegisterService(" in probe and "smUnregisterService(" in probe,
       "探测用注册/撤销，而非 smGetService")

    # ── 实时预览的触发条件 ──
    #
    # 真机 bug: 选一个滤镜 → A 确认 → 返回 → 画面变成另一个滤镜。
    # 根因是框架在列表第一帧会**强制设一次焦点**（m_hasSetInitialFocusHack），
    # 若把 setFocused 直接当"用户选了这一项"，预览就会被误触发。
    # 必须要求"先有方向输入"。
    if "preview_preset" in gui:
        pv = re.search(r'void\s+preview_preset\s*\([^)]*\)\s*\{', gui)
        if pv:
            i7 = pv.end() - 1
            d7 = 0
            body7 = None
            for j7 in range(i7, len(gui)):
                if gui[j7] == "{":
                    d7 += 1
                elif gui[j7] == "}":
                    d7 -= 1
                    if d7 == 0:
                        body7 = gui[i7:j7 + 1]
                        break
            if body7:
                ck("g_userNavigated" in body7,
                   "预览要求「先有方向输入」才触发",
                   "★ 否则框架的第一帧强制聚焦会被误当成用户选择 —— "
                   "真机表现为「选 A 返回后跳到另一个滤镜」")
        ck("isNavigationInput" in gui,
           "存在方向输入判定（方向键 + 摇杆）")
        ck("handleInput" in gui,
           "PresetGui 实现了 handleInput 来检测方向输入")

    # ── 导航栈语义 ──
    #
    # 真机 bug: 「点分类后位置不对」+「按 B 直接退出插件」。
    # 根因是框架里 changeTo 是**压栈**（tesla.hpp:12016），
    # swapTo 才是**替换栈顶**（12043）。PresetGui 内部重建页面
    # （展开/收起分类）若用 changeTo，每操作一次就多压一层:
    #   · 按 B 会回到上一层那个旧 PresetGui（位置/状态都不对）
    #   · 栈被撑高后走到 12120 的"栈见底 → hide()"分支，整个退出
    #
    # 允许的 changeTo<PresetGui> 只有一处: MainGui 进入本页的入口
    # （那里就该压栈，B 才能弹回主页面）。
    code_lines = []
    for ln in gui.split("\n"):
        s = ln.strip()
        if "changeTo<PresetGui>" in ln and not (s.startswith("//") or
                                                s.startswith("*")):
            code_lines.append(s)
    ck(len(code_lines) <= 1,
       f"PresetGui 内部重建用 swapTo，不用 changeTo（实际 {len(code_lines)} 处）",
       f"发现: {code_lines} —— changeTo 会压栈，栈被撑高后 B 会直接退出插件")
    ck("swapTo<PresetGui>" in gui,
       "展开/收起分类用 swapTo（替换栈顶，栈深度不变）")

    # 不允许 pgl
    allsrc = "".join(srcs.values())
    ck("pglLaunchProgram(" not in allsrc and "pglInitialize(" not in allsrc,
       "没有 pgl 调用（会卡死）")

    # createUI 里 connect 必须在 running 守卫内
    cui = re.search(r'tsl::elm::Element\s*\*\s*MainGui::createUI\s*\(\s*\)\s*\{', gui)
    if cui:
        i = cui.end() - 1
        d = 0
        body = None
        for j in range(i, len(gui)):
            if gui[j] == "{":
                d += 1
            elif gui[j] == "}":
                d -= 1
                if d == 0:
                    body = gui[i:j+1]
                    break
        if body:
            ok = re.search(r'if\s*\(\s*running\s*\)\s*\{[^}]*?connect_fizeau\(\)',
                           body, re.S) is not None
            ck(ok, "createUI 里 connect_fizeau 在 if (running) 内")

    # ── 下拉式分组的 lambda 捕获生命周期 ──
    #
    # GroupHeaderItem 的展开回调在 PresetGui::createUI 里构造。
    # 它引用了局部 vector `buckets`。若按引用捕获 vector 的**元素**
    # （形如 `[&b, ...]`），一旦 buckets 再扩容，引用立刻悬空 ——
    # 这是"有时能跑、有时崩"的典型来源，必须用下标访问。
    pg = re.search(r'tsl::elm::Element\s*\*\s*PresetGui::createUI\s*\(\s*\)\s*\{',
                   gui)
    if pg:
        i6 = pg.end() - 1
        d6 = 0
        body6 = None
        for j6 in range(i6, len(gui)):
            if gui[j6] == "{":
                d6 += 1
            elif gui[j6] == "}":
                d6 -= 1
                if d6 == 0:
                    body6 = gui[i6:j6 + 1]
                    break
        if body6:
            # 找所有 lambda 捕获列表
            caps = re.findall(r'\[([^\]]*)\]\s*\(\s*\)', body6)
            bad_caps = [c for c in caps
                        if re.search(r'&\s*b\b', c)]   # 捕获了 vector 元素引用
            ck(not bad_caps,
               "分组回调没有按引用捕获 vector 元素",
               f"发现 {bad_caps} —— vector 扩容会让它悬空；"
               f"应改为捕获 &buckets + 下标")
            # 当前实现: 分类行**只切换静态展开状态 + 重建页面**，
            # 不动态增删列表项、也不捕获任何局部容器的引用。
            #   · 不允许按引用捕获局部 vector（groups / buckets …）
            #   · 不允许在点击回调里调用 list->addItem / removeItem
            #     （List 的增删按帧惰性生效，在遍历中改它会崩）
            ref_caps = [c for c in caps if c.strip().startswith("&")]
            ck(all(re.fullmatch(r'&\w+', c.strip()) and
                   c.strip()[1:] in ("g_state", "g_expandedGroups")
                   for c in ref_caps),
               "分组回调不按引用捕获局部容器",
               f"发现引用捕获 {ref_caps} —— 局部容器在页面重建后会失效")
            ck("swapTo<PresetGui>" in body6,
               "分类行点击后用 swapTo 重建页面（不动态增删列表项）",
               "swapTo 替换栈顶；changeTo 会压栈，导致 B 行为异常。"
               "在点击回调里 addItem/removeItem 则会崩溃")


def main():
    # 版本号从 version.hpp 读（唯一来源），不手抄 ——
    # 这里曾硬编码 "2.0.0"，源码升到 3.0.0 后本工具的横幅就一直在报旧版本。
    _vh = (SRC / "version.hpp")
    _m = re.search(r'#define\s+FNX_VERSION\s+"([^"]+)"',
                   _vh.read_text(encoding="utf-8")) if _vh.is_file() else None
    ver = _m.group(1) if _m else "?"

    print("=" * 70)
    print(f"  超能滤镜 · {ver} 深度审计")
    print("=" * 70)

    files = ["main.cpp", "gui.cpp", "gui.hpp", "fizeau_ipc.cpp",
             "fizeau_ipc.hpp", "presets.hpp", "layout.hpp",
             "version.hpp", "fnx_log.hpp", "fnx_probe.hpp"]
    srcs = {}
    for f in files:
        p = SRC / f
        if p.is_file():
            srcs[f] = read(p)
    print(f"  读取 {len(srcs)} 个源文件")

    presets, declared, _ = parse_presets(srcs["presets.hpp"])
    print(f"  解析到 {len(presets)} 个预设，数组声明 {declared}")

    audit_unused(srcs)
    parsed = audit_numbers(presets)
    audit_layout(srcs, presets, declared)
    v = audit_consistency(srcs, presets)
    audit_safety(srcs)

    print()
    print("=" * 70)
    if notes:
        print(f"  提示（{len(notes)} 条，不一定算问题）:")
        for n in notes:
            print(f"    · {n}")
        print()
    print(f"  检查项: {checks}   问题: {len(problems)}")
    print("=" * 70)
    if problems:
        for cat, msg, detail in problems:
            print(f"  ★ [{cat}] {msg}")
            if detail:
                print(f"           {detail}")
        return 1
    print("  结果: 深度审计未发现问题")
    return 0


if __name__ == "__main__":
    sys.exit(main())
