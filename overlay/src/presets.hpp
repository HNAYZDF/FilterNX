/*
 * FilterNX — 大气层中文滤镜插件
 *
 * presets.hpp — 中文滤镜预设表
 *
 * ═══════════════════════════════════════════════════════════════════════════
 * 文案长度约束（源码实测，不是估算）
 * ═══════════════════════════════════════════════════════════════════════════
 * libultrahand 的 ListItem 把"名字"和"数值"并排画在同一行：
 *
 *     [ 名字 ..................... 数值 ]
 *     名字: 字号 23      数值: 字号 20   (tesla.hpp:7435 / 7849)
 *
 *     m_maxWidth  = getWidth() - valueWidth - 66     (calculateWidths)
 *     m_truncated = textWidth > m_maxWidth + 20
 *
 * 一旦超限，名字会走"滚动动画"路径 —— 静止时看起来就是被截断的
 * （真机实测:「单色暖黄」显示成「单色」）。
 *
 * 字体是 stb_truetype 渲染的系统共享字体，全角字符宽度 ≈ 字号，
 * 因此可用像素反推字数上限。约 400px 可用宽度下：
 *
 *     4 字名字(92px) + 5 字数值(100px) = 192px，余量充足
 *
 * 所以硬约束:  name ≤ 4 字,  desc ≤ 5 字
 * tests/test_layout.cpp 有断言强制。
 *
 * ═══════════════════════════════════════════════════════════════════════════
 * 关于"预设质量"
 * ═══════════════════════════════════════════════════════════════════════════
 * 每个预设都经过这几条检验（由 tests/test_presets.cpp 断言）:
 *
 *   1. 至少有一个参数与中性值不同 —— 否则按下去毫无变化
 *   2. 任意两个预设的**完整参数集**都不相同 —— 否则用户看不出区别
 *   3. 参数选择有明确意图，而不是随手填:
 *        · 低色温偏黄是**降低蓝光**的物理原理（蓝光波长短、能量高）
 *        · 伽马 <2.4 提亮暗部、>2.4 压暗
 *        · 对比度用三次曲线居中调整，>1 拉开明暗层次
 *        · 调光类压 range 而不是降 luminance —— 保留暗部层次，不易死黑
 *        · 单色类的 filter 把**亮度**写进所选通道（权重 0.2126/0.7152/0.0722），
 *          所以是"灰阶染色"且亮度正确保留，不会整体变暗
 *   4. 数值全部落在 Fizeau 合法范围内 —— 越界会被静默钳制，
 *      表现为"写入成功但效果不对"，是最难查的一类故障
 *
 * 参数含义（Fizeau types.h 的合法区间）:
 *     temperature  1000..10000 K   色温，6500K = D65 中性
 *     saturation   0..2            饱和度，0 = 全灰，1 = 原样
 *     hue          -1..1           色相旋转
 *     contrast     0..2            对比度，1 = 原样
 *     gamma        0..5            伽马，2.4 = 原样（sRGB）
 *     luminance    -1..1           整体亮度偏移，0 = 原样
 *     range        0..1 x 0..1     输出范围压缩，0..1 = 原样
 *     components / filter          通道选择
 *
 * ⚠ 关于「色觉辅助」一组: 这里做的是**色相旋转 + 提高饱和度/对比度**，
 *   用来把容易混淆的颜色拉开差距。它不是医学意义的色盲矫正，
 *   效果因人而异 —— 文案上不能宣称"治疗"或"矫正"。
 *
 * GPLv2，详见 LICENSE。
 */

#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <string>

#include "fizeau_ipc.hpp"

namespace fnx {

// 界面布局约束（见文件头说明）
inline constexpr std::size_t NAME_MAX_CHARS = 4;
inline constexpr std::size_t DESC_MAX_CHARS = 5;

// 中性值 —— 所有参数等于这些值时画面与原样一致
inline constexpr std::uint32_t NEUTRAL_TEMP     = TEMP_D65;   // 6500
inline constexpr float         NEUTRAL_SAT      = 1.0f;
inline constexpr float         NEUTRAL_HUE      = 0.0f;
inline constexpr float         NEUTRAL_CONTRAST = 1.0f;
inline constexpr float         NEUTRAL_GAMMA    = 2.4f;
inline constexpr float         NEUTRAL_LUMA     = 0.0f;
inline constexpr float         NEUTRAL_RANGE_LO = 0.0f;
inline constexpr float         NEUTRAL_RANGE_HI = 1.0f;

// 预设分类
enum class PresetGroup {
    Basic,      // 基础
    Eyecare,    // 护眼
    Style,      // 风格
    Cinema,     // 电影
    Mood,       // 氛围
    Game,       // 游戏
    Retro,      // 怀旧
    Night,      // 夜间
    Dim,        // 调光
    Mono,       // 单色
    Vision,     // 色觉辅助
};

// ⚠ 分类数量（供 layout.hpp 的预算计算与测试核对）
inline constexpr std::size_t PRESET_GROUP_COUNT = 11;

inline const char *group_name(PresetGroup g) {
    switch (g) {
        case PresetGroup::Basic:   return "基础";
        case PresetGroup::Eyecare: return "护眼";
        case PresetGroup::Style:   return "风格";
        case PresetGroup::Cinema:  return "电影";
        case PresetGroup::Mood:    return "氛围";
        case PresetGroup::Game:    return "游戏";
        case PresetGroup::Retro:   return "怀旧";
        case PresetGroup::Night:   return "夜间";
        case PresetGroup::Dim:     return "调光";
        case PresetGroup::Mono:    return "单色";
        case PresetGroup::Vision:  return "色觉辅助";
    }
    return "";
}

struct Preset {
    const char  *id;
    const char  *name;      // 中文名，≤4 字
    const char  *desc;      // 一句话说明，≤5 字
    PresetGroup  group;
    FzSettings   settings;
    std::uint32_t components;
    std::uint32_t filter;

