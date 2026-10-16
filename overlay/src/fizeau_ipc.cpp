/*
 * FilterNX — 大气层中文滤镜插件
 *
 * fizeau_ipc.cpp — Fizeau IPC 客户端实现
 *
 * ═══════════════════════════════════════════════════════════════════════════
 * 为什么用 libnx 的 serviceDispatch* 宏而不是手写 CMIF
 * ═══════════════════════════════════════════════════════════════════════════
 * 手写 CMIF 需要自己构造请求头、解析响应头（含 SFCO 魔数、结果码位置、
 * 对齐规则）。libnx 的 cmifParseResponse() 内部逻辑不少，手写极易出错，
 * 而错误的后果是"设置静默失效"，在真机上很难定位。
 *
 * serviceDispatch* 宏正是为这种情况准备的，且被所有官方 homebrew 使用：
 *     serviceDispatchIn     (srv, cmd, in)            有输入无输出
 *     serviceDispatchOut    (srv, cmd, out)           无输入有输出
 *     serviceDispatchInOut  (srv, cmd, in, out)       两者皆有
 *
 * 本文件里的调用形式与 Fizeau 官方 fizeau.c 逐行对应，便于交叉核对。
 *
 * GPLv2，详见 LICENSE。
 */

#include <switch.h>
#include <sys/stat.h>
#include <cstring>

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

#include "fizeau_ipc.hpp"

