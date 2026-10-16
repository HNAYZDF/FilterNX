# 更新日志

本文件记录**可观察的改动**（现象 → 原因 → 修法），不是提交流水账。
版本号唯一来源是 `overlay/src/version.hpp`。

---

## 5.0.1 — 2026-10-17

### 修复：设置重启后丢失（真机反馈）

**现象**：「每次重启之后屏幕会变黄，要去滤镜那里重新调节。」

**根因**：**持久化的责任方搞错了** —— 插件只发 IPC，从不写盘。

Fizeau 的架构是「sysmodule 只读配置、overlay 负责写配置」：

| 组件 | 与配置文件的关系 | 源码依据 |
|---|---|---|
| sysmodule | 开机 **只读一次** 然后应用 | `sysmodule/src/main.cpp`: `if (parse_config()) profile.apply();` |
| sysmodule 的 IPC 服务 | **完全不碰磁盘** | `sysmodule/src/ipc_server.c` 里没有任何 fopen/写盘 |
| 官方 overlay | **唯一的写盘方** | `FizeauOverlayGui::~FizeauOverlayGui()` 里 `config.write()` |

所以磁盘上的 `config/Fizeau/config.ini` 才是重启后的**唯一事实来源**，
`SetProfile` 这类 IPC 只改 sysmodule 的运行态。本插件不走官方 overlay，
于是用户选的滤镜只活在内存里 —— 重启后 sysmodule 读回整合包预置的旧参数
（偏黄的色温），画面自然又变回去了。

**修法**：插件自己承担这次写盘（新增 `fzSaveConfigToSd()`）。

- 通过 IPC 读回**全部 4 个 profile** 与 `active` 开关、掌机/底座映射；
- 按 Fizeau `Config::make()` 的**同一格式**（字段名、顺序、精度）写出
  `sdmc:/config/Fizeau/config.ini`；已存在 `/switch/Fizeau/config.ini` 时沿用后者
  —— 与上游 `Config::find_config()` 的查找顺序一致；
- 值全部取自读回的真实状态，因此**不会覆盖**用户在官方 overlay 里做过的其它设置；
- **不做 sanitize**，与官方 `Config::write()` 行为一致（值本就来自 Fizeau）；
- 读不全（任一 profile 读失败）就**放弃写入** —— 宁可不保存，也不用半份数据覆盖配置；
- 挂载 SD 卡时先判断是否已挂载（NX_EEXIST），只卸载自己挂的那次。

**调用时机**：按 **A 确认滤镜**、以及**开关滤镜**之后。刻意**不在光标预览的每一步**
写盘 —— 那会让 SD 卡在按住方向键时被反复写入。

**界面反馈**：确认后右下角如实提示 `已应用·已保存` 或 `已应用·重启失效`
（后者表示写盘失败：卡只读 / 写保护 / 空间不足），不再让用户以为"存上了"。

### 顺带修掉的两个隐患

- **`fzFillProfile()` 会静默重置黄昏/黎明时刻**：它原先无条件把
  `dusk_begin`/`dusk_end`/`dawn_begin`/`dawn_end`/`dimming_timeout` 写成
  21:00 / 07:00 / 30:00，而函数上方注释却写着"保留默认的黄昏/黎明时刻" ——
  用户若在官方 overlay 里改过调度时间，一用滤镜就被悄悄改回去。
  现在只改色彩设置、`components`、`filter` 三类字段，其余原样保留。
- **`apply_preset()` 读回失败时用全零 profile 兜底**：那会把一份全零配置写进
  Fizeau，等于清掉 profile 的调度字段。现在**读不到就直接返回失败**，
  宁可这次不生效，也不静默破坏数据。

### 产物

```
Chaoneng.ovl   760,009 字节
SHA256         ACBA54E3B9BBCA8D298DFEF50B47F268A30D50ED771F0068DCBBBE711F63347A
菜单显示       超能滤镜  5.0.1
verify_all.ps1 25 项检查全部通过（2 项需插卡，记为 SKIP）
```

