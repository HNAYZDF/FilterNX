/*
 * libnx_types_shim.h — 为主机侧验证提供 libnx 的基础类型定义
 *
 * ═══════════════════════════════════════════════════════════════════════════
 * 为什么需要它
 * ═══════════════════════════════════════════════════════════════════════════
 * devkitPro 的 switch/nacp.h **不 include 任何头文件** —— 它假定调用方
 * 已经引入了 switch/types.h。所以主机侧（MSYS2 g++）想直接 #include
 * nacp.h，就必须先提供 u8/u16/u32/u64/s8 等基础类型。
 *
 * ═══════════════════════════════════════════════════════════════════════════
 * 关键点: 这里只是"类型别名"，不是"重写结构体"
 * ═══════════════════════════════════════════════════════════════════════════
 * NacpStruct / NacpLanguageEntry 的定义仍然来自**官方 nacp.h**，
 * 本文件只补齐类型名。所以 offsetof 的结果与真机 devkitA64 编译一致 ——
 * 这正是这个验证有意义的前提。
 *
 * ⚠ 如果这里改写结构体定义，验证就退化成"自己验证自己"，
 *   和当初 isbn/display_version 两处错得一致的情况没有区别。
 *
 * 类型取值严格照抄 libnx switch/types.h:
 *   typedef uint8_t  u8;   typedef int8_t  s8;   typedef uint32_t Result;
 *   且 libnx 的结构体**没有** __attribute__((packed))，
 *   所以按默认对齐即可，两侧一致。
 */

#pragma once

#include <cstdint>

typedef std::uint8_t  u8;
typedef std::uint16_t u16;
typedef std::uint32_t u32;
typedef std::uint64_t u64;

typedef std::int8_t   s8;
typedef std::int16_t  s16;
typedef std::int32_t  s32;
typedef std::int64_t  s64;

typedef u32 Result;