namespace fnx {

namespace {
Service g_session = {};
bool    g_initialized = false;

// ── 会话守卫 ──
//
// ═══════════════════════════════════════════════════════════════════════════
// 这是本插件最严重的一次崩溃的修复
// ═══════════════════════════════════════════════════════════════════════════
// 症状: 机器上没装 / 没运行 Fizeau 时，一打开本插件，**整个特斯拉菜单炸掉**。
//
// 根因: 所有 IPC 函数都直接用 g_session 发请求，**没有检查会话是否建立**:
//
//     Result fzGetIsActive(bool *out) {
//         u8 tmp = 0;
//         auto rc = serviceDispatchOut(&g_session, 0, tmp);   // ← 空句柄！
//     }
//
//   fzInitialize() 失败时 g_session 保持全零（句柄 0 是无效句柄），
//   拿它发 IPC 会触发 svcSendSyncRequest 失败，进而把菜单带崩。
//
//   main.cpp 里写着"失败也不中止 —— 界面会显示未连接"，
//   但那个设计**从未真正生效**，因为崩溃发生在更底层。
//
// 修法: 把守卫放进**每个 IPC 函数内部**，而不是依赖调用方记得先检查。
//   调用方可能忘记；函数自己不会。
//
//   这不是"防御性编程"的洁癖 —— 是这次故障的直接教训:
//   只要有任何一条路径漏检，用户看到的就是菜单崩溃，而不是提示页。
// ═══════════════════════════════════════════════════════════════════════════
inline bool session_ready() {
    return g_initialized && serviceIsActive(&g_session);
}

// 会话未就绪时返回的错误码。
//
// 刻意用一个**非零且可辨认**的值，而不是 0:
//   0 表示成功。若这里返回 0，调用方会以为操作成功，
//   于是界面显示"已开启"而实际什么都没发生 —— 比崩溃更难查。
inline constexpr Result RC_NO_SESSION = MAKERESULT(Module_Libnx, LibnxError_NotInitialized);
} // namespace

// ---------------------------------------------------------------- 会话

Result fzInitialize() {
    if (session_ready())
        return 0;

    // 上一次尝试可能失败过并留下半开状态，先清干净再重试。
    // serviceClose 对未激活的句柄是安全的。
    if (g_initialized) {
        serviceClose(&g_session);
        g_initialized = false;
        g_session = {};
    }

    auto rc = smGetService(&g_session, FIZEAU_SERVICE);
    if (R_FAILED(rc)) {
        // 关键: 失败时把句柄显式清零，确保 session_ready() 一定返回 false，
        // 后续 IPC 全部走"无会话"分支而不是拿垃圾句柄去发请求。
        g_session = {};
        g_initialized = false;
        return rc;
    }

    g_initialized = true;
    return 0;
}

void fzExit() {
    if (session_ready())
        serviceClose(&g_session);
    g_session = {};
    g_initialized = false;
}

bool fzIsSessionReady() {
    return session_ready();
}

// ---------------------------------------------------------------- 文件系统探测

/*
 * 纯文件系统探测 —— 一个 IPC 都不发。
 *
 * ⚠ 为什么不用 smGetService 判断:
 *   真机故障是「Fizeau 没运行时打开插件整个菜单消失」。
 *   既然故障恰恰发生在 Fizeau 不在的时候，就不能假设那次 IPC 安全。
 *   读文件系统没有这个问题 —— 最坏情况是返回"文件不存在"。
 *
 * ⚠ 为什么不用 stat() 而用 fopen():
 *   libnx 的 devoptab 对 stat 的支持在不同固件上有差异，
 *   而 fopen/fclose 是最基础、最可靠的路径。读一个字节即可。
 */
namespace {

bool fileExists(const char *path) {
    std::FILE *f = std::fopen(path, "rb");
    if (!f)
        return false;
    std::fclose(f);
    return true;
}

} // namespace

FzPresence fzDetectPresence() {
    // Fizeau 的 sysmodule 目录（title id 0100000000000F12）
    static constexpr const char *EXEFS =
        "sdmc:/atmosphere/contents/0100000000000F12/exefs.nsp";
    static constexpr const char *BOOT2 =
        "sdmc:/atmosphere/contents/0100000000000F12/flags/boot2.flag";

    if (!fileExists(EXEFS))
        return FzPresence::NotInstalled;

    if (!fileExists(BOOT2))
        return FzPresence::InstalledNoBoot;

    return FzPresence::InstalledBoot;
}

bool fzIsAvailable() {
    // ═══════════════════════════════════════════════════════════════════════
    // 只做一件事: 尝试连接。连不上就是不可用。
    // ═══════════════════════════════════════════════════════════════════════
    //
    // ⚠ 这里曾经**先**用 Atmosphère 的 "IsServiceActive" 扩展查询:
    //
    //     tipcDispatchInOut(smGetServiceSessionTipc(), 65100, name, alive)
    //
    //   那条路径虽然 Fizeau 官方 overlay 也在用，但它依赖:
    //     · 系统运行 Atmosphère（而非其他 CFW）
    //     · AMS 版本支持 65100 这个扩展命令
    //     · TIPC 会话可用
    //   三个前提任一不成立，行为就不可预期 —— 而这一步发生在**判断可用性**
    //   的过程里，本身就不该引入额外风险。
    //
    //   已去掉。现在只用 smGetService（libnx 最基础、所有版本都有的路径）:
    //   服务不存在时它干净地返回错误码，不会崩。
    //
    //   代价只是"多一次连接尝试"，而连接失败本来就要走引导页。
    Service probe = {};
    auto rc = smGetService(&probe, FIZEAU_SERVICE);
    if (R_FAILED(rc)) {
        // 确保不留半开句柄
        probe = {};
        return false;
    }
    serviceClose(&probe);
    return true;
}

// ---------------------------------------------------------------- 命令
// 每个函数与 Fizeau 官方 fizeau.c 的实现一一对应
//
// ⚠ 每个函数开头都必须 session_ready() 检查 —— 见上方"会话守卫"的说明。

Result fzGetIsActive(bool *out_active) {
    if (!session_ready())
        return RC_NO_SESSION;

    // 官方: u8 tmp; serviceDispatchOut(&srv, GetIsActive, tmp);
    u8 tmp = 0;
    auto rc = serviceDispatchOut(&g_session, 0 /* GetIsActive */, tmp);
    if (R_SUCCEEDED(rc) && out_active)
        *out_active = (tmp != 0);
    return rc;
}

Result fzSetIsActive(bool active) {
    if (!session_ready())
        return RC_NO_SESSION;

    // 官方: serviceDispatchIn(&srv, SetIsActive, is_active);
    // 注意官方传的实参是 bool，宏内部按 sizeof(bool)=1 发送
    return serviceDispatchIn(&g_session, 1 /* SetIsActive */, active);
}

Result fzGetProfile(std::uint32_t id, FzProfile *out_profile) {
    if (!session_ready())
        return RC_NO_SESSION;

    // 官方: FizeauProfile tmp; serviceDispatchInOut(&srv, GetProfile, id, tmp);
    FzProfile tmp = {};
    auto rc = serviceDispatchInOut(&g_session, 2 /* GetProfile */, id, tmp);
    if (R_SUCCEEDED(rc) && out_profile)
        *out_profile = tmp;
    return rc;
}

Result fzSetProfile(std::uint32_t id, const FzProfile &profile) {
    if (!session_ready())
        return RC_NO_SESSION;

    // 官方:
    //   struct { FizeauProfileId id; FizeauProfile profile; } tmp = { id, *profile };
    //   return serviceDispatchIn(&g_srv, SetProfile, tmp);
    struct Request {
        std::uint32_t id;
        FzProfile     profile;
    } tmp = { id, profile };

    static_assert(sizeof(Request) == 96, "SetProfile 请求负载必须为 96 字节");
    return serviceDispatchIn(&g_session, 3 /* SetProfile */, tmp);
}

Result fzGetActiveProfileId(bool is_external, std::uint32_t *out_id) {
    if (!session_ready())
        return RC_NO_SESSION;

    // 官方: serviceDispatchInOut(&srv, GetActiveProfileId, is_external, id);
    std::uint32_t id = 0;
    auto rc = serviceDispatchInOut(&g_session, 4 /* GetActiveProfileId */, is_external, id);
    if (R_SUCCEEDED(rc) && out_id)
        *out_id = id;
    return rc;
}

// ---------------------------------------------------------------- 辅助

void fzFillProfile(FzProfile *out, const FzSettings &s,
                   std::uint32_t components, std::uint32_t filter) {
    if (!out)
        return;

    // day 与 night 写同一份设置：
    //   Fizeau 按 dusk/dawn 自动在两组之间切换。只写一组的话，用户会在
    //   黄昏时刻看到画面突然变化 —— 意外行为，且很难排查。
    out->day_settings   = s;
    out->night_settings = s;

    out->components = components;
    out->filter     = filter;

    // ⚠ 刻意**不动** out 里已有的 dusk_begin / dusk_end / dawn_begin /
    //   dawn_end / dimming_timeout。
    //
    //   本函数曾经把这五项无条件写成 21:00 / 07:00 / 30:00 —— 那会把用户
    //   在官方 overlay 里调过的黄昏黎明时刻静默重置，而且因为注释写着
    //   "保留默认的黄昏/黎明时刻"，看代码的人不会察觉。
    //
    //   调用方传进来的必须是 fzGetProfile() 读回的真实 profile；
    //   若传 {}，这些字段就是 0（下发后由 Fizeau 的 sanitize 钳回合法值）。
}

// ═══════════════════════════════════════════════════════════════════════════
// 配置落盘 —— 让设置在重启后仍然生效
// ═══════════════════════════════════════════════════════════════════════════
//
// 为什么必须有这一段（真机故障的根因）:
//
//   用户反馈「每次重启之后屏幕会变黄，要去滤镜那里重新调节」。
//
//   根因不在画面处理，而在**持久化责任归属**:
//     · Fizeau 的 sysmodule 开机只 parse_config() 读一次盘，之后只认 IPC；
//     · ipc_server.c 里没有任何写盘代码；
//     · 写盘是 **overlay 的职责** —— 官方 overlay 在析构时调 config.write()
//       （FizeauOverlayGui::~FizeauOverlayGui）。
//
//   本插件只发 IPC，等于只改了运行态。重启后 sysmodule 读回盘上那份旧配置
//   （整合包预置的黄屏参数），于是用户看到的画面又变回偏黄。
//
//   修法: 插件自己把完整配置写回盘，格式与 Fizeau 的 Config::make() 一致，
//   值全部来自 IPC 读回的真实状态 —— 既包含用户刚选的滤镜，也不覆盖
//   他在官方 overlay 里做过的其它设置。
//
// ⚠ 这里**不做 sanitize**，与官方 Config::write() 的行为一致:
//   值本来就是从 Fizeau 读回来的，已在合法范围内。自己再钳一次反而可能
//   与官方行为产生分歧（例如 range 的合法下限并非 0）。
namespace {

inline constexpr const char *CONFIG_MAIN   = "sdmc:/config/Fizeau/config.ini";
inline constexpr const char *CONFIG_ALT    = "sdmc:/switch/Fizeau/config.ini";
inline constexpr const char *CONFIG_DIRS[] = { "sdmc:/config/Fizeau",
                                               "sdmc:/switch/Fizeau" };

/*
 * 决定把配置写到哪个路径 —— 必须与 Fizeau 的 Config::find_config() 同序。
 *
 * 上游 find_config() 遍历 {"/switch/Fizeau/config.ini", "/config/Fizeau/config.ini"}，
 * 返回**第一个 stat 成功的**；都不存在时返回**第二个**（即 /config/Fizeau/）。
 * 两者都保留，因为整合包可能只放了其中一个。
 */
const char *resolveConfigPath() {
    if (fileExists(CONFIG_ALT))
        return CONFIG_ALT;
    if (fileExists(CONFIG_MAIN))
        return CONFIG_MAIN;
    return CONFIG_MAIN;   // 与上游一致: 新建时用 /config/Fizeau/
}

/*
 * 挂载 SD 卡。
 *
 * ⚠ 这是本插件第一次**写** SD 卡（此前只读 log/probe 文件），所以不能想当然:
 *   · 已经挂上（官方 overlay 或框架挂过）→ 直接用，别重复挂；
 *   · 没挂 → 自己挂，并在写完的**最后**卸载，避免把挂载状态留给别的 overlay。
 */
struct SdAccess {
    bool mounted_here = false;
    bool ok           = false;

