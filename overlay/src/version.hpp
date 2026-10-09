/*
 * 超能滤镜 (Chaoneng / FilterNX) — 大气层中文滤镜插件
 *
 * version.hpp — 版本号的唯一来源
 *
 * 为什么单独放一个头文件:
 *   版本号出现在多处，必须一致，否则会出现"界面显示一个版本、
 *   zip 又叫另一个版本"这种自相矛盾:
 *     1. 插件界面的标题栏（用户最直接看到的地方）
 *     2. NRO 里 NACP 的 display_version 字段（菜单列表里显示的版本）
 *     3. 分发 zip 的文件名
 *
 *   package.sh 用 sed 从本文件读出版本号，不靠手抄。
 *
 * ⚠ 改版本号只需要改 FNX_VERSION 这一处。
 *
 * ── 为什么用宏而不是 constexpr ──
 *   界面里要把版本号与普通字符串拼接:
 *       OverlayFrame("超能滤镜", FNX_VERSION_LABEL " · 按下即生效")
 *   相邻字符串字面量的拼接是**编译期**行为，只对宏展开生效 ——
 *   如果它是 const char* 变量，上面这行会报
 *   "expected ')' before string constant"。
 *
 * ═══════════════════════════════════════════════════════════════════════
 * ⚠ 菜单里显示的名字与版本都来自 NACP（不是文件名）
 * ═══════════════════════════════════════════════════════════════════════
 * 源码依据: Ultrahand-Overlay source/utils.hpp:953 getOverlayInfo()
 *
 *     fread(&nacp, sizeof(NacpStruct), 1, file);
 *     memchr(nacp.lang_data.lang[0].name, '\0', ...)   → 显示名
 *     memchr(nacp.display_version, '\0', ...)          → 显示版本
 *
 * WerWolv 原版 Tesla-Menu 同理。文件名只用于排序与启动路径。
 *
 * ⚠ 还有一层覆盖: overlays.ini 的 custom_name / custom_version
 *   （Ultrahand source/main.cpp:6894）非空时会压过 NACP。
 *   曾经因为注册表里留着旧的 custom_version=6.0.0，
 *   出现"菜单显示 6.0.0 但插件内显示 1.0.0"的矛盾。
 *   现在部署脚本把这两个键写成**空值**，让 NACP 成为唯一来源。
 *
 * ⚠ NACP 字段偏移易错，定义统一放在 tools/nacp_layout.py:
 *     NacpLanguageEntry 步长 = 0x300（name 0x200 + author 0x100），不是 0x200
 *     isbn            @ 0x3000   ← 曾把版本号误写到 isbn，菜单读不到
 *     display_version @ 0x3060   ← 真正的版本字段
 *
 * GPLv2，详见 LICENSE。
 */

#pragma once

// 版本号 —— 唯一来源。改这里即可。
//
// 1.0.x = 首个正式（release）系列。此前的 0.x / 6.x 是迭代中的编号，
// 从 1.0.0 起按语义化版本: 主.次.修
#define FNX_VERSION "5.0.0"

// 界面副标题里显示的版本标签
#define FNX_VERSION_LABEL "v" FNX_VERSION

namespace fnx {

inline constexpr const char *VERSION = FNX_VERSION;

} // namespace fnx
