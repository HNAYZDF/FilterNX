/*
 * FilterNX — 大气层中文滤镜插件
 *
 * fizeau_ipc.hpp — Fizeau 的 IPC 协议与数据模型
 *
 * ═══════════════════════════════════════════════════════════════════════════
 * 这一版做了什么改变
 * ═══════════════════════════════════════════════════════════════════════════
 * 上一版只写 Fizeau 的配置文件，必须重启才生效。本版实现它的 IPC 协议，
 * 因此**按下即生效，不需要重启**。
 *
 * Fizeau 的 sysmodule 常驻运行并注册了 "fizeau" 服务，命令如下：
 *     0 GetIsActive          空 → u8
 *     1 SetIsActive          u8
 *     2 GetProfile           u32 id → FizeauProfile
 *     3 SetProfile           {u32 id, FizeauProfile} → 空
 *     4 GetActiveProfileId   u8 is_external → u32
 *     5 SetActiveProfileId   {u8 is_external, u32 id}
 *
 * 布局已由 tests/test_fizeau_proto.cpp 逐字段验证（66 项断言全通过），
 * 包括结构体尺寸、每个字段的字节偏移、命令号与取值范围。
 * 这一步很关键：IPC 送的是整个结构体的裸字节，任何偏移错误都会让服务端
 * 收到错位数据 —— 表现为"设置没反应"或"画面怪怪的"，极难在真机上定位。
 *
 * 协议权威来源: https://github.com/averne/Fizeau  common/include/fizeau.h
 *
 * GPLv2，详见 LICENSE。
 */

#pragma once

#ifdef FNX_HOST_TEST
#include "switch_shim.h"
#else
#include <switch.h>
#endif

#include <cstdint>

