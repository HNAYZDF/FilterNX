/*
 * FilterNX — 大气层中文滤镜插件（全中文界面）
 *
 * gui.cpp — 界面实现
 *
 * ═══════════════════════════════════════════════════════════════════════════
 * 界面布局的硬约束（真机实测踩过的坑）
 * ═══════════════════════════════════════════════════════════════════════════
 * libultrahand 的 ListItem 会把"名字"和"数值"并排画在同一行：
 *
 *     [ 名字 .................... 数值 ]
 *     m_maxWidth  = getWidth() - valueWidth - 66
 *     m_truncated = textWidth > m_maxWidth + 20
 *
 * 说明文字（value）越长，名字能用的宽度越小；一旦超限，ListItem 会启用
 * 滚动动画 —— 静止时看起来就是被截断了（实测:「单色暖黄」显示成「单色」）。
 *
 * 应对方式不是调参，而是从设计上避免:
 *   · 预设名字    ≤ 4 字
 *   · 预设说明    ≤ 9 字
 *   · 主界面不堆长句，说明文字放进小标题或单独一页
 *   · 约束由 tests/test_presets.cpp 断言强制
 *
 * 另外，为了让用户知道"当前生效的是哪个预设"，主界面会回读 Fizeau 的
 * 实际设置并与预设表比对 —— 显示的是真实状态，不是我们"以为写入"的值。
 *
 * GPLv2，详见 LICENSE。
 */

#include <tesla.hpp>
#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

#include "fnx_log.hpp"
#include "fnx_probe.hpp"
#include "fnx_group_list.hpp"
#include "fnx_preview.hpp"
#include "gui.hpp"
#include "presets.hpp"
#include "version.hpp"

using namespace fnx;