### 升级说明

直接覆盖 `SD:/switch/.overlays/Chaoneng.ovl` 即可，无需其它操作。
升级后**按一次 A 确认**你想要的滤镜，配置就会落到卡上；此后重启保持。

---

## 5.0.0 — 2026-10-08

以**修复缺陷与优化**为主。滤镜数量维持 **100 种**（11 类），无新增、无删减。

### 修复

- **修掉 Fizeau 探测的 IPC 句柄泄漏**（`overlay/src/fnx_probe.hpp`）

  `smRegisterService` 成功时会返回一个**服务端口句柄**，原先的写法直接
  `return false`，句柄没有回收。而探测函数**每次打开插件**都会调用，
  属于反复执行的路径 —— 修法是补上 `svcCloseHandle`，并明确顺序为
  **先关句柄、再 `smUnregisterService`**，两步缺一不可。

- **修掉主页面内容溢出被裁剪**（`overlay/src/gui.cpp`、`layout.hpp`）

  主页面一度是 8 项，实际高度 `33 + 3×33 + 8×70 = 692px`，而 `List` 的
  可见高度只有 **557px** —— 溢出 135px。真机表现：

  - 「适用游戏」被裁剪矩形**从中间切开** → 屏幕底部半行残影；
  - 「关于本插件」整行落在裁剪区外 → **用户找不到作者与 QQ 群的入口**。

  更隐蔽的是 `layout.hpp` 的 `MAIN_ITEMS` 停在 5，于是
  `tests/test_layout.cpp` 的高度断言算的是**一个并不存在的页面**，
  断言"通过"而真机在溢出。

  修法：删掉两行重复说明（「生效方式 / 立即生效」与标题栏副标题
  「· 按下即生效」重复；「适用游戏 / 全部通用」已被「关于」取代），
  主页面压回 6 项 = `552 ≤ 557` 整页放得下，并把 `MAIN_ITEMS` 同步为 6、
  `INFO_ITEMS` 校正为真实的 7。

- **修掉菜单里版本号恒为 1.0.0**（`overlay/Makefile`）

  两处叠加：NACP 目标里把版本号**硬编码成 `"1.0.0"`**，且 `$(NACP)`
  没有先决条件 —— make 认定"文件已存在 = 已是最新"，改了 `version.hpp`
  也不会重新生成 .nacp。于是源码升到 3.x 之后，菜单里仍显示 1.0.0。

  修法：版本号改为用 sed 从 `src/version.hpp` 读 `FNX_VERSION`
  （与 `package.sh` 同一读法，两处不会漂移），并补上
  `$(NACP): src/version.hpp` 依赖声明。

### 优化与文案纠错

- 预设数量文案「共19种」改为**动态取自 `PRESETS.size()`** ——
  原先是硬编码，滤镜扩充后就成了错误信息；
- `update()` 首帧日志原写「渲染已走通」是**错的**：框架一帧的顺序是
  `update() → draw() → handleInput()`，update 跑在 draw 之前。
  这条日志是排障时判断"崩在哪一阶段"的依据，说反了会误判，已改正；
- 注释里"想重连请按界面上的「重试连接」按钮"与实现矛盾 ——
  引导页实际是**零按钮、零回调**（`pgl` 卡死教训之后的刻意设计），
  已改为"重开一次插件触发重新探测"；
- 补齐多处"为什么这么做"的源码注释（高度预算算式、句柄回收原因、
  一帧调用顺序），并新增 `fnx_probe.hpp` / `layout.hpp` 的风险说明。

### 构建与校验

- 新增 `tools/msys_build.sh`：Windows 侧 PATH 里没有 `make` 与
  `aarch64-none-elf-*`，需由 MSYS2 bash 摆好工具链路径再进 `overlay/` 编译；
- 修正 `README.md` 中滞后两个大版本的版本号（3.0.0 → 5.0.0）——
  它会让「文档一致性」与「深度审计」两项检查报 FAIL；
