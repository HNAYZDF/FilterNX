/*
 * fizeau_proto.h — Fizeau IPC 协议定义（主机侧测试用）
 *
 * 本文件是 Fizeau 官方 common/include/fizeau.h + types.h 相关部分的
 * 忠实复刻，去掉 Switch 专属依赖，以便在 PC 上验证结构体布局。
 *
 * 为什么必须验证布局:
 *   Fizeau 的 IPC 用 serviceDispatchIn 直接发送整个 FizeauProfile 结构体。
 *   若我方结构体有任何字段偏移/大小差异，服务端会收到错位的数据 ——
 *   轻则设置无效，重则写入异常数值导致画面异常。
 *   早期版本的 IPC 就是没做这层验证才出的问题。
 *
 * 权威来源:
 *   https://github.com/averne/Fizeau  common/include/fizeau.h
 *                                     common/include/types.h
 */

#pragma once

#include <cstdint>

namespace fz {

// ── types.h ──
using Temperature = std::uint32_t;
inline constexpr Temperature MIN_TEMP = 1000;
inline constexpr Temperature D65_TEMP = 6500;
inline constexpr Temperature MAX_TEMP = 10000;

using Saturation = float;
inline constexpr Saturation MIN_SAT = 0.0f;
inline constexpr Saturation MAX_SAT = 2.0f;
inline constexpr Saturation DEFAULT_SAT = 1.0f;

using Hue = float;
inline constexpr Hue MIN_HUE = -1.0f;
inline constexpr Hue MAX_HUE = 1.0f;
inline constexpr Hue DEFAULT_HUE = 0.0f;

// Component 位掩码
enum Component : std::uint32_t {
    Component_None  = 0,
    Component_Red   = 1u << 0,
    Component_Green = 1u << 1,
    Component_Blue  = 1u << 2,
    Component_All   = Component_Red | Component_Green | Component_Blue,
};

using Contrast = float;
inline constexpr Contrast MIN_CONTRAST = 0.0f;
inline constexpr Contrast MAX_CONTRAST = 2.0f;
inline constexpr Contrast DEFAULT_CONTRAST = 1.0f;

using Gamma = float;
inline constexpr Gamma MIN_GAMMA = 0.0f;
inline constexpr Gamma MAX_GAMMA = 5.0f;
inline constexpr Gamma DEFAULT_GAMMA = 2.4f;

using Luminance = float;
inline constexpr Luminance MIN_LUMA = -1.0f;
inline constexpr Luminance MAX_LUMA = 1.0f;
inline constexpr Luminance DEFAULT_LUMA = 0.0f;

struct ColorRange {
    float lo, hi;
};
inline constexpr float MIN_RANGE = 0.0f;
inline constexpr float MAX_RANGE = 1.0f;
// CEA-861 有限范围
inline constexpr float MIN_LIMITED_RANGE = 16.0f / 255.0f;
inline constexpr float MAX_LIMITED_RANGE = 235.0f / 255.0f;

// Time: uint8_t h, m, s; __attribute__((aligned(4)))
struct __attribute__((aligned(4))) Time {
    std::uint8_t h, m, s;
};

// ── fizeau.h ──
struct FizeauSettings {
    Temperature temperature;
    Saturation  saturation;
    Hue         hue;
    Contrast    contrast;
    Gamma       gamma;
    Luminance   luminance;
    ColorRange  range;
};

struct FizeauProfile {
    FizeauSettings day_settings, night_settings;
    Component      components;
    Component      filter;

    Time dusk_begin, dusk_end;
    Time dawn_begin, dawn_end;

    Time dimming_timeout;
};

enum FizeauCommandId : std::uint32_t {
    FizeauCommandId_GetIsActive = 0,
    FizeauCommandId_SetIsActive,
    FizeauCommandId_GetProfile,
    FizeauCommandId_SetProfile,
    FizeauCommandId_GetActiveProfileId,
    FizeauCommandId_SetActiveProfileId,
};

enum FizeauProfileId : std::uint32_t {
    FizeauProfileId_Profile1 = 0,
    FizeauProfileId_Profile2,
    FizeauProfileId_Profile3,
    FizeauProfileId_Profile4,
    FizeauProfileId_Total,
    FizeauProfileId_Invalid = 0xffff,
};

// fizeauSetProfile 发送的结构（fizeau.c 里的匿名 struct）
struct SetProfileRequest {
    FizeauProfileId id;
    FizeauProfile   profile;
};

inline constexpr const char *FIZEAU_SERVICE_NAME = "fizeau";

} // namespace fz
