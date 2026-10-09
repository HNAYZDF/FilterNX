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
#include <cstring>

#include <cstdio>

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

    // 保留默认的黄昏/黎明时刻，不改动 Fizeau 的调度语义
    out->dusk_begin = FzTime{21, 0, 0};
    out->dusk_end   = FzTime{21, 30, 0};
    out->dawn_begin = FzTime{7, 0, 0};
    out->dawn_end   = FzTime{7, 30, 0};

    out->dimming_timeout = FzTime{30, 0, 0};
}

} // namespace fnx