- `verify_all.ps1` 25 项检查全部通过（其中「注册表一致性」
  「Fizeau 自启动条件」两项需插卡，不插卡记为 SKIP）。

### 产物

```
Chaoneng.ovl   739,529 字节
SHA256         9E64B8A7131684411A4BAFC98CFAD4F0CFED3E6F65634FB96B43A9AE111BF91F
菜单显示       超能滤镜  5.0.0
标题栏         超能滤镜  v5.0.0 · 按下即生效
```

---

## 4.2.0 — 布局修正版

- 修正主页面高度预算，把溢出到裁剪区的行收进可见区（`33 + 3×33 + 5×70`）；
- 界面改为下拉式分组列表，预设页收起时只显示分类行，展开显示该组预设。

## 1.0.3 – 1.0.6

- 统一分发文件名为纯 ASCII 的 `Chaoneng.ovl`（中文文件名大气层无法加载），
  中文显示名与版本号改由文件内 NACP 元数据承载；
- 修正 NACP 字段写入位置（`display_version @ 0x3060`，
  `NacpLanguageEntry` 步长 `0x300`），修掉"版本号被误写进 isbn"的问题；
- 加入逐步日志（纯 ASCII 路径 + 卡根退路），用于定位
  "Fizeau 未运行时打开插件导致整个特斯拉菜单消失"这一故障；
- 移除引导页的「连接色彩调节」按钮 —— 真机验证按下会因调用 `pgl` 卡死。

## 1.0.0 — 首个正式版

- 100 种中文滤镜预设，分 11 类；走 Fizeau IPC，按下即生效；
- 未连接时显示纯提示页，零按钮、零 IPC。

---

## 待办（尚未实现，欢迎讨论）

- **行数常量与实际界面自动对齐**：`layout.hpp` 的常量目前没有被
  `gui.cpp` 引用，同步靠人工，正是 5.0.0 那个溢出 bug 的根因。
  计划让校验脚本直接数 `gui.cpp` 里每个 `createUI` 的 `addItem` 调用数，
  与常量比对，把"漂移"变成红灯；并把未连接引导页也纳入断言。
- **日志体积上限**：日志目前是追加模式，永不清理、无大小上限，
  长期使用会持续增长。计划加上限检查与逐会话分隔。
- **清理未使用符号**：`deep_audit.py` 列出 28 条未被引用的函数与常量
  （如 `fnxLogRc()`、`fzInstalled()`、`height_budget()` 等）。
- **主页面空间已满**：`552/557`，只剩 5px，再加一行必然越界。
  后续要加功能需先调整版面结构（把说明项移出首屏，或改为可滚动页面）。
- **`deep_audit.py` 统计口径**：「主页面源码里的小标题调用数: 6
  （常量 MAIN_HEADERS=3）」这条提示统计的是全文件 `CategoryHeader` 总数
  （引导页 3 + 主页面 3），不是主页面的，属噪音提示。
- **跟踪 23.0.1 的工具链**（2026-10-17 核实）：基线为 devkitPro
  `libnx 4.12.0-1`（构建于 2026-02-04，`dkp-libs` 仓库内最新，
  `pacman -Qu` 无 Switch 侧可升级项）+ libultrahand `v2.5.3`（上游最新）。
  上游 Atmosphere-libs 已于 2026-10-15 加入 23.0.1 支持，但**尚未由 devkitPro
  打包**，且那批改动在 libstratosphere（sysmodule 侧）—— 与本 overlay 无关：
  本插件只用 `sm*` 会话/注册与 `svcCloseHandle`/`svcSendSyncRequest`，
  不碰 `hosversion` / `setsys` / `fatal` / `socket` / `applet`。
  **新固件真正要重编的是 Fizeau，不是本插件。** 完整依据与判断方式见
  [开发说明.md](开发说明.md) 第三节「工具链基线：要不要"对齐最新 libnx"」。
