/*
 * FilterNX — 大气层中文滤镜插件
 *
 * layout.hpp — 界面布局的实测常量与高度预算
 *
 * ═══════════════════════════════════════════════════════════════════════════
 * 这些数字不是估算，是从 libultrahand（tesla.hpp）源码里读出来的
 * ═══════════════════════════════════════════════════════════════════════════
 * 单独放一个头文件的原因: gui.hpp 依赖 <tesla.hpp>（Switch 专属），
 * 主机侧测试无法编译它。把常量抽出来，真机和测试就能共用同一份定义，
 * 而不是让测试抄一份数字（那样测试就失去意义了）。
 *
 * ── 可见高度 ──
 * List::draw() 的裁剪矩形:
 *     enableScissoring(0, 88, FramebufferWidth,
 *                      FramebufferHeight - 73 - 97 + 2 + 5);
 * 源码注释也印证: "The List's logical bounds (topBound ≈ 97, bottomBound ≈ 647)"
 *
 * 在 1280x720 下:  720 - 73 - 97 + 2 + 5 = 557
 *
 * ⚠ List 的裁剪是硬性的: 超出可见高度的部分不会显示，必须滚动才能看到；
 *   而**恰好跨在底边上的那一行会被从中间切开** —— 屏幕底部出现半行残影。
 *   真机实测过两次（预设页的说明文字、主页面的「生效方式」）。
 *   所以每页都必须算清楚: 哪些行必须在首屏（不可滚动才能看到），
 *   哪些行可以放到滚动区。
 *
 * ── 单项高度 ──
 *   style::ListItemDefaultHeight     = 70
 *   CategoryHeader                   = 33（draw() 里 getBottomBound() - 33）
 *   首项前的额外偏移                 ≈ 33（List::addItem 的 first-item 优化）
 *
 * ── 各页实测账（行数由 gui.cpp 的 addItem 调用点数出来的，不是估的）──
 *   未连接引导页:   33 + 3*33 + 6*70 = 552 ≤ 557   → 整页放得下
 *   主页面(已连接): 33 + 3*33 + 6*70 = 552 ≤ 557   → 整页放得下
 *   信息页:         33 + 3*33 + 7*70 = 622 > 557   → 需要滚动
 *
 * ⚠ 常量必须与 gui.cpp 的实际 addItem 数保持同步。
 *   曾经 MAIN_ITEMS 停在 5（实际一度是 8）、INFO_ITEMS 停在 8（实际 7）:
 *   于是 test_layout 的高度断言算的是**并不存在的页面** —— 断言"通过"，
 *   真实主页面却溢出 135px，「适用游戏」「关于本插件」两行落到裁剪区外。
 *   主页面已按本条把行数压回 6 项（删掉两行重复说明），现在整页放得下。
 *   改界面行数时请一起改这里，并重跑 tests/test_layout.exe 与
 *   tools/check_preview_clip.py（两者都会读这些常量）。
 *
 * tests/test_layout.cpp 用这些常量校验每页的行数预算。
 *
 * GPLv2，详见 LICENSE。
 */

#pragma once

namespace fnx::ui {

// 可见区域高度（1280x720）
inline constexpr int VISIBLE_HEIGHT = 557;

// 单个列表项高度
inline constexpr int ITEM_HEIGHT = 70;

// 单个分类小标题高度
inline constexpr int HEADER_HEIGHT = 33;

// 首个列表项之前的偏移
inline constexpr int FIRST_ITEM_OFFSET = 33;

// 一页内容的总高度
inline constexpr int height_budget(int headers, int items) {
    return FIRST_ITEM_OFFSET + headers * HEADER_HEIGHT + items * ITEM_HEIGHT;
}

// 在给定行数下能放下的最大列表项数（供设计时参考）
inline constexpr int max_items_for(int headers) {
    return (VISIBLE_HEIGHT - FIRST_ITEM_OFFSET - headers * HEADER_HEIGHT) / ITEM_HEIGHT;
}

// ═══════════════════════════════════════════════════════════════════════════
// 各页面的实际行数
// ═══════════════════════════════════════════════════════════════════════════
// ⚠ 这两个数字必须与 gui.cpp 里 createUI() 的实际调用数一致。
//   放在这里而不是 Gui 类里，是因为 Gui 类声明依赖 <tesla.hpp>，
//   主机侧测试编不了 —— 而测试需要读这两个数字来算高度预算。
//
//   改界面行数时，必须同步改这里，否则测试会漏掉溢出。
//   gui.cpp 对应位置也留了同样的算式注释，两处要一起看。

// 主页面: 3 个小标题 + 6 个列表项
//   = 3 个「当前画面」状态行（滤镜/效果/作用于）
//   + 2 个操作项（选择滤镜 / 开启·关闭滤镜）
//   + 1 个说明项（关于本插件）
//   33 + 3*33 + 6*70 = 552 ≤ 557 → 整页放得下，「关于」入口不会被裁。
//   ⚠ 3 个小标题下**最多 6 项**（再加一项就是 622 > 557，底行被切）。
//   已删除的两行（曾把页面顶到 8 项 = 692px）:
//     「生效方式 / 立即生效」 —— 与 OverlayFrame 副标题「· 按下即生效」重复
//     「适用游戏 / 全部通用」 —— 作者原注释已写明该由「关于」取代
//   理由与算式见 gui.cpp「说明与关于」处的注释。
inline constexpr int MAIN_HEADERS = 3;
inline constexpr int MAIN_ITEMS   = 6;

// 预设页: 7 个分类小标题 + 30 个预设
// 预设页现在是**下拉式**: 默认只显示分组行，展开后才有子项。
//   收起态 = 分组数（一屏放得下）
//   展开态 = 分组数 + 该组项数（可滚动，由 List 处理）
inline constexpr int PRESET_HEADERS = 0;
inline constexpr int PRESET_ITEMS   = 11;   // 收起态 = 分组数

// 信息页: 3 个小标题 + 7 个列表项
//   作者 1 + 群号 3 + 说明 3 = 7
//   33 + 3*33 + 7*70 = 622 > 557 → 需要滚动（正常）。
// ⚠ 滚动到底部时最后一项会被裁剪矩形切掉部分 —— 所以信息页的
//   最后一项必须是"结尾"性质的说明（版本号），不能是关键操作。
inline constexpr int INFO_HEADERS = 3;
inline constexpr int INFO_ITEMS   = 7;

} // namespace fnx::ui