    SdAccess() {
        if (R_SUCCEEDED(fsInitialize())) {
            if (R_SUCCEEDED(fsdevMountSdmc())) {
                mounted_here = true;
                ok           = true;
            } else {
                // NX_EEXIST / 已被挂载 —— 仍然可用，只是不该由我们卸载。
                ok = true;
            }
        }
    }

    ~SdAccess() {
        if (mounted_here)
            fsdevUnmountDevice("sdmc");
        fsExit();
    }
};

void mkdirFor(const char *file_path) {
    for (const char *d : CONFIG_DIRS) {
        if (std::strstr(file_path, d) == file_path)
            ::mkdir(d, 0777);      // 返回 -1（已存在/建不了）都不影响后面
    }
}

// 与 Fizeau 的 format_time 一致: "%02d:%02d"
std::string fmtTime(FzTime t) {
    char b[8];
    std::snprintf(b, sizeof(b), "%02u:%02u", unsigned(t.h), unsigned(t.m));
    return std::string(b);
}

// 与 Fizeau 的 format_range 一致: "%.2f-%.2f"
std::string fmtRange(const FzColorRange &r) {
    char b[32];
    std::snprintf(b, sizeof(b), "%.2f-%.2f", double(r.lo), double(r.hi));
    return std::string(b);
}

std::string fmtComponents(std::uint32_t c) {
    if (c == COMP_NONE)
        return "none";
    if (c == COMP_ALL)
        return "all";
    std::string s;
    if (c & COMP_RED)   s.push_back('r');
    if (c & COMP_GREEN) s.push_back('g');
    if (c & COMP_BLUE)  s.push_back('b');
    return s.empty() ? std::string("none") : s;
}

// 单通道筛选: 只有**恰好一位**被置起才算有效，其余写 none。
// 与官方 format_filter 的语义一致（多位置起时落到 default → none）。
std::string fmtFilter(std::uint32_t f) {
    if (f != 0 && (f & (f - 1)) == 0) {
        if (f == COMP_RED)   return "red";
        if (f == COMP_GREEN) return "green";
        if (f == COMP_BLUE)  return "blue";
    }
    return "none";
}

// 写入一个 profile 段（字段名与顺序对齐 Config::make()）
std::string profileSection(const std::string &tag, const FzProfile &p) {
    auto f = [](double v) {
        char b[32];
        std::snprintf(b, sizeof(b), "%f", v);
        return std::string(b);
    };

    std::string s = "[" + tag + "]\n";
    s += "dusk_begin        = " + fmtTime(p.dusk_begin) + "\n";
    s += "dusk_end          = " + fmtTime(p.dusk_end)   + "\n";
    s += "dawn_begin        = " + fmtTime(p.dawn_begin) + "\n";
    s += "dawn_end          = " + fmtTime(p.dawn_end)   + "\n";
    s += "temperature_day   = " + std::to_string(p.day_settings.temperature)   + "\n";
    s += "temperature_night = " + std::to_string(p.night_settings.temperature) + "\n";
    s += "saturation_day    = " + f(p.day_settings.saturation)   + "\n";
    s += "saturation_night  = " + f(p.night_settings.saturation) + "\n";
    s += "hue_day           = " + f(p.day_settings.hue)          + "\n";
    s += "hue_night         = " + f(p.night_settings.hue)        + "\n";
    s += "components        = " + fmtComponents(p.components)    + "\n";
    s += "filter            = " + fmtFilter(p.filter)            + "\n";
    s += "contrast_day      = " + f(p.day_settings.contrast)     + "\n";
    s += "contrast_night    = " + f(p.night_settings.contrast)   + "\n";
    s += "gamma_day         = " + f(p.day_settings.gamma)        + "\n";
    s += "gamma_night       = " + f(p.night_settings.gamma)      + "\n";
    s += "luminance_day     = " + f(p.day_settings.luminance)    + "\n";
    s += "luminance_night   = " + f(p.night_settings.luminance)  + "\n";
    s += "range_day         = " + fmtRange(p.day_settings.range)   + "\n";
    s += "range_night       = " + fmtRange(p.night_settings.range) + "\n";
    // 官方这一行只写分:秒（h 被丢弃），照抄，避免与官方产物不一致
    s += "dimming_timeout   = " + fmtTime(FzTime{0, p.dimming_timeout.m,
                                                    p.dimming_timeout.s}) + "\n";
    s += "\n";
    return s;
}

} // namespace

bool fzSaveConfigToSd() {
    // 没有会话就别动盘 —— 读不到真实状态时写出去只会覆盖掉用户设置
    if (!session_ready())
        return false;

    bool active = false;
    std::uint32_t handheld = PROFILE_1, docked = PROFILE_1;
    if (R_FAILED(fzGetIsActive(&active)))
        return false;
    if (R_FAILED(fzGetActiveProfileId(false, &handheld)))
        handheld = PROFILE_1;
    if (R_FAILED(fzGetActiveProfileId(true, &docked)))
        docked = PROFILE_1;

    FzProfile profiles[PROFILE_TOTAL] = {};
    for (std::uint32_t i = 0; i < PROFILE_TOTAL; ++i) {
        if (R_FAILED(fzGetProfile(i, &profiles[i])))
            return false;      // 读不全就不写: 宁可不保存，也不要用半份数据覆盖配置
    }

    const char *path = resolveConfigPath();

    SdAccess sd;
    if (!sd.ok)
        return false;

    mkdirFor(path);

    std::string out;
    // 与官方 make() 一致: active 行可被注释掉（表示由用户显式设定过）
    out += std::string("active            = ") + (active ? "true" : "false") + "\n\n";
    out += "handheld_profile  = profile" + std::to_string(handheld + 1) + "\n";
    out += "docked_profile    = profile" + std::to_string(docked   + 1) + "\n\n";
    for (std::uint32_t i = 0; i < PROFILE_TOTAL; ++i)
        out += profileSection("profile" + std::to_string(i + 1), profiles[i]);

    std::FILE *fp = std::fopen(path, "w");
    if (!fp)
        return false;

    const std::size_t n = std::fwrite(out.c_str(), 1, out.length(), fp);
    std::fclose(fp);
    return n == out.length();
}

} // namespace fnx
