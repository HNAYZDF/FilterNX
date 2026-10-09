/*
 * switch_shim.h — 最小 libnx 垫片（仅供主机侧测试）
 *
 * 作用: 让只依赖少量 libnx 类型/宏的协议头（ipc.hpp）能在 PC 上用普通
 *       g++ 编译，从而对 IPC 协议做字节级往返测试。
 *
 * 原则: 只提供测试真正需要的定义，且语义必须与 libnx 一致——
 *       尤其是 Result 的位布局与 R_SUCCEEDED / R_FAILED / MAKERESULT，
 *       否则测试会给出与真机不同的结论。
 *
 * libnx 的 Result 是 u32（原为 u64，新版本改为 u32）:
 *   bit 31     : 1 = 失败（R_FAILED），0 = 成功
 *   bit 30..28 : Module
 *   bit 27..9  : Description
 *   bit 8..0   : 保留
 */

#pragma once

#include <cstdint>
#include <cstddef>

using u8  = std::uint8_t;
using u16 = std::uint16_t;
using u32 = std::uint32_t;
using u64 = std::uint64_t;
using s32 = std::int32_t;
using s64 = std::int64_t;

using Result = u32;

// ---- 与 libnx 一致的结果码构造/判定 ----
#define MAKERESULT(module, description) \
    ((((Result)(module) & 0x1FF) << 28) | (((Result)(description) & 0x3FFFF) << 9))

#define R_SUCCEEDED(res)  ((res) == 0)
#define R_FAILED(res)     ((res) != 0)
#define R_MODULE(res)     (((res) >> 28) & 0x1FF)
#define R_DESCRIPTION(res) (((res) >> 9) & 0x3FFFF)

// 测试里用到的少量模块号/描述值（只要能让 R_FAILED 成立即可）
enum {
    Module_Libnx = 345,
};

enum {
    LibnxError_BadInput        = 1,
    LibnxError_NotInitialized  = 2,
    LibnxError_NotFound        = 3,
};

enum {
    KernelError_ConnectionClosed = 0x7C0,
};

#define KERNELRESULT(desc) MAKERESULT(2, desc)

// 协议头里出现的类型（测试不实际调用服务，给个占位即可）
struct Service {
    std::uint32_t session;
};