    bool is_dim() const { return group == PresetGroup::Dim; }
};

// ═══════════════════════════════════════════════════════════════════════════
// 预设总数 100 个，分 11 类
// ═══════════════════════════════════════════════════════════════════════════
// 名字一律 ≤4 字、说明 ≤5 字；名字之间不存在前缀包含关系
// （都由 tools/check_preset_table.py 与 check_name_prefix.py 强制）。
//
// 参数取值思路:
//   · 色温 <6500K 偏暖、>6500K 偏冷
//   · 伽马 <2.4 提亮暗部、>2.4 压暗
//   · 对比度 >1 拉开层次、<1 柔和
//   · range.hi <1 压暗（保留暗部层次，优于降 luminance）
//   · filter != COMP_NONE 时是"灰阶染色"（亮度写进所选通道）
// ═══════════════════════════════════════════════════════════════════════════
inline constexpr std::array<Preset, 100> PRESETS = {{
    // ═══════════════ 基础 ═══════════════
    // 真正的恒等设置，参数与 Fizeau 的 DEFAULT_* 完全一致，
    // 这样"反查当前预设"在默认状态下也能正确识别成「原色」。
    { "original", "原色", "不处理", PresetGroup::Basic,
      { NEUTRAL_TEMP, NEUTRAL_SAT, NEUTRAL_HUE, NEUTRAL_CONTRAST,
        NEUTRAL_GAMMA, NEUTRAL_LUMA, { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_NONE },

    // ═══════════════ 护眼 ═══════════════
    // 色温越低蓝光成分越少（蓝光波长短、能量高，夜间抑制褪黑素分泌）。
    // 四档逐级加深，相邻色温差 ≥700K，保证肉眼可辨。
    { "eyecare_tiny", "极轻护眼", "6200K", PresetGroup::Eyecare,
      { 6200, 0.97f, 0.0f, 1.02f, 2.35f, 0.0f,
        { 0.0f, 1.0f } },
      COMP_ALL, COMP_NONE },

    { "eyecare_office", "办公护眼", "日光暖", PresetGroup::Eyecare,
      { 5600, 0.93f, 0.0f, 1.05f, 2.28f, 0.01f,
        { 0.0f, 1.0f } },
      COMP_ALL, COMP_NONE },

    { "eyecare_low", "轻度护眼", "5000K", PresetGroup::Eyecare,
      { 5000, 0.95f, NEUTRAL_HUE, 1.02f, 2.30f, NEUTRAL_LUMA,
        { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_NONE },

    { "eyecare_mid", "中度护眼", "4200K", PresetGroup::Eyecare,
      { 4200, 0.88f, NEUTRAL_HUE, 1.02f, 2.20f, NEUTRAL_LUMA,
        { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_NONE },

    { "eyecare_deep", "深度护眼", "3400K", PresetGroup::Eyecare,
      { 3400, 0.80f, NEUTRAL_HUE, 1.00f, 2.15f, NEUTRAL_LUMA,
        { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_NONE },

    { "paper", "纸质", "2800K", PresetGroup::Eyecare,
      { 2800, 0.70f, 0.01f, 0.95f, 2.10f, 0.02f,
        { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_NONE },

    // ═══════════════ 风格 ═══════════════
    { "vivid", "鲜艳", "浓艳", PresetGroup::Style,
      { NEUTRAL_TEMP, 1.50f, NEUTRAL_HUE, 1.15f, 2.35f, NEUTRAL_LUMA,
        { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_NONE },

    // 动画风: 高饱和 + 轻提暗部，适合卡通渲染
    { "anime", "动画", "高饱和", PresetGroup::Style,
      { 6800, 1.55f, NEUTRAL_HUE, 1.12f, 2.25f, 0.03f,
        { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_NONE },

    { "cool", "冷色", "偏蓝", PresetGroup::Style,
      { 8200, 1.05f, -0.04f, 1.15f, 2.35f, NEUTRAL_LUMA,
        { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_NONE },

    // 名字用「暖色」而不是「暖调」: 后者是「暖调电影」的前缀，
    // 用户在列表里快速扫过时容易看错（由 tools/check_name_prefix.py 检出）。
    { "warm", "暖橙", "偏橙", PresetGroup::Style,
      { 5400, 1.05f, 0.03f, 1.10f, 2.40f, NEUTRAL_LUMA,
        { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_NONE },

    { "hipop", "高反差", "强对比", PresetGroup::Style,
      { NEUTRAL_TEMP, 1.12f, NEUTRAL_HUE, 1.45f, 2.10f, NEUTRAL_LUMA,
        { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_NONE },

    { "lowcon", "柔和", "降反差", PresetGroup::Style,
      { 6200, 0.92f, NEUTRAL_HUE, 0.85f, 2.50f, NEUTRAL_LUMA,
        { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_NONE },

    { "neon", "霓虹", "高亮饱和", PresetGroup::Style,
      { 7200, 1.75f, -0.02f, 1.35f, 2.15f, 0.04f,
        { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_NONE },

    { "candy", "糖果", "甜亮", PresetGroup::Style,
      { 7000, 1.60f, 0.02f, 1.05f, 2.05f, 0.06f,
        { 0.02f, 0.98f } },
      COMP_ALL, COMP_NONE },

    { "aqua", "水色", "清透", PresetGroup::Style,
      { 8600, 1.20f, -0.05f, 1.10f, 2.20f, 0.04f,
        { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_NONE },

    { "royal", "宝蓝", "沉冷", PresetGroup::Style,
      { 9200, 1.15f, -0.03f, 1.25f, 2.45f, -0.02f,
        { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_NONE },

    { "ember", "余烬", "暗红", PresetGroup::Style,
      { 4200, 1.25f, 0.05f, 1.30f, 2.55f, -0.03f,
        { 0.04f, 0.96f } },
      COMP_ALL, COMP_NONE },

    { "stone", "石色", "低饱和", PresetGroup::Style,
      { 6300, 0.78f, 0.01f, 1.08f, 2.38f, NEUTRAL_LUMA,
        { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_NONE },

    { "mist", "薄雾", "柔亮", PresetGroup::Style,
      { 6600, 0.85f, NEUTRAL_HUE, 0.92f, 2.10f, 0.06f,
        { 0.08f, 0.92f } },
      COMP_ALL, COMP_NONE },

    { "steel", "钢铁", "冷灰", PresetGroup::Style,
      { 7400, 0.82f, -0.02f, 1.20f, 2.50f, NEUTRAL_LUMA,
        { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_NONE },

    { "rgb", "红蓝", "双色", PresetGroup::Style,
      { 6200, 1.85f, 0.32f, 1.28f, 2.30f, NEUTRAL_LUMA,
        { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_NONE },

    { "turbo", "高锐", "强反差", PresetGroup::Style,
      { 6800, 1.40f, NEUTRAL_HUE, 1.60f, 2.05f, 0.02f,
        { 0.02f, 0.98f } },
      COMP_ALL, COMP_NONE },

    { "ultravivid", "极致艳", "极高饱和", PresetGroup::Style,
      { 6700, 1.9f, 0.0f, 1.22f, 2.3f, 0.02f,
        { 0.0f, 1.0f } },
      COMP_ALL, COMP_NONE },

    { "greysoft", "素雅", "极低饱和", PresetGroup::Style,
      { 6400, 0.45f, 0.0f, 1.0f, 2.35f, 0.01f,
        { 0.0f, 1.0f } },
      COMP_ALL, COMP_NONE },

    { "copper", "铜锈", "旧金属", PresetGroup::Style,
      { 4300, 0.95f, 0.06f, 1.18f, 2.45f, 0.0f,
        { 0.04f, 0.96f } },
      COMP_ALL, COMP_NONE },

    { "plasma", "等离子", "紫青高亮", PresetGroup::Style,
      { 7900, 1.68f, 0.28f, 1.3f, 2.18f, 0.03f,
        { 0.0f, 1.0f } },
      COMP_ALL, COMP_NONE },

    // ═══════════════ 电影 ═══════════════
    { "cinecool", "冷调电影", "青蓝", PresetGroup::Cinema,
      { 8200, 1.05f, -0.05f, 1.25f, 2.45f, NEUTRAL_LUMA,
        { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_NONE },

    { "cinewarm", "暖调电影", "橙调", PresetGroup::Cinema,
      { 5400, 1.08f, 0.04f, 1.20f, 2.50f, NEUTRAL_LUMA,
        { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_NONE },

    { "teal", "青橙调", "红青分离", PresetGroup::Cinema,
      { 7000, 1.20f, -0.06f, 1.30f, 2.40f, NEUTRAL_LUMA,
        { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_NONE },

    { "noir", "黑色电影", "低饱和", PresetGroup::Cinema,
      { 6000, 0.40f, NEUTRAL_HUE, 1.35f, 2.60f, NEUTRAL_LUMA,
        { 0.04f, 0.96f } },
      COMP_ALL, COMP_NONE },

    // 导演风格: 偏青绿的冷调 + 高对比，接近记忆中的胶片观感
    { "nolan", "诺兰冷", "青灰高反", PresetGroup::Cinema,
      { 7600, 0.88f, -0.04f, 1.38f, 2.40f, NEUTRAL_LUMA,
        { 0.03f, 0.97f } },
      COMP_ALL, COMP_NONE },

    { "wong", "王家卫", "浓艳暖", PresetGroup::Cinema,
      { 5000, 1.45f, 0.06f, 1.15f, 2.30f, NEUTRAL_LUMA,
        { 0.04f, 0.96f } },
      COMP_ALL, COMP_NONE },

    // 「黄昏」是余晖的观感: 暖色 + 压暗 + 保留层次
    { "dusk", "黄昏", "暖暗", PresetGroup::Cinema,
      { 4800, 1.15f, 0.04f, 1.18f, 2.35f, NEUTRAL_LUMA,
        { NEUTRAL_RANGE_LO, 0.82f } },
      COMP_ALL, COMP_NONE },

    { "gothic", "暗黑", "冷暗高反", PresetGroup::Cinema,
      { 7000, 0.72f, -0.03f, 1.55f, 2.65f, -0.02f,
        { 0.02f, 0.94f } },
      COMP_ALL, COMP_NONE },

    { "desert", "沙漠", "暖沙", PresetGroup::Cinema,
      { 4600, 1.18f, 0.03f, 1.10f, 2.25f, 0.03f,
        { 0.05f, 0.95f } },
      COMP_ALL, COMP_NONE },

    { "memoir", "回忆", "泛黄柔", PresetGroup::Cinema,
      { 5200, 0.68f, 0.03f, 0.90f, 2.05f, 0.04f,
        { 0.10f, 0.90f } },
      COMP_ALL, COMP_NONE },

    { "silver", "银幕", "冷调低反", PresetGroup::Cinema,
      { 7100, 0.65f, -0.02f, 0.88f, 2.55f, 0.02f,
        { 0.06f, 0.94f } },
      COMP_ALL, COMP_NONE },

    { "fincher", "芬奇绿", "冷绿高反", PresetGroup::Cinema,
      { 7300, 0.8f, -0.07f, 1.42f, 2.38f, 0.0f,
        { 0.03f, 0.97f } },
      COMP_ALL, COMP_NONE },

    { "wes", "韦斯暖", "粉黄对称", PresetGroup::Cinema,
      { 5900, 1.35f, 0.07f, 1.08f, 2.22f, 0.03f,
        { 0.03f, 0.97f } },
      COMP_ALL, COMP_NONE },

    { "abyss", "深渊", "极冷极暗", PresetGroup::Cinema,
      { 9400, 0.78f, -0.05f, 1.3f, 2.7f, -0.05f,
        { 0.02f, 0.9f } },
      COMP_ALL, COMP_NONE },

    // ═══════════════ 氛围 ═══════════════
    { "aurora", "极光", "青紫高饱和", PresetGroup::Mood,
      { 8000, 1.65f, -0.10f, 1.22f, 2.25f, 0.02f,
        { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_NONE },

    { "cyber", "赛博", "洋红青", PresetGroup::Mood,
      { 7500, 1.70f, 0.40f, 1.35f, 2.20f, NEUTRAL_LUMA,
        { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_NONE },

    { "sakura", "樱花", "粉柔", PresetGroup::Mood,
      { 6100, 1.30f, 0.12f, 1.02f, 2.15f, 0.05f,
        { 0.04f, 0.96f } },
      COMP_ALL, COMP_NONE },

    { "amber", "琥珀", "暖金", PresetGroup::Mood,
      { 4700, 1.22f, 0.03f, 1.12f, 2.20f, 0.02f,
        { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_NONE },

    { "velvet", "丝绒", "深暖", PresetGroup::Mood,
      { 5600, 1.28f, 0.03f, 1.25f, 2.50f, NEUTRAL_LUMA,
        { 0.03f, 0.97f } },
      COMP_ALL, COMP_NONE },

    { "deepsea", "深海", "深青", PresetGroup::Mood,
      { 9000, 1.10f, -0.04f, 1.28f, 2.60f, -0.04f,
        { 0.03f, 0.95f } },
      COMP_ALL, COMP_NONE },

    { "emberglow", "熔岩", "炽红", PresetGroup::Mood,
      { 3800, 1.55f, 0.06f, 1.35f, 2.35f, NEUTRAL_LUMA,
        { 0.02f, 0.98f } },
      COMP_ALL, COMP_NONE },

    { "poison", "毒液", "亮绿", PresetGroup::Mood,
      { 6600, 1.62f, -0.22f, 1.28f, 2.15f, NEUTRAL_LUMA,
        { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_NONE },

    { "lavender", "薰衣草", "淡紫", PresetGroup::Mood,
      { 6800, 1.12f, 0.10f, 1.00f, 2.20f, 0.03f,
        { 0.05f, 0.95f } },
      COMP_ALL, COMP_NONE },

    { "mint", "薄荷", "清凉", PresetGroup::Mood,
      { 7800, 1.12f, -0.07f, 1.00f, 2.18f, 0.05f,
        { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_NONE },

    { "solar", "日冕", "炽亮暖", PresetGroup::Mood,
      { 5200, 1.45f, 0.02f, 1.20f, 2.05f, 0.07f,
        { 0.03f, 0.97f } },
      COMP_ALL, COMP_NONE },

    { "sunset", "日落", "暖橙渐变", PresetGroup::Mood,
      { 4900, 1.35f, 0.07f, 1.15f, 2.28f, 0.02f,
        { 0.03f, 0.97f } },
      COMP_ALL, COMP_NONE },

    { "storm", "风暴", "冷暗灰", PresetGroup::Mood,
      { 8000, 0.72f, -0.03f, 1.32f, 2.55f, -0.03f,
        { 0.03f, 0.94f } },
      COMP_ALL, COMP_NONE },

    { "jade", "翡翠", "青绿", PresetGroup::Mood,
      { 7100, 1.38f, -0.14f, 1.12f, 2.25f, 0.2f,
        { 0.0f, 1.0f } },
      COMP_ALL, COMP_NONE },

    { "rose", "玫瑰金", "粉暖", PresetGroup::Mood,
      { 5800, 1.42f, 0.1f, 1.1f, 2.2f, 0.04f,
        { 0.02f, 0.98f } },
      COMP_ALL, COMP_NONE },

    // ═══════════════ 游戏 ═══════════════
    // 「提暗部」类: 伽马明显低于 2.4 + 轻抬 range.lo，
    // 让阴影里的敌人/道具更容易看清，同时不过曝高光。
    { "game_fps", "射击增强", "提暗部", PresetGroup::Game,
      { 6600, 1.22f, NEUTRAL_HUE, 1.25f, 2.00f, NEUTRAL_LUMA,
        { 0.03f, 0.98f } },
      COMP_ALL, COMP_NONE },

    { "game_open", "开放世界", "护眼清晰", PresetGroup::Game,
      { 6200, 1.15f, NEUTRAL_HUE, 1.12f, 2.25f, 0.02f,
        { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_NONE },

    { "game_dark", "恐怖暗场", "提亮暗部", PresetGroup::Game,
      { 6400, 1.10f, NEUTRAL_HUE, 1.05f, 1.85f, 0.05f,
        { 0.10f, 0.92f } },
      COMP_ALL, COMP_NONE },

    { "game_comp", "竞技对比", "强辨识", PresetGroup::Game,
      { 7000, 1.35f, NEUTRAL_HUE, 1.48f, 2.10f, NEUTRAL_LUMA,
        { 0.02f, 0.98f } },
      COMP_ALL, COMP_NONE },

    { "game_pixel", "像素复古", "硬边高饱", PresetGroup::Game,
      { 6800, 1.65f, -0.03f, 1.40f, 2.05f, NEUTRAL_LUMA,
        { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_NONE },

    { "game_moba", "技能显眼", "高饱和", PresetGroup::Game,
      { 6900, 1.72f, 0.05f, 1.22f, 2.20f, 0.03f,
        { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_NONE },

    { "game_race", "竞速清晰", "动感对比", PresetGroup::Game,
      { 6900, 1.3f, 0.0f, 1.38f, 2.15f, 0.01f,
        { 0.0f, 1.0f } },
      COMP_ALL, COMP_NONE },

    { "game_rpg", "剧情观影", "暖调沉浸", PresetGroup::Game,
      { 6100, 1.2f, 0.03f, 1.15f, 2.3f, 0.02f,
        { 0.0f, 1.0f } },
      COMP_ALL, COMP_NONE },

    { "game_cart", "卡通明快", "高亮低反", PresetGroup::Game,
      { 6900, 1.55f, 0.0f, 0.95f, 2.05f, 0.05f,
        { 0.03f, 0.97f } },
      COMP_ALL, COMP_NONE },

    // ═══════════════ 怀旧 ═══════════════
    { "retro", "复古", "泛黄", PresetGroup::Retro,
      { 4600, 0.65f, 0.03f, 0.95f, 1.95f, NEUTRAL_LUMA,
        { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_NONE },

    { "vhs", "VHS", "录像带", PresetGroup::Retro,
      { 5200, 1.28f, 0.04f, 0.92f, 2.05f, 0.04f,
        { 0.08f, 0.92f } },
      COMP_ALL, COMP_NONE },

    { "sepia", "棕褐", "老照片", PresetGroup::Retro,
      { 4400, 0.52f, 0.02f, 1.05f, 2.10f, 0.03f,
        { 0.08f, 0.92f } },
      COMP_ALL, COMP_NONE },

    { "faded", "褪色", "旧照片", PresetGroup::Retro,
      { 5800, 0.55f, 0.02f, 0.80f, 2.15f, 0.05f,
        { 0.06f, 0.94f } },
      COMP_ALL, COMP_NONE },

    { "crt", "显像管", "荧光绿", PresetGroup::Retro,
      { 6300, 1.18f, -0.06f, 1.10f, 2.30f, 0.03f,
        { 0.05f, 0.95f } },
      COMP_ALL, COMP_NONE },

    { "polaroid", "拍立得", "暖柔", PresetGroup::Retro,
      { 5600, 1.05f, 0.03f, 0.95f, 2.08f, 0.05f,
        { 0.09f, 0.91f } },
      COMP_ALL, COMP_NONE },

    { "super8", "超8", "暖颗粒", PresetGroup::Retro,
      { 5000, 0.88f, 0.05f, 1.02f, 1.98f, 0.03f,
        { 0.1f, 0.9f } },
      COMP_ALL, COMP_NONE },

    { "kodachrome", "柯达", "浓艳旧片", PresetGroup::Retro,
      { 5500, 1.32f, 0.04f, 1.15f, 2.15f, 0.01f,
        { 0.05f, 0.95f } },
      COMP_ALL, COMP_NONE },

    // ═══════════════ 夜间 ═══════════════
    // 低色温 + 低亮度，为睡前使用准备。
    // ⚠ 与「护眼」的区别: 护眼只降色温，「夜间」同时压亮度。
    { "night_read", "夜间读", "低亮暖", PresetGroup::Night,
      { 3600, 0.78f, 0.02f, 0.95f, 2.15f, NEUTRAL_LUMA,
        { NEUTRAL_RANGE_LO, 0.55f } },
      COMP_ALL, COMP_NONE },

    { "night_deep", "深夜", "极低亮", PresetGroup::Night,
      { 3000, 0.65f, 0.02f, 0.92f, 2.10f, NEUTRAL_LUMA,
        { NEUTRAL_RANGE_LO, 0.30f } },
      COMP_ALL, COMP_NONE },

    { "night_soft", "床头暖", "柔和暖", PresetGroup::Night,
      { 4000, 0.82f, 0.02f, 0.98f, 2.20f, NEUTRAL_LUMA,
        { NEUTRAL_RANGE_LO, 0.62f } },
      COMP_ALL, COMP_NONE },

    { "night_green", "暗夜绿", "低亮绿", PresetGroup::Night,
      { 5200, 0.72f, -0.03f, 1.00f, 2.22f, NEUTRAL_LUMA,
        { NEUTRAL_RANGE_LO, 0.48f } },
      COMP_ALL, COMP_NONE },

    { "night_cinema", "夜间观影", "低亮电影", PresetGroup::Night,
      { 5600, 1.05f, 0.02f, 1.2f, 2.35f, 0.0f,
        { 0.0f, 0.42f } },
      COMP_ALL, COMP_NONE },

    { "night_amber", "夜灯琥珀", "极暖低亮", PresetGroup::Night,
      { 2700, 0.7f, 0.03f, 0.95f, 2.08f, 0.0f,
        { 0.0f, 0.38f } },
      COMP_ALL, COMP_NONE },

    // ═══════════════ 调光 ═══════════════
    // 通过压缩色彩范围压低画面亮度，而不是降低 luminance ——
    // 压 range 是把输出区间挤到低位，暗部层次保留得更好，不易死黑。
    // 两者也不叠加（由测试断言强制，避免亮度难以预期）。
    //
    // OLED 用户建议: 系统亮度调最亮（高亮度走 DC 调光，避开 PWM 频闪区），
    // 再用这里降低感知亮度。
    { "dim_soft", "微光调光", "85%", PresetGroup::Dim,
      { 6500, 1.0f, 0.0f, 1.0f, 2.4f, 0.0f,
        { 0.0f, 0.85f } },
      COMP_ALL, COMP_NONE },

    { "dim_light", "轻度调光", "65%", PresetGroup::Dim,
      { NEUTRAL_TEMP, NEUTRAL_SAT, NEUTRAL_HUE, NEUTRAL_CONTRAST,
        NEUTRAL_GAMMA, NEUTRAL_LUMA, { NEUTRAL_RANGE_LO, 0.65f } },
      COMP_ALL, COMP_NONE },

    { "dim_mid", "中度调光", "35%", PresetGroup::Dim,
      { NEUTRAL_TEMP, NEUTRAL_SAT, NEUTRAL_HUE, NEUTRAL_CONTRAST,
        NEUTRAL_GAMMA, NEUTRAL_LUMA, { NEUTRAL_RANGE_LO, 0.35f } },
      COMP_ALL, COMP_NONE },

    { "dim_cool", "调光冷色", "低亮冷", PresetGroup::Dim,
      { 7600, 1.05f, NEUTRAL_HUE, 1.10f, 2.30f, NEUTRAL_LUMA,
        { NEUTRAL_RANGE_LO, 0.30f } },
      COMP_ALL, COMP_NONE },

    { "dim_warm", "调光暖色", "低亮暖", PresetGroup::Dim,
      { 5000, 0.90f, NEUTRAL_HUE, 1.02f, 2.20f, NEUTRAL_LUMA,
        { NEUTRAL_RANGE_LO, 0.28f } },
      COMP_ALL, COMP_NONE },

    { "dim_deep", "深度调光", "18%", PresetGroup::Dim,
      { NEUTRAL_TEMP, NEUTRAL_SAT, NEUTRAL_HUE, NEUTRAL_CONTRAST,
        NEUTRAL_GAMMA, NEUTRAL_LUMA, { NEUTRAL_RANGE_LO, 0.18f } },
      COMP_ALL, COMP_NONE },

    { "dim_strong", "强力调光", "10%", PresetGroup::Dim,
      { 6500, 1.0f, 0.0f, 1.0f, 2.4f, 0.0f,
        { 0.0f, 0.1f } },
      COMP_ALL, COMP_NONE },

    // ═══════════════ 单色 ═══════════════
    // filter 的真实语义（Fizeau color.cpp 的 filter_matrix）:
    //   Component_Green 不是"只留绿色通道"，而是把**亮度**按
    //   0.2126/0.7152/0.0722 的权重写进所选通道，其余通道输出 0。
    //   所以画面是"灰阶染色"，且亮度被正确保留，不会整体变暗。
    { "mono", "黑白", "去色", PresetGroup::Mono,
      { NEUTRAL_TEMP, 0.00f, NEUTRAL_HUE, 1.05f, 2.40f, NEUTRAL_LUMA,
        { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_NONE },

    // 名字用「硬黑白」而不是「黑白硬调」: 后者以「黑白」开头，
    // 与同分类的「黑白」构成前缀关系（由 check_name_prefix.py 检出）。
    { "mono_contrast", "硬黑白", "强反差", PresetGroup::Mono,
      { NEUTRAL_TEMP, 0.00f, NEUTRAL_HUE, 1.55f, 2.20f, NEUTRAL_LUMA,
        { 0.03f, 0.97f } },
      COMP_ALL, COMP_NONE },

    { "mono_green", "单色绿", "绿屏", PresetGroup::Mono,
      { NEUTRAL_TEMP, NEUTRAL_SAT, NEUTRAL_HUE, 1.05f, 2.30f, NEUTRAL_LUMA,
        { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_GREEN },

    // 单色暖黄 = 绿通道承载亮度 + 4000K 低色温把绿色偏暖，
    // 得到接近琥珀终端的观感。
    { "mono_amber", "单色暖黄", "琥珀", PresetGroup::Mono,
      { 4000, NEUTRAL_SAT, NEUTRAL_HUE, 1.02f, 2.20f, NEUTRAL_LUMA,
        { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_GREEN },

    { "mono_blue", "单色蓝", "冷蓝", PresetGroup::Mono,
      { 8200, NEUTRAL_SAT, NEUTRAL_HUE, 1.12f, 2.35f, NEUTRAL_LUMA,
        { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_BLUE },

    { "mono_red", "单色红", "暗房", PresetGroup::Mono,
      { 6500, NEUTRAL_SAT, NEUTRAL_HUE, 1.25f, 2.50f, NEUTRAL_LUMA,
        { 0.03f, 0.97f } },
      COMP_ALL, COMP_RED },

    { "mono_cyan", "单色青", "冷青", PresetGroup::Mono,
      { 7400, 1.0f, 0.0f, 1.08f, 2.32f, 0.0f,
        { 0.0f, 1.0f } },
      COMP_ALL, COMP_BLUE },

    // ═══════════════ 色觉辅助 ═══════════════
    //
    // ⚠ 这不是医学意义的色盲矫正，而是**色相旋转 + 提高饱和度/对比度**，
    //   把容易混淆的颜色拉开差距。效果因人而异，文案不做医疗宣称。
    //
    // 红绿色弱（deuteranopia / protanopia）的核心困难是红与绿难以区分。
    // 把色相往黄-蓝轴旋转，可以让原本接近的红绿在色相上分开。
    { "vision_red", "红绿辅助", "色相偏移", PresetGroup::Vision,
      { 6000, 1.35f, 0.18f, 1.25f, 2.35f, NEUTRAL_LUMA,
        { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_NONE },

    { "vision_blue", "蓝黄辅助", "色相偏移", PresetGroup::Vision,
      { 6200, 1.30f, -0.20f, 1.22f, 2.35f, NEUTRAL_LUMA,
        { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_NONE },

    { "vision_high", "高辨识", "强化区分", PresetGroup::Vision,
      { 6500, 1.70f, 0.10f, 1.40f, 2.30f, NEUTRAL_LUMA,
        { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_NONE },

    { "vision_soft", "视觉舒缓", "降刺激", PresetGroup::Vision,
      { 5200, 0.75f, 0.05f, 0.92f, 2.30f, 0.02f,
        { 0.02f, 0.98f } },
      COMP_ALL, COMP_NONE },

    // 低色温 + 色相向暖侧旋转 + 提高饱和:
    // 红色系被推向橙黄、绿色系更饱和，红绿差异随之拉开。
    { "vision_warm", "暖色辅助", "低蓝光", PresetGroup::Vision,
      { 4500, 1.25f, 0.18f, 1.12f, 2.25f, NEUTRAL_LUMA,
        { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_NONE },

    { "vision_max", "极限辨识", "极高饱和", PresetGroup::Vision,
      { 6400, 1.95f, 0.14f, 1.50f, 2.25f, NEUTRAL_LUMA,
        { NEUTRAL_RANGE_LO, NEUTRAL_RANGE_HI } },
      COMP_ALL, COMP_NONE },
    { "vision_contrast", "对比辅助", "拉明暗差", PresetGroup::Vision,
      { 6400, 0.85f, 0.0f, 1.62f, 2.28f, 0.0f,
        { 0.02f, 0.98f } },
      COMP_ALL, COMP_NONE },

}};

inline const Preset *preset_by_index(std::size_t i) {
    return i < PRESETS.size() ? &PRESETS[i] : nullptr;
}

inline const Preset *find_preset(const std::string &id) {
    for (const auto &p : PRESETS) {
        if (id == p.id)
            return &p;
    }
    return nullptr;
}

// 按 UTF-8 编码统计字符数（不是字节数）。
// 界面的宽度约束是按"字符"计的，中文每字 3 字节，用 size() 会误判。
inline std::size_t utf8_length(const char *s) {
    if (!s)
        return 0;
    std::size_t n = 0;
    for (const unsigned char *p = reinterpret_cast<const unsigned char *>(s); *p; ++p) {
        // 只统计非连续字节（UTF-8 后续字节形如 10xxxxxx）
        if ((*p & 0xC0) != 0x80)
            ++n;
    }
    return n;
}

inline std::size_t utf8_length(const std::string &s) {
    return utf8_length(s.c_str());
}

// 设置是否与中性值完全一致（即画面未被处理）
inline bool is_neutral(const FzSettings &s, std::uint32_t filter) {
    return s.temperature == NEUTRAL_TEMP
        && s.saturation  == NEUTRAL_SAT
        && s.hue         == NEUTRAL_HUE
        && s.contrast    == NEUTRAL_CONTRAST
        && s.gamma       == NEUTRAL_GAMMA
        && s.luminance   == NEUTRAL_LUMA
        && s.range.lo    == NEUTRAL_RANGE_LO
        && s.range.hi    == NEUTRAL_RANGE_HI
        && filter        == COMP_NONE;
}

// 把设置浓缩成一行中文摘要，用于主界面显示当前状态
// （用户自己调过、不匹配任何预设时才会用到）。
//
// 长度约束: ≤10 字。
//   主界面这一行名字是「效果」(2 字)，而 ListItem 布局是
//       m_maxWidth = getWidth() - valueWidth - 66
//   value 越长名字可用宽度越小。真机实测: value 过长时「效果」被截断成「效」。
//
// 刻意实现为头文件内联函数: 主机侧测试要验证它的输出，若放到 .cpp 里
// 就得写第二份实现来链接，那样"测试的"和"真机跑的"就不是同一份代码了。
inline std::string settings_summary(const FzSettings &s, std::uint32_t filter) {
    char buf[128];

    if (filter == COMP_GREEN) {
        // 低色温会让绿通道偏暖，因此区分"绿"与"暖黄"两种观感
        if (s.temperature <= 4500) {
            std::snprintf(buf, sizeof(buf), "暖黄%uK", s.temperature);
        } else {
            std::snprintf(buf, sizeof(buf), "绿%uK", s.temperature);
        }
        return buf;
    }
    if (filter == COMP_RED)
        return "红色单色";
    if (filter == COMP_BLUE)
        return "蓝色单色";

    if (s.saturation <= 0.001f)
        return "黑白";

    if (s.range.hi < 0.999f) {
        std::snprintf(buf, sizeof(buf), "调光%d%%",
                      static_cast<int>(s.range.hi * 100.0f + 0.5f));
        return buf;
    }

    // 形如 "6500K·1.40"：色温 · 饱和度
    //
    // 只显示两个值。三个值（色温·饱和·伽马）是 15 字，超出这一行能承受的
    // 长度 —— 会把名字「效果」挤掉。
    // 5 位色温（10000K）时省略 K 单位: "10000K·2.00" 是 11 字会超限，
    // 省略后 "10000·2.00" 是 10 字。
    if (s.temperature >= 10000) {
        std::snprintf(buf, sizeof(buf), "%u·%.2f",
                      s.temperature, s.saturation);
    } else {
        std::snprintf(buf, sizeof(buf), "%uK·%.2f",
                      s.temperature, s.saturation);
    }
    return buf;
}

} // namespace fnx