namespace fnx {

// ---------------------------------------------------------------- 服务

inline constexpr const char *FIZEAU_SERVICE = "fizeau";

// Fizeau 的 title id。
//
// 来源: 官方 Makefile 的 FZ_TID
//   https://github.com/averne/Fizeau/blob/master/Makefile
// 它以 SystemProgram 形式安装在 atmosphere/contents/<此 tid>/
inline constexpr std::uint64_t FIZEAU_TITLE_ID = 0x0100000000000F12ULL;

// ---------------------------------------------------------------- 取值范围
// 来源: Fizeau common/include/types.h
// 越界值会被 Fizeau 的 sanitize() 静默钳制，导致预设与实际效果不符

inline constexpr std::uint32_t TEMP_MIN = 1000;    // 开尔文
inline constexpr std::uint32_t TEMP_D65 = 6500;    // D65 标准光源
inline constexpr std::uint32_t TEMP_MAX = 10000;

inline constexpr float SAT_MIN = 0.0f;
inline constexpr float SAT_MAX = 2.0f;

inline constexpr float HUE_MIN = -1.0f;
inline constexpr float HUE_MAX = 1.0f;

inline constexpr float CONTRAST_MIN = 0.0f;
inline constexpr float CONTRAST_MAX = 2.0f;

inline constexpr float GAMMA_MIN = 0.0f;
inline constexpr float GAMMA_MAX = 5.0f;

inline constexpr float LUMA_MIN = -1.0f;
inline constexpr float LUMA_MAX = 1.0f;

inline constexpr float RANGE_MIN = 0.0f;
inline constexpr float RANGE_MAX = 1.0f;

// ---------------------------------------------------------------- 组件
// 对应 Fizeau 的 Component 位掩码

inline constexpr std::uint32_t COMP_NONE  = 0;
inline constexpr std::uint32_t COMP_RED   = 1u << 0;
inline constexpr std::uint32_t COMP_GREEN = 1u << 1;
inline constexpr std::uint32_t COMP_BLUE  = 1u << 2;
inline constexpr std::uint32_t COMP_ALL   = COMP_RED | COMP_GREEN | COMP_BLUE;

// ---------------------------------------------------------------- 结构体
// 布局必须与 Fizeau 完全一致（已由主机侧测试验证尺寸与偏移）

struct __attribute__((aligned(4))) FzTime {
    std::uint8_t h, m, s;
};

struct FzColorRange {
    float lo, hi;
};

// 32 字节
struct FzSettings {
    std::uint32_t temperature;   // +0
    float         saturation;    // +4
    float         hue;           // +8
    float         contrast;      // +12
    float         gamma;         // +16
    float         luminance;     // +20
    FzColorRange  range;         // +24 (8 字节)
};
static_assert(sizeof(FzSettings) == 32, "FzSettings 必须为 32 字节");

// 92 字节
struct FzProfile {
    FzSettings    day_settings;    // +0
    FzSettings    night_settings;  // +32
    std::uint32_t components;      // +64
    std::uint32_t filter;          // +68
    FzTime        dusk_begin;      // +72
    FzTime        dusk_end;        // +76
    FzTime        dawn_begin;      // +80
    FzTime        dawn_end;        // +84
    FzTime        dimming_timeout; // +88
};
static_assert(sizeof(FzProfile) == 92, "FzProfile 必须为 92 字节");

// SetProfile 的请求负载（fizeau.c 里的匿名 struct）
struct FzSetProfileRequest {
    std::uint32_t id;
    FzProfile     profile;
};
static_assert(sizeof(FzSetProfileRequest) == 96, "请求负载必须为 96 字节");

// 档位
inline constexpr std::uint32_t PROFILE_1 = 0;
inline constexpr std::uint32_t PROFILE_TOTAL = 4;

// ---------------------------------------------------------------- 客户端

// 连接 Fizeau 服务。成功返回 0。
//
// ⚠ 失败是**正常情况**（没装 Fizeau），不是异常。调用方必须检查返回值，
//   并且在失败后**不要**再调用下面的命令函数 —— 虽然它们现在都有会话守卫
//   （不会崩），但会一律返回失败，界面上表现为"操作无效"。
Result fzInitialize();
void   fzExit();

// 会话是否已建立且仍然有效。
//
// 存在的意义: 让界面能在决定"是显示正常页还是引导页"时，
// 用**同一个判据**判断，而不是各自去猜。
bool fzIsSessionReady();

// 服务是否可用（不建立持久会话，用 AMS 扩展查询）
bool fzIsAvailable();

// ---------------------------------------------------------------- 文件系统探测
//
// ⚠ 这是**唯一不碰 IPC** 的检测手段。
//
// 用户诉求: 「检测没有启动提示，启动不该崩溃」——
// 也就是判断"Fizeau 在不在"本身必须绝对安全。
//
// smGetService 是一次 IPC。真机故障恰恰是「Fizeau 没运行时打开插件
// 整个菜单消失」，所以不能假设那次 IPC 一定安全。
//
// 这里改为**只读文件系统**，问三个问题:
//   · atmosphere/contents/0100000000000F12/exefs.nsp 存在吗？  → 装了没
//   · .../flags/boot2.flag 存在吗？                            → 开了开机自启没
//
// 用它做第一道判断: 未安装就直接显示提示，一个 IPC 都不发。
enum class FzPresence {
    NotInstalled,   // 卡上没有 exefs.nsp —— 根本没装
    InstalledNoBoot,// 装了，但没放 boot2.flag（开机不会自动启动）
    InstalledBoot,  // 装了且开了开机自启
};

// 纯文件系统探测，绝不发 IPC
FzPresence fzDetectPresence();

// 便捷判断: 是否已安装（未安装时不必尝试连接）
inline bool fzInstalled() {
    return fzDetectPresence() != FzPresence::NotInstalled;
}

Result fzGetIsActive(bool *out_active);
Result fzSetIsActive(bool active);

Result fzGetProfile(std::uint32_t id, FzProfile *out_profile);
Result fzSetProfile(std::uint32_t id, const FzProfile &profile);

Result fzGetActiveProfileId(bool is_external, std::uint32_t *out_id);

// 便捷：把一份设置同时写入 day 与 night
//   Fizeau 会按黄昏/黎明时间在两组之间自动切换。写成相同数值可以避免
//   画面在黄昏时刻突然变化 —— 那既意外又难排查。
//
// ⚠ 只改「色彩设置 / components / filter」这三类字段，
//   **保留** profile 里已有的黄昏黎明时刻与调光超时。
//   本函数曾经无条件把 dusk/dawn 覆盖成 21:00/07:00 —— 那会把用户在
//   官方 overlay 里改过的调度时刻静默重置（真机表现为"黄昏切换时机变了"）。
//   传进来的 prof 必须是 fzGetProfile() 读回的**真实 profile**，不是 {}。
void fzFillProfile(FzProfile *prof, const FzSettings &s,
                   std::uint32_t components, std::uint32_t filter);

// ---------------------------------------------------------------- 配置落盘
//
// ═══════════════════════════════════════════════════════════════════════════
// ⚠ 这是本插件最容易漏掉的一环：Fizeau 的 sysmodule **只读配置，从不写配置**
// ═══════════════════════════════════════════════════════════════════════════
// 源码依据（Fizeau 上游）:
//
//   sysmodule/src/main.cpp 启动时:
//       if (parse_config())
//           profile.apply();          // ← 开机只从 SD 读一次，然后应用
//   sysmodule/src/ipc_server.c:
//       整个文件没有任何 fopen / 写盘操作
//   common/src/config.cpp 的 Config::write() 只有 overlay 调用:
//       FizeauOverlayGui::~FizeauOverlayGui() {
//           tsl::hlp::doWithSDCardHandle([this] { this->config.write(); });
//           fizeauExit();
//       }
//
// 也就是说: **磁盘上的 config.ini 才是重启后的唯一事实来源**，
// IPC 改的只是 sysmodule 的运行态。
//
// 本插件不走官方 overlay，因此必须自己承担这次写盘 ——
// 否则用户在插件里选的滤镜**重启后必然丢失**，画面回落到 config.ini 里的旧值
// （真机现象: 重启后屏幕偏黄，要去滤镜菜单里重新调一次）。
//
// 写出格式与 Fizeau 的 Config::make() 完全一致（含 4 个 profile、
// handheld/docked 映射、active 开关），值取自 IPC 读回的真实状态，
// 所以不会覆盖用户在官方 overlay 里做过的其它设置。
//
// 调用时机: 用户**确认**了改动之后（按 A 确认滤镜 / 开关滤镜），
// 以及离开插件时仍有未落盘的改动。**不要**在光标预览的每一步都写 ——
// 那会让 SD 卡在按住方向键时被反复写入。
//
// 路径: 优先沿用卡上已有的配置文件位置（/config/Fizeau/config.ini 或
// /switch/Fizeau/config.ini）；都不存在时按 Fizeau 的默认约定新建前者。
//
// 返回: true 表示确实写入成功。失败不影响运行态（画面照常变），
// 只影响重启后是否保留 —— 界面上会如实提示。
bool fzSaveConfigToSd();

} // namespace fnx