namespace fnx::ui {

namespace {

// 界面用的状态快照
struct LiveState {
    bool          service_ok = false;
    bool          active     = false;
    std::uint32_t profile_id = PROFILE_1;
    FzProfile     profile    = {};
};

LiveState g_state;

/*
 * 刷新 Fizeau 状态 —— **只读，绝不建立新连接**
 *
 * ═══════════════════════════════════════════════════════════════════
 * 设计原则: 没开后台时，插件绝不能崩
 * ═══════════════════════════════════════════════════════════════════
 * 真机故障史（每一版都试过，都失败）:
 *   · 打开插件就自动连 Fizeau（fzInitialize）      → 菜单崩
 *   · 加会话守卫（session_ready）                  → 仍崩
 *   · 移除 TIPC（AMS 扩展）探测                     → 仍崩
 *   · 创建 boot2.flag 让 Fizeau 自启动              → 仍崩
 *   · 怀疑内存占用 → 实测 .rodata 仅 34KB          → 不是原因
 *   · 怀疑 TLS ABI 破坏 → 扫全部 16 个 overlay     → 均无旧签名
 *   · 加「连接色彩调节」按钮（pgl 启动 sysmodule）  → **点下去卡死**
 *
 * ⚠ 最后一条是关键教训:
 *   pgl 是给 qlaunch（系统外壳）用的服务。从 applet 里调用它**不会
 *   返回错误码，而是直接挂住** —— 比崩溃更糟，用户只能强制关机。
 *
 *   所以「调用失败会返回错误码」这个假设**不成立**。
 *   对权限不明的服务，正确做法是**根本不调用**。
 *
 * ═══════════════════════════════════════════════════════════════════
 * 现在的设计: Fizeau 未运行时，插件只显示操作指引
 * ═══════════════════════════════════════════════════════════════════
 *   · overlay 初始化 (initServices) → 零 Fizeau 调用
 *   · 主页面构造 (createUI)         → 零 Fizeau 调用
 *   · 未连接时                      → 纯提示页，无按钮、无回调
 *   · refresh_state()               → 会话不在才连，连上后只读
 *   · 每个 IPC 函数内部             → 都有会话守卫（双保险）
 *
 * 唯一的连接点是 apply_preset()（用户选滤镜时）—— 那时若 Fizeau
 * 没运行，会走到会话守卫并返回失败，界面提示「未连接 Fizeau」。
 * ═══════════════════════════════════════════════════════════════════
 */
/*
 * refresh_state —— 刷新已连接会话的状态
 *
 * 未连接时尝试建立会话（fzInitialize 内部有守卫，服务不存在时
 * 干净返回错误码）。已连接时只做只读刷新。
 *
 * ⚠ 两种极端都试过，都不对:
 *   · 每次刷新都重连  → 浪费 IPC
 *   · 改成只读      → **全工程无人建立会话，插件彻底失效**
 *   现在是: 会话不在才连，连上后只读。
 */
/*
 * connect_fizeau —— 建立与 Fizeau 的会话（唯一的连接入口）
 *
 * ═══════════════════════════════════════════════════════════════════════════
 * ⚠ 为什么单独拆出来，而不是塞进 refresh_state()
 * ═══════════════════════════════════════════════════════════════════════════
 * 因为要**分清职责**，这样日志才能定位:
 *
 *   connect_fizeau()  → 会发 IPC（smGetService）  ← 唯一可能出问题的地方
 *   refresh_state()   → 纯本地判断 + 已连接时读状态，不发新连接
 *
 * 之前两者混在一起，日志里"refresh_state"这一行既可能是纯本地判断、
 * 也可能是发起了连接 —— 真出问题时根本分不清是哪一步。
 *
 * 现在的调用顺序（MainGui::createUI 里）:
 *   1. refresh_state()      ← 纯本地，绝对安全
 *   2. 建好界面
 *   3. connect_fizeau()     ← 万一它出问题，界面已在屏幕上，日志也有记录
 * ═══════════════════════════════════════════════════════════════════════════
 */
bool connect_fizeau() {
    if (fzIsSessionReady())
        return true;                 // 已有会话

    fnx::fnxLog("[gui]   connect: 调用 fzInitialize()");
    const Result rc = fzInitialize();
    if (R_FAILED(rc)) {
        char buf[64];
        std::snprintf(buf, sizeof(buf),
                      "[gui]   connect: fzInitialize 失败 0x%08X",
                      (unsigned)rc);
        fnx::fnxLog(buf);
        g_state.service_ok = false;
        return false;
    }

    g_state.service_ok = true;
    fnx::fnxLog("[gui]   connect: 会话已建立");
    return true;
}

/*
 * refresh_state —— 只读刷新
 *
 * ⚠ 本函数**不建立新连接**。未连接时直接返回 false，一个字节都不发。
 *   连接请用 connect_fizeau()。
 *
 * 这样 update() 里周期性调用它是安全的 —— 不会每 0.5 秒重连一次。
 */
bool refresh_state() {
    if (!g_state.service_ok || !fzIsSessionReady()) {
        g_state.service_ok = false;
        return false;
    }

    bool active = false;
    if (R_SUCCEEDED(fzGetIsActive(&active)))
        g_state.active = active;

    std::uint32_t pid = PROFILE_1;
    if (R_SUCCEEDED(fzGetActiveProfileId(false, &pid)) && pid < PROFILE_TOTAL)
        g_state.profile_id = pid;

    // 只有读取成功才覆盖快照；失败时保留上一次的有效值，
    // 而不是让全零数据污染后续判断。
    FzProfile fresh = {};
    if (R_SUCCEEDED(fzGetProfile(g_state.profile_id, &fresh))) {
        if (fresh.filter != COMP_NONE && fresh.filter != COMP_RED &&
            fresh.filter != COMP_GREEN && fresh.filter != COMP_BLUE) {
            fresh.filter = COMP_NONE;
        }
        g_state.profile = fresh;
    }

    return true;
}


// 把设置写入 Fizeau 并立即生效
bool apply_preset(const Preset &p) {
    if (R_FAILED(fzInitialize()))
        return false;

    const std::uint32_t pid = g_state.profile_id;

    // 先读现有 profile 只为保留其黄昏/黎明等调度字段
    FzProfile prof = {};
    if (R_FAILED(fzGetProfile(pid, &prof)))
        prof = {};

    fzFillProfile(&prof, p.settings, p.components, p.filter);

    if (R_FAILED(fzSetProfile(pid, prof)))
        return false;

    // 确保总开关打开，否则用户看不到任何变化
    if (!g_state.active) {
        if (R_FAILED(fzSetIsActive(true)))
            return false;   // 开关打不开，用户看不到任何效果，如实报告失败
    }

    return true;
}

// ══════════════════════════════════════════════════════════ 实时预览
//
// 「光标移到哪个滤镜就应用哪个」—— 特斯拉 overlay 是半透明的，
// 游戏画面在底下透出来，所以能立刻看到效果。
//
// 进入预设页时把当前 profile 存一份（begin_preview），
// 离开页面时写回（end_preview）。这样预览不会污染用户原来的设置。
//
// ⚠ 恢复用的是「整份 profile 写回」，而不是「把某个预设再应用一次」——
//   用户原来的设置可能不对应任何预设（他在 Fizeau 里自己调过），
//   只有整份写回才能原样还原。
//
// ⚠ 只在服务可用时才预览。服务没运行时的行为保持和之前完全一致 ——
//   那条路径（未连接 → 引导页）已经反复验证过不能有任何 IPC。

namespace {
bool          g_preview_active = false;
FzProfile     g_preview_saved  = {};
std::uint32_t g_preview_pid    = PROFILE_1;

/*
 * 「用户刚刚移动了光标」—— 预览只在它为 true 时触发。
 *
 * ⚠ 为什么需要它（真机 bug 的根因）:
 *   libultrahand 的 List::draw 会在列表**第一帧强制设一次焦点**
 *   （tesla.hpp:5834 的 m_hasSetInitialFocusHack），那不是用户操作。
 *   若把 setFocused(true) 直接当"光标移到这里"，就会:
 *       进入页面 → 误触发预览 → 画面变成列表首项
 *       按 A 确认后返回 → 列表重建又强制设焦点 → 又预览一次
 *       结果就是"返回后跳到另一个滤镜，再返回还返回"。
 *
 *   所以要用**方向输入**作为"用户真的在移动"的证据 ——
 *   它不依赖任何下标状态，页面重建也不会伪造出方向输入。
 */
bool g_userNavigated = false;

/*
 * ══════════════════════════════════════════════════════════════════════
 * 光标位置记录 —— 用来在页面重建后恢复（否则会跳回最上面）
 * ══════════════════════════════════════════════════════════════════════
 * 展开/收起分类用 changeTo<PresetGui>() 重建页面，而 List 构造时
 * m_focusedIndex 被置 0 —— 用户刚点的那一行就丢了，表现为"跳回顶部"。
 *
 * 用框架的 List::setFocusedIndex() 恢复（它同时会更新滚动偏移）。
 * ══════════════════════════════════════════════════════════════════════
 */
enum class CursorKind : unsigned char {
    None = 0,     // 光标在列表首项（框架默认），不需要恢复
    Group,        // 光标在某个分类行上
    Preset,       // 光标在某个滤镜项上
};

CursorKind    g_cursorKind  = CursorKind::None;
std::size_t   g_cursorGroup = 0;   // 第几个分类
std::size_t   g_cursorItem  = 0;   // 该分类里的第几项

/*
 * 是否已经建立过光标位置。
 *
 * ⚠ 必须与 g_cursorKind 分开:
 *   g_cursorKind == None 有两种含义 ——
 *     ① 光标就在首项（框架默认），不需要恢复
 *     ② 用户还没移动过，同样不需要恢复
 *   两者都"不需要恢复"，所以 None 时直接不跳转即可。
 *
 *   但反过来，用户可能**把光标移回了首项**（None），那时也不该跳转 ——
 *   语义正好一致，所以一个枚举就够，不需要额外的布尔量。
 */

// 本帧是否收到过方向输入 —— 由 PresetGui::handleInput 置位，
// PresetGui::update 消费并清零（两者每帧各调用一次）
bool g_navThisFrame = false;

// 方向键 / 摇杆 —— 这些才算"用户在移动光标"
inline bool isNavigationInput(u64 keysDown) {
    return (keysDown & (HidNpadButton_Up | HidNpadButton_Down |
                        HidNpadButton_Left | HidNpadButton_Right |
                        HidNpadButton_StickLUp | HidNpadButton_StickLDown |
                        HidNpadButton_StickLLeft | HidNpadButton_StickLRight |
                        HidNpadButton_StickRUp | HidNpadButton_StickRDown |
                        HidNpadButton_StickRLeft | HidNpadButton_StickRRight))
           != 0;
}
} // namespace

/*
 * ═══════════════════════════════════════════════════════════════════════════
 * ⚠ 预览基准（g_preview_saved）为什么不能每次 createUI 都重新保存
 * ═══════════════════════════════════════════════════════════════════════════
 * 展开/收起分类用的是 `tsl::changeTo<PresetGui>()`，它会:
 *     析构旧的 PresetGui  → 构造新的 PresetGui
 *
 * 如果两端都动预览状态，就会出现:
 *     begin（新）记下"当前设置" —— 而当前设置是**上一次预览的值**，
 *     不是用户进来时的原设置。
 * 于是每展开一次，基准就往预览值偏一次。反复几次后按 B，
 * 恢复的已经不是用户原来的设置，而是某个中间状态。
 *
 * 正确的语义是: **基准属于"进入预设页这个会话"，不属于某个 Gui 对象。**
 *
 * 判据用「是否已经在会话里」（g_preview_active）:
 *     begin:  已在会话 → 什么都不做（保住最初的基准）
 *             不在会话 → 读一次 profile 作为基准，进入会话
 *     end:    离开会话时才真正写回
 *
 * 而"离开会话"由 MainGui::createUI() 显式触发（见那里的 end_preview 调用）
 * —— 用户从预设页返回主页面，就是会话结束。这是框架里最可靠的信号:
 * 主页面被构建 ⇒ 预设页已被离开。
 * ═══════════════════════════════════════════════════════════════════════════
 */

// 进入预设页: 若不在会话中，记下当前设置作为基准
void begin_preview() {
    if (g_preview_active)
        return;              // 已在会话里 —— 保住最初的基准，别覆盖

    if (!g_state.service_ok)
        return;
    if (R_FAILED(fzInitialize()))
        return;

    g_preview_pid = g_state.profile_id;
    FzProfile cur = {};
    if (R_FAILED(fzGetProfile(g_preview_pid, &cur)))
        return;

    g_preview_saved  = cur;
    g_preview_active = true;
    fnx::fnxLog("[gui] 预览: 已保存原设置（会话开始）");
}

// 离开预设页: 写回基准
void end_preview() {
    if (!g_preview_active)
        return;              // 不在会话里，或已确认过 —— 无事可做
    g_preview_active = false;

    if (R_FAILED(fzInitialize())) {
        fnx::fnxLog("[gui] 预览: 恢复失败（无会话）");
        return;
    }
    if (R_FAILED(fzSetProfile(g_preview_pid, g_preview_saved)))
        fnx::fnxLog("[gui] 预览: 恢复失败（写回出错）");
    else
        fnx::fnxLog("[gui] 预览: 已恢复原设置（会话结束）");
}

// 光标移到某个滤镜上 —— 立即应用，但不提示（移动时提示会刷屏）
void preview_preset(const Preset &p) {
    // ⚠ 只在用户**真的按了方向键/摇杆**之后才预览。
    //   否则框架在列表第一帧的强制聚焦、以及页面重建后的自动聚焦，
    //   都会被误当成"用户选了这一项"（详见 g_userNavigated 的说明）。
    if (!g_userNavigated)
        return;
    if (!g_state.service_ok)
        return;

    g_userNavigated = false;   // 用掉本次导航意图，避免后续误触发
    (void)apply_preset(p);
    // 刻意不回读状态: 预览只为看效果，主界面刷新留到真正确认时再做
}

// 用户按 A 确认 —— 保留这个滤镜，离开时不再恢复
void commit_preview() {
    g_preview_active = false;
    fnx::fnxLog("[gui] 预览: 已确认，保留所选");
}

/*
 * 记下"光标现在在哪" —— 由列表项在自己获得焦点时调用。
 *
 * ⚠ 只记录**用户方向输入之后**的焦点变化。
 *   框架第一帧的强制聚焦、页面重建后的自动聚焦都会调 setFocused，
 *   那些不是用户的选择（预览功能踩过同一个坑，这里用同样的判据）。
 */
void noteCursorOnGroup(std::size_t gi) {
    if (!g_userNavigated)
        return;
    g_cursorKind  = CursorKind::Group;
    g_cursorGroup = gi;
    char b[80];
    std::snprintf(b, sizeof(b), "[gui] 光标记录: 分类行 idx=%zu", gi);
    fnx::fnxLog(b);
}

void noteCursorOnPreset(std::size_t gi, std::size_t ii) {
    if (!g_userNavigated)
        return;
    g_cursorKind  = CursorKind::Preset;
    g_cursorGroup = gi;
    g_cursorItem  = ii;
}

bool feq(float a, float b) { return std::fabs(a - b) < 1e-4f; }

// 反查当前设置对应哪个预设。
// 回读 Fizeau 的真实设置再比对，比"记住上次点了什么"可靠 ——
// 用户可能在 Fizeau 自己的界面里改过设置。
const Preset *detect_current_preset() {
    const FzSettings &s = g_state.profile.day_settings;
    const std::uint32_t f = g_state.profile.filter;

    for (const auto &p : PRESETS) {
        const FzSettings &q = p.settings;
        if (s.temperature == q.temperature &&
            feq(s.saturation, q.saturation) &&
            feq(s.hue, q.hue) &&
            feq(s.contrast, q.contrast) &&
            feq(s.gamma, q.gamma) &&
            feq(s.luminance, q.luminance) &&
            feq(s.range.lo, q.range.lo) &&
            feq(s.range.hi, q.range.hi) &&
            f == p.filter) {
            return &p;
        }
    }
    return nullptr;
}

// 当前画面的中文描述
std::string current_description() {
    if (!g_state.service_ok)
        return "服务未连接";
    if (!g_state.active)
        return "已关闭";

    if (const Preset *p = detect_current_preset())
        return p->name;

    // 不是任何预设（用户自己调过）→ 显示数值摘要
    return settings_summary(g_state.profile.day_settings,
                            g_state.profile.filter);
}

} // namespace

// ═══════════════════════════════════════════════════════════ 主页面

/*
 * 「当前画面」那三行需要动态刷新。
 *
 * 为什么必须这样:
 *   tsl::Gui 的 createUI() 只在**首次进入页面时调用一次**，之后每次回到
 *   该页面走的是 update()（tesla.hpp:11370 每帧调用）。
 *   早期版本的 update() 是空的，所以从预设页返回后「当前画面」一直显示
 *   旧值 —— 看起来就是"效果显示不能实时更新"。
 *
 * 做法: 把这三项存下来，在 update() 里按固定间隔回读 Fizeau 真实状态并
 *       setValue()。只改文本，不重建列表 —— 重建会打断用户的选中位置。
 *
 * 显示的是**回读值**而不是"我们写入的值": 用户可能在 Fizeau 自己的界面里
 * 改过设置，也可能写入失败，只有回读才反映真实状态。
 */
namespace {
tsl::elm::ListItem *g_filter_item  = nullptr;
tsl::elm::ListItem *g_effect_item  = nullptr;
tsl::elm::ListItem *g_profile_item = nullptr;

// 回读间隔（帧）。不每帧都读: IPC 虽轻但每秒 60 次没有意义，
// 而且会让状态文字频繁闪动。30 帧 ≈ 0.5 秒。
constexpr int REFRESH_INTERVAL_FRAMES = 30;
int g_frame_counter = 0;

std::string filter_state_text() {
    if (!g_state.service_ok) return "未连接";
    return g_state.active ? "已开启" : "已关闭";
}

std::string profile_text() {
    char buf[16];
    std::snprintf(buf, sizeof(buf), "档位%u", g_state.profile_id + 1);
    return buf;
}
} // namespace

tsl::elm::Element *MainGui::createUI() {
    // ═══════════════════════════════════════════════════════════════════════
    // 顺序很重要: **先建界面，再尝试连接**
    // ═══════════════════════════════════════════════════════════════════════
    // 为什么是这个顺序:
    //
    //   真机故障: Fizeau 没运行时打开插件 → **整个特斯拉菜单消失**。
    //   反复试过多种方案（会话守卫 / 移除 TIPC / 建 boot2.flag / 查 TLS ABI /
    //   查内存占用）都没根治。既然定位不到确切原因，就必须假设
    //   **"连接 Fizeau"这个动作本身在某些机器状态下会让进程死掉**。
    //
    //   那么唯一能降低损失的做法就是: 让它死得**晚一点、可控一点**。
    //   · 先 refresh_state()（纯本地判断，不建连接）
    //   · 界面**立即建好**，最坏情况也只是显示"未连接"
    //   · 之后再尝试连一次 —— 万一这里崩，界面已经在屏幕上了，
    //     而且日志会记下"尝试连接"这一行，下次就能确认是它
    //
    //   ⚠ 注意: 这里连上与否**不改界面结构**。界面是按"未连接"建的，
    //     如果连接成功，update() 会在下一帧把内容刷成真实状态。
    //     这样避免了在 createUI 里 changeTo（那会重建页面 → 抖动）。
    // ═══════════════════════════════════════════════════════════════════════
    fnx::fnxLog("[gui] createUI 进入");

    // ═══════════════════════════════════════════════════════════════════════
    // 回到主页面 ⇒ 预设页已被离开 ⇒ 结束预览会话，恢复原设置
    // ═══════════════════════════════════════════════════════════════════════
    // ⚠ 这是框架里最可靠的「离开预设页」信号:
    //   预设页用 changeTo<PresetGui>() 重建自己（展开/收起分类），
    //   所以不能靠 PresetGui 的析构来判断离开 —— 那个会被重建误触发。
    //   而主页面被构建，只可能是因为用户真的回到了主页面。
    //
    // 用户按过 A 确认的话，commit_preview() 已把会话置为结束，
    // 这里就是空操作 —— 那是「我就要这个滤镜」，不该被撤销。
    end_preview();

    // ═══════════════════════════════════════════════════════════════════════
    // 判断 Fizeau 是否在运行 —— 用**注册探测**，不用 smGetService
    // ═══════════════════════════════════════════════════════════════════════
    // 这是从 sys-clk overlay（同类插件，处理同样的问题）学到的做法:
    //
    //     尝试**注册** "fizeau" 这个名字:
    //       注册失败 = 名字已被占用 = 服务正在运行
    //       注册成功 = 名字没人用   = 服务没运行 → 立刻撤销注册
    //
    // `smRegisterService` 只往 sm 的名字表写一条，**不建立客户端会话、
    // 不接触目标进程**。所以目标在不在，它都只返回错误码 —— 纯探测。
    //
    // 而 `smGetService` 会真的去建立会话、拿句柄，涉及目标进程状态，
    // 那才是不可预期的部分（真机故障正出在这里）。
    //
    // ⚠ 任何不确定的情况（sm 会话无效等）都判为"没运行" ——
    //   宁可显示提示页，也不去碰一个可能不存在的服务。
    // ═══════════════════════════════════════════════════════════════════════
    const bool sm_ok = fnx::smSessionReady();
    fnx::fnxLog(sm_ok ? "[gui] sm 会话有效" : "[gui] ★ sm 会话无效");

    const bool running = fnx::isFizeauRunning();
    fnx::fnxLog(running ? "[gui] 探测: fizeau 服务在运行"
                        : "[gui] 探测: fizeau 服务未运行");

    // 文件系统探测 —— 用来区分"没装"和"装了但没启动"，纯读文件
    if (!running) {
        switch (fzDetectPresence()) {
            case FzPresence::NotInstalled:
                fnx::fnxLog("[gui]   并且卡上没找到 Fizeau（未安装）");
                break;
            case FzPresence::InstalledNoBoot:
                fnx::fnxLog("[gui]   卡上有 Fizeau，但没有 boot2.flag（未开自启）");
                break;
            case FzPresence::InstalledBoot:
                fnx::fnxLog("[gui]   卡上有 Fizeau 且已开自启（但没有运行）");
                break;
        }
    }

    // ═══════════════════════════════════════════════════════════════════════
    // 判断显示哪一页 —— 依据是**探测结果**，不是连接成功与否
    // ═══════════════════════════════════════════════════════════════════════
    // 顺序上的两个保证:
    //
    //   ① 探测用注册命令，**不建立客户端会话**（见 fnx_probe.hpp）
    //   ② **只有探测说"在运行"时才调用 connect_fizeau()**
    //
    // 换句话说: 服务没运行时，本函数走到这里就结束了，
    // **一个字节都不会发给 Fizeau**。这正对应用户的要求
    // 「检测没有启动提示，启动不该崩溃」。
    // ═══════════════════════════════════════════════════════════════════════
    if (running) {
        // 服务确实在运行 → 建立会话是安全的（历史版本证明可用）
        if (connect_fizeau()) {
            refresh_state();
            fnx::fnxLog("[gui] 已连接，显示正常界面");
        } else {
            fnx::fnxLog("[gui] 探测说在运行但连接失败 → 显示提示页");
        }
    } else {
        fnx::fnxLog("[gui] 服务未运行 → 显示提示页（零 IPC）");
    }

    // ── 未连接 Fizeau ──
    //
    // 走到这里说明当前没有可用的 Fizeau 会话 ——
    // 机器上没装，或者装了但没运行。
    //
    // ⚠ 这一页曾经"写了但没用": 早期所有 IPC 函数都不检查会话是否建立，
    //   拿空句柄发请求直接把整个特斯拉菜单搞崩。现在 IPC 层有会话守卫，
    //   而且刷新逻辑也做了结构性隔离，这个引导页才真正能显示出来。
    if (!g_state.service_ok) {
        g_filter_item = g_effect_item = g_profile_item = nullptr;

        auto *frame = new tsl::elm::OverlayFrame("超能滤镜", FNX_VERSION_LABEL " · 未连接");
        auto *list  = new tsl::elm::List();

        // 行数预算: 33 + 3*33 + 6*70 = 552 ≤ 557
        list->addItem(new tsl::elm::CategoryHeader("未检测到 Fizeau"));

        // ═══════════════════════════════════════════════════════════════════
        // 这一页是**纯提示**，一个 Fizeau 调用都没有
        // ═══════════════════════════════════════════════════════════════════
        // 曾经这里有个「连接色彩调节」按钮，按下会:
        //   ① smGetService 连它的 IPC 服务
        //   ② pglInitialize + pglLaunchProgram 启动它的系统模块
        //
        // 真机结果: **点下去卡死**。
        //
        // 原因: pgl 是给 qlaunch（系统外壳）用的服务，从 applet 里调用它
        //       不会返回错误码，而是直接挂住 —— 比崩溃更难处理，
        //       因为用户只能强制关机。
        //
        // 教训: **"调用失败会返回错误码"这个假设不成立**。
        //       有些服务在权限不足时是**阻塞**而不是报错。
        //       所以对权限不明的服务，正确做法是根本不调用。
        //
        // 现在: 页面只显示怎么操作，零 IPC、零按钮回调。
        //       用户按提示去「系统模块」启用 + 重启即可。
        // ═══════════════════════════════════════════════════════════════════

        list->addItem(new tsl::elm::CategoryHeader("怎么启用"));

        // 步骤用名字 + 数值两列表达，避免超宽
        list->addItem(new tsl::elm::ListItem("第一步", "特斯拉菜单"));
        list->addItem(new tsl::elm::ListItem("第二步", "系统模块"));
        list->addItem(new tsl::elm::ListItem("第三步", "启用色彩调节"));
        list->addItem(new tsl::elm::ListItem("第四步", "重启机器"));

        list->addItem(new tsl::elm::CategoryHeader("说明"));
        list->addItem(new tsl::elm::ListItem("为何要重启", "开机接管"));
        list->addItem(new tsl::elm::ListItem("本插件", "不碰硬件"));

        frame->setContent(list);

        // 注意: 这里**不再尝试连接**。
        //   连接已经在上面的 `if (running)` 分支里做过（且只在服务确实
        //   在运行时才做）。走到这个分支说明服务没运行，或者连接失败 ——
        //   两种情况都应当保持提示页，一个 IPC 都不发。
        fnx::fnxLog("[gui] 显示提示页（本次未连接）");
        return frame;
    }

    fnx::fnxLog("[gui] 已连接，构建正常界面");
    auto *frame = new tsl::elm::OverlayFrame("超能滤镜", FNX_VERSION_LABEL " · 按下即生效");
    auto *list  = new tsl::elm::List();

    // ── 高度预算 ──
    // 本页实际行数（与 layout.hpp 的 MAIN_HEADERS / MAIN_ITEMS 一致）:
    //   33(首项偏移) + 3*33(小标题) + 6*70(列表项) = 552 ≤ 557  → 整页放得下
    // 所以「关于本插件」这一最后一行不会被裁剪（曾经 8 项 = 692px 时被切掉）。
    // ⚠ 行数改了就同步改 layout.hpp，否则那条高度断言会算错页面
    //   （历史上就发生过: 常量停在 5 项、实际 8 项，断言形同虚设）。

    // ── 当前画面（这三项会在 update() 里动态刷新）──
    list->addItem(new tsl::elm::CategoryHeader("当前画面"));

    g_filter_item = new tsl::elm::ListItem("滤镜", filter_state_text());
    list->addItem(g_filter_item);

    g_effect_item = new tsl::elm::ListItem("效果", current_description());
    list->addItem(g_effect_item);

    g_profile_item = new tsl::elm::ListItem("作用于", profile_text());
    list->addItem(g_profile_item);

    // ── 操作 ──
    list->addItem(new tsl::elm::CategoryHeader("操作"));

    // 预设数量动态取自 PRESETS.size()，避免加了预设却忘记改文案
    // （之前硬编码"共19种"，扩充后就成了错误信息）。
    auto *choose = new tsl::elm::ListItem("选择滤镜",
        "共" + std::to_string(PRESETS.size()) + "种");
    choose->setClickListener([](u64 keys) -> bool {
        if (keys & HidNpadButton_A) {
            tsl::changeTo<PresetGui>();
            return true;
        }
        return false;
    });
    list->addItem(choose);

    auto *toggle = new tsl::elm::ListItem(
        g_state.active ? "关闭滤镜" : "开启滤镜",
        g_state.active ? "恢复画面" : "启用设置");
    toggle->setClickListener([](u64 keys) -> bool {
        if (!(keys & HidNpadButton_A))
            return false;

        const bool want = !g_state.active;
        if (R_SUCCEEDED(fzSetIsActive(want))) {
            g_state.active = want;
            // 立即刷新显示，不等 0.5 秒的轮询间隔
            if (g_filter_item) g_filter_item->setValue(filter_state_text());
            if (g_effect_item) g_effect_item->setValue(current_description());
            tsl::notification->showNow(want ? "滤镜已开启" : "滤镜已关闭",
                                       26, "立即生效");
        } else {
            tsl::notification->showNow("操作失败", 26, "检查 Fizeau");
        }
        return true;
    });
    list->addItem(toggle);

    // ── 说明与关于 ──
    //
    // 行数必须与 layout.hpp 的 MAIN_HEADERS / MAIN_ITEMS 一致（本页共 6 项）:
    //   33(首项偏移) + 3*33(小标题) + 6*70(列表项) = 552 ≤ 557  → 整页放得下
    //
    // ⚠ 这里**只能有一行**。曾经有两行额外的说明项:
    //     「生效方式 / 立即生效」 —— 与本页副标题「· 按下即生效」重复
    //     「适用游戏 / 全部通用」 —— 作者已决定用「关于」取代它（却没删）
    //   两行一起把主页面顶到 8 项 = 692px > 557px，于是:
    //     · 「关于本插件」掉到裁剪区外 —— 用户找不到作者与 QQ 群的入口
    //     · 「适用游戏」被裁剪矩形从中间切开 —— 底部半行残影
    //   由 tools/check_preview_clip.py（主页面必须完整可见）与
    //   tests/test_layout.cpp（整页高度 ≤ VISIBLE_HEIGHT）两条断言守着。
    //   要再加行请先算高度: 3 小标题下最多 6 项。
    // QQ 群等长文本放在独立的 InfoGui 页（那里不受值列宽度限制）。
    list->addItem(new tsl::elm::CategoryHeader("使用说明"));

    // 作者署名行。
    //
    // 名字用完整的 "hnayzdf"（7 个半角字符）。
    // 宽度核算: 「关于」2 字 = 46px，值 "hnayzdf" 7 半角 ≈ 84px，
    // 合计 130px，远小于可用宽度（>300px）—— 安全。
    // 由 tests/test_layout.cpp 的宽度断言守着（上限 8.0 全角字宽）。
    auto *about = new tsl::elm::ListItem("关于本插件", "hnayzdf");
    about->setClickListener([](u64 keys) -> bool {
        if (keys & HidNpadButton_A) {
            tsl::changeTo<InfoGui>();
            return true;
        }
        return false;
    });
    list->addItem(about);

    frame->setContent(list);
    return frame;
}

void MainGui::update() {
    // createUI() 只在首次进入时调用一次；每次回到本页面走的都是 update()。
    // 所以「当前画面」的刷新必须放在这里，否则会一直显示旧值。

    // ═══════════════════════════════════════════════════════════════════════
    // ⚠ 未连接时**什么都不做** —— 包括不做轮询、不重建页面
    // ═══════════════════════════════════════════════════════════════════════
    // 这里曾经写成: 轮询状态 → 若 service_ok 发生变化就 tsl::changeTo<MainGui>()
    // 重建页面。那个写法有两个真问题:
    //
    //   1. changeTo 会再次触发 createUI() → 再次 refresh_state()。
    //      状态在切换中抖动时就是**重建循环**。
    //   2. "未连接"这条路径本来就不该有任何运行期活动 ——
    //      它是最容易出事的路径，越安静越好。
    //
    // 现在: 未连接 = 静态引导页，零 IPC、零重建。
    //       ⚠ 引导页上**没有**「重试连接」按钮 —— 它刻意做成零按钮、零回调
    //       （见上面 createUI 里的说明: pgl 那次教训之后不再在引导页放任何
    //       动作）。所以本插件不提供运行期重连: 想连上必须让 Fizeau 先跑起来
    //       再重新打开插件（重开一次 overlay 就会重新走 createUI 的探测）。
    //
    // 代价是服务中途起停不会自动反映到界面上。这是刻意的取舍:
    // 用户重开一次插件，好过菜单崩掉。
    if (!g_state.service_ok)
        return;

    if (++g_frame_counter < REFRESH_INTERVAL_FRAMES)
        return;
    g_frame_counter = 0;

    refresh_state();

    // 服务在运行中掉线: 不再重建页面（那正是上面说的隐患），
    // 只把状态文字更新为「未连接」，并把各项显示清空。
    if (!g_state.service_ok) {
        if (g_filter_item) g_filter_item->setValue(filter_state_text());
        if (g_effect_item) g_effect_item->setValue("—");
        if (g_profile_item) g_profile_item->setValue("—");
        return;
    }

    // 只更新文本，不重建列表（重建会打断用户的选中位置）。
    //
    // 先比较再赋值: ListItem::setValue() 内部会重置 m_maxWidth 并触发
    // 宽度重算，值没变时没必要做。同时这也是个廉价的"无变化就不刷新"优化。
    if (g_filter_item) {
        const std::string v = filter_state_text();
        if (g_filter_item->getValue() != v) g_filter_item->setValue(v);
    }
    if (g_effect_item) {
        const std::string v = current_description();
        if (g_effect_item->getValue() != v) g_effect_item->setValue(v);
    }
    if (g_profile_item) {
        const std::string v = profile_text();
        if (g_profile_item->getValue() != v) g_profile_item->setValue(v);
    }
}

// ═══════════════════════════════════════════════════════════ 预设页

tsl::elm::Element *PresetGui::createUI() {
    // 进入本页时记下当前设置 —— 离开时会写回（除非用户按 A 确认）
    begin_preview();

    auto *frame = new tsl::elm::OverlayFrame("选择滤镜",
                                             FNX_VERSION_LABEL " · 移动预览 / A 确认");
    auto *list  = new tsl::elm::List();

    // ═══════════════════════════════════════════════════════════════════════
    // 分类做成**可折叠的下拉式**
    // ═══════════════════════════════════════════════════════════════════════
    // 100 个滤镜平铺要滚很久。改成:
    //     · 默认只显示 11 个分类行（一屏放得下）
    //     · 按 A 展开某类，它的滤镜出现在该行下方
    //     · 再按 A 收起
    //
    // ⚠ 实现方式是「点击后重建整个页面」，**不是动态增删列表项**。
    //
    //   第一版用 List::addItem / removeItem 在点击回调里动态增删，
    //   真机结果是**按 A 就蓝屏**。原因是 List 的增删按帧惰性生效
    //   （m_itemsToAdd / m_itemsToRemove），而点击回调发生在输入处理阶段、
    //   列表正在遍历；在遍历中改它的待处理队列，会与 requestFocus
    //   （有待处理项时返回 nullptr）、索引重算、滚动修正相互纠缠。
    //
    //   现在: 分类行只切换一个**静态**展开状态，然后 changeTo<PresetGui>()。
    //   界面按新状态从头构建，效果一样，但没有任何"遍历中改列表"的操作。
    //   展开状态存静态变量，所以重建后仍是用户上次看到的展开情况。
    //
    //   ⚠ changeTo 在按钮回调里是安全的（用户明确操作、一帧一次）；
    //     在 update() 里才危险（每帧跑 → 状态抖动时无限重建）。
    //     后者已由 tools/check_fizeau_safety.py 禁止。
    // ═══════════════════════════════════════════════════════════════════════

    // 每个分类的预设范围（用下标区间表示，不持有 vector 元素引用）
    struct GroupRange {
        PresetGroup group;
        std::size_t begin;
        std::size_t end;
    };
    std::vector<GroupRange> groups;

    for (std::size_t i = 0; i < PRESETS.size(); ++i) {
        if (groups.empty() || groups.back().group != PRESETS[i].group) {
            groups.push_back(GroupRange{PRESETS[i].group, i, i});
        }
        groups.back().end = i + 1;
    }

    fnx::fnxLog("[gui] 预设页: 构建分类行（下拉式）");

    for (std::size_t gi = 0; gi < groups.size(); ++gi) {
        const GroupRange &g = groups[gi];
        const std::size_t count = g.end - g.begin;

        // ── 分类行 ──
        //
        // ⚠ 回调只捕获 `list` 和 `gi`（值捕获下标，不是引用）。
        //   不捕获 groups —— 它是局部变量，重建页面后就不存在了，
        //   而回调可能被框架短暂持有。
        auto *hdr = new GroupHeaderItem(
            group_name(g.group), count, gi,
            [list]() {
                // ═══════════════════════════════════════════════════════
                // ⚠ 必须用 swapTo，**不能用 changeTo**
                // ═══════════════════════════════════════════════════════
                // 框架里两者语义不同:
                //   changeTo(gui)  tesla.hpp:12016  push      ← 压栈
                //   swapTo(gui)    tesla.hpp:12043  pop+push  ← 替换栈顶
                //
                // 用 changeTo 的话，每展开一次就多压一个 PresetGui，
                // 于是:
                //   · 按 B（goBack 只弹一层）会回到**上一层那个旧 PresetGui**，
                //     看起来就是"位置不对/回到旧状态"
                //   · 栈被撑高后，goBack 会走到 tesla.hpp:12120 那个
                //     "栈见底 → hide() 整个 overlay" 的分支，
                //     表现为"按 B 直接退出插件"
                //
                // swapTo 先弹当前页再压新页，栈深度不变 —— B 一定回主页面。
                // ═══════════════════════════════════════════════════════
                (void)list;
                tsl::swapTo<PresetGui>();
            },
            // 上报焦点: 记住光标停在这个分类行上，
            // 下次重建时恢复到这一行（否则会跳回最上面）
            [gi]() { noteCursorOnGroup(gi); });
        hdr->installClickListener();
        list->addItem(hdr);

        // 逐组埋点: 崩在某组就能从日志看出是哪一组
        {
            char gbuf[96];
            std::snprintf(gbuf, sizeof(gbuf),
                          "[gui]   组 %zu/%zu 已建: %s (展开=%d)",
                          gi + 1, groups.size(), group_name(g.group),
                          fnx::ui::groupExpanded(gi) ? 1 : 0);
            fnx::fnxLog(gbuf);
        }

        if (!fnx::ui::groupExpanded(gi))
            continue;

        // ── 展开时: 把该类下的滤镜行加进来 ──
        for (std::size_t i = g.begin; i < g.end; ++i) {
            const Preset *pp = &PRESETS[i];
            const std::size_t ii = i - g.begin;   // 该分类内的序号

            // ── 用 PreviewListItem: 光标移上来就立即预览 ──
            //
            // 预览的实际动作是 apply_preset —— 特斯拉 overlay 是半透明的，
            // 游戏画面在底下透出来，所以画面立刻变化，用户直接看到效果。
            //
            // ⚠ 回调里只捕获 pp（指向 PRESETS 的常量，生命周期是整个程序），
            //   不捕获任何局部对象 —— 页面会被 changeTo 重建，局部对象会失效。
            auto *row = new PreviewListItem(
                pp->name, pp->desc, true,
                [pp, gi, ii]() {
                    // 两件事: ① 实时预览 ② 记住光标位置
                    //
                    // 两者都用 g_userNavigated 作为"这是用户操作"的判据 ——
                    // 框架第一帧的强制聚焦、页面重建后的自动聚焦都会调
                    // setFocused，那些不是用户选择（预览功能已因此出过 bug）。
                    preview_preset(*pp);
                    noteCursorOnPreset(gi, ii);
                });

            row->setClickListener([pp](u64 keys) -> bool {
                if (!(keys & HidNpadButton_A))
                    return false;

                if (!g_state.service_ok) {
                    tsl::notification->showNow("未连接 Fizeau", 26, "无法应用");
                    return true;
                }
                // 光标已经把它预览上去了，这里只需"确认"——
                // commit 之后离开页面就不会再恢复原设置
                if (apply_preset(*pp)) {
                    commit_preview();
                    refresh_state();   // 回读真实状态，主界面显示实际值
                    tsl::notification->showNow(pp->name, 26, "已应用");
                } else {
                    tsl::notification->showNow("应用失败", 26, "检查服务状态");
                }
                return true;
            });
            list->addItem(row);
        }
        {
            char b2[80];
            std::snprintf(b2, sizeof(b2), "[gui]   组 %zu 展开，加入 %zu 项",
                          gi + 1, count);
            fnx::fnxLog(b2);
        }
    }

    // 把每个分类行在列表中的实际下标写进日志 ——
    // 这是判断"索引算错"还是"滚动错觉"的关键依据
    {
        std::size_t row = 0;
        for (std::size_t k = 0; k < groups.size(); ++k) {
            char rb[112];
            std::snprintf(rb, sizeof(rb),
                          "[gui] 行号: 分类 idx=%zu 「%s」在第 %zu 行%s",
                          k, group_name(groups[k].group), row,
                          fnx::ui::groupExpanded(k) ? "（已展开）" : "");
            fnx::fnxLog(rb);
            row += 1;
            if (fnx::ui::groupExpanded(k))
                row += groups[k].end - groups[k].begin;
        }
    }

    fnx::fnxLog("[gui] 预设页: 构建完成 → setContent");

    frame->setContent(list);

    // ═══════════════════════════════════════════════════════════════════════
    // 恢复光标位置 —— 否则 changeTo 重建后光标会跳回列表最上面
    // ═══════════════════════════════════════════════════════════════════════
    // 展开/收起分类会重建整个页面，而 List 构造时 m_focusedIndex = 0，
    // 用户刚点的那一行就丢了（表现为"点击分类后选择框跳到最上面"）。
    //
    // 这里按记录的位置把光标设回去。下标要**按已展开的分类累计** ——
    // 与实际构建顺序一致（分类行 1 行，展开时后面跟 count 行）。
    // ═══════════════════════════════════════════════════════════════════════
    // ═══════════════════════════════════════════════════════════════════════
    // 恢复光标位置 —— 用 jumpToItem，不能用 setFocusedIndex
    // ═══════════════════════════════════════════════════════════════════════
    // ⚠ 为什么必须用 jumpToItem（第一版用 setFocusedIndex，真机无效）:
    //
    //   List::draw 在新列表的**第一帧**有这样一段（tesla.hpp:5791）:
    //       } else if (!m_hasSetInitialFocusHack && !m_items.empty()) {
    //           // NO JUMP: Set up focus on first item
    //           m_focusedIndex = i;        // ← 强制设到第一个可选项
    //   于是在 createUI 里 setFocusedIndex 设的值会被它覆盖。
    //
    //   而同一个 if 的**上一分支**（5788）走的是 jump:
    //       if (m_pendingJump && !m_items.empty()) {
    //           resolveJumpImmediately();  // 它会把 m_hasSetInitialFocusHack 置 true
    //   置 true 之后上面那个分支就不会执行 —— 光标得以保留。
    //
    // jumpToItem 的匹配靠 matchesJumpCriteria，ListItem 的实现比较
    // **m_text / m_value**，也就是列表项实际显示的文字。所以:
    //     分类行 → jumpToItem(它现在显示的标题，如「▶ 电影(14)」)
    //     滤镜行 → jumpToItem(预设名, 说明)
    // ═══════════════════════════════════════════════════════════════════════
    if (g_cursorKind == CursorKind::Group &&
        g_cursorGroup < groups.size()) {
        // 分类行: 直接用它当前显示的标题（含展开符号与计数）
        const std::string title =
            std::string(fnx::ui::groupExpanded(g_cursorGroup) ? "\u25BC "
                                                              : "\u25B6 ") +
            group_name(groups[g_cursorGroup].group) +
            "(" + std::to_string(groups[g_cursorGroup].end -
                                 groups[g_cursorGroup].begin) + ")";
        {
            const std::string msg =
                "[gui] 恢复: 请求跳到分类行，title=「" + title + "」";
            fnx::fnxLog(msg.c_str());
        }
        list->jumpToItem(title, "");

    } else if (g_cursorKind == CursorKind::Preset &&
               g_cursorGroup < groups.size() &&
               fnx::ui::groupExpanded(g_cursorGroup)) {
        const GroupRange &cg = groups[g_cursorGroup];
        const std::size_t idx = cg.begin + g_cursorItem;
        if (idx < cg.end) {
            // 滤镜行: name + desc（ListItem 的 m_text / m_value）
            char b2[128];
            std::snprintf(b2, sizeof(b2),
                          "[gui] 恢复: 请求跳到滤镜 grp=%zu item=%zu "
                          "name=「%s」",
                          g_cursorGroup, g_cursorItem, PRESETS[idx].name);
            fnx::fnxLog(b2);
            list->jumpToItem(PRESETS[idx].name, PRESETS[idx].desc);
        }
    }
    fnx::fnxLog("[gui] 预设页: createUI 即将返回");
    return frame;
}


/*
 * 检测「用户是否真的在移动光标」。
 *
 * ⚠ 顺序说明（先看清楚再改）: 框架里一帧的实际顺序是
 *
 *     overlay->loop()      → Gui::update() → Gui::draw()      (tesla.hpp:11371-11373)
 *     overlay->handleInput()                                   (tesla.hpp:13847)
 *
 * 也就是 **update() 在前、handleInput() 在后** —— 与直觉相反。
 * 所以本函数置下的标志不是"本帧 update 立刻消费"，而是**留给下一帧**:
 *   · 本帧 handleInput 置位 → List 处理方向键 → setFocused → 预览回调，
 *     此刻标志已经是 true，预览照常触发（这是它必须置位的原因）；
 *   · 下一帧 update() 看到 g_navThisFrame == true → 不清 g_userNavigated，
 *     然后把它清零。于是标志的有效窗口正好覆盖"用户操作"这几帧，
 *     而框架自己的首帧强制聚焦（那时还没有任何方向输入）不会被误判。
 *
 * ⚠ 只在 keysDown（本帧新按下）里看方向键 —— keysHeld 是一直按着，
 *   那会导致按住方向键时每帧都触发预览，写入频率过高。
 */
bool PresetGui::handleInput(u64 keysDown, u64 keysHeld,
                            const HidTouchState &touchPos,
                            const HidAnalogStickState leftJoyStick,
                            const HidAnalogStickState rightJoyStick) {
    (void)keysHeld; (void)touchPos;
    (void)leftJoyStick; (void)rightJoyStick;

    if (fnx::ui::isNavigationInput(keysDown)) {
        g_userNavigated = true;
        g_navThisFrame = true;
    }
    return false;   // 不吞输入，让 List 正常处理移动
}


/*
 * 本页析构 = 离开本页（swapTo 替换、或 goBack 返回主页面）。
 *
 * 统一在这里结束预览会话:
 *   · 展开/收起分类 → swapTo 销毁旧页 → 这里恢复 → 新页重新捕获基准
 *   · 按 B 回主页面 → 销毁 → 这里恢复
 * 两处行为一致，不需要在别的地方重复处理。
 */
PresetGui::~PresetGui() {
    end_preview();
}

void PresetGui::update() {
    // 没有方向输入的那一帧就把导航意图清掉 ——
    // 否则一次方向输入会一直留着，后续任何 setFocused 都会被当成用户操作
    if (!g_navThisFrame)
        g_userNavigated = false;
    g_navThisFrame = false;

    // ⚠ 只在第一次调用时写日志 —— update 每帧都跑，
    //   不能每帧写 SD 卡（会把卡写爆，也拖慢帧率）。
    //
    // 这一行的意义: 它是"**update 已经进入**"的证据。注意它的位置 ——
    // 框架一帧的顺序是 update() → draw() → handleInput()（tesla.hpp:11371-11373
    // 与 13847），所以这一行**不代表已经渲染成功**，它只说明:
    //   · 日志里有它  → createUI() 走完了，且第一帧的 update 没崩；
    //                  之后崩的话，范围在 draw / 输入处理
    //   · 日志里没有它 → 崩在 createUI() 或第一帧 update 之前
    // （早先这里写成"渲染已走通"，那是错的: update 跑在 draw 之前。）
    static bool logged = false;
    if (!logged) {
        logged = true;
        fnx::fnxLog("[gui] 预设页 update 首帧（createUI 已完成）");
    }
}

// ═══════════════════════════════════════════════════════════ 信息页

/*
 * 关于 / 联系方式
 *
 * 单独一页的原因: InfoGui 的 ListItem「值」列同样有宽度限制，
 * 但这一页没有条目数量压力，可以把 QQ 群号逐行列出 —— 群号是 9 位数字，
 * 放在主页面那一行会把名字挤掉（见 presets.hpp 的宽度说明）。
 *
 * 行数: 3 个小标题 + 8 个列表项
 *       33 + 3*33 + 8*70 = 692 > 557 → 需要滚动
 * 滚动是正常的（列表机制支持），但要注意**底部会被裁剪**，
 * 所以最后一项应是"结尾"性质的说明，而不是重要信息。
 * 这里最后放的是版本信息，滚动到底即可看到。
 */
tsl::elm::Element *InfoGui::createUI() {
    auto *frame = new tsl::elm::OverlayFrame("关于本插件", FNX_VERSION_LABEL " · 超能滤镜");
    auto *list  = new tsl::elm::List();

    // ── 作者 ──
    list->addItem(new tsl::elm::CategoryHeader("作者"));
    list->addItem(new tsl::elm::ListItem("作者", "hnayzdf"));

    // ── 交流群 ──
    list->addItem(new tsl::elm::CategoryHeader("QQ 交流群"));
    list->addItem(new tsl::elm::ListItem("1群", "259121473"));
    list->addItem(new tsl::elm::ListItem("2群", "712676771"));
    list->addItem(new tsl::elm::ListItem("3群", "71627115"));

    // ── 说明 ──
    list->addItem(new tsl::elm::CategoryHeader("说明"));
    list->addItem(new tsl::elm::ListItem("滤镜数", "100种"));
    list->addItem(new tsl::elm::ListItem("引擎", "Fizeau"));
    list->addItem(new tsl::elm::ListItem("版本", FNX_VERSION_LABEL));

    frame->setContent(list);
    return frame;
}

void InfoGui::update() {}


} // namespace fnx::ui
