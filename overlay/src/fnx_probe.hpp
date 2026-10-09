/*
 * fnx_probe.hpp — 判断 Fizeau 是否在运行（**不用 smGetService**）
 *
 * ═══════════════════════════════════════════════════════════════════════════
 * 为什么不用 smGetService —— 这是从成熟实现学到的方法
 * ═══════════════════════════════════════════════════════════════════════════
 * 真机故障: Fizeau 没运行时打开插件 → **整个特斯拉菜单消失**。
 * 反复用 smGetService 判断可用性都会崩，说明"发起连接"这个动作本身
 * 在服务不存在时行为不可预期。
 *
 * 参考 sys-clk overlay（同类插件，处理同样的问题）的做法:
 *
 *     bool sysclkIpcRunning() {
 *         Handle handle;
 *         // 尝试**注册**同名服务:
 *         //   失败 = 名字已被占用 = 服务正在运行
 *         //   成功 = 名字没人用   = 服务没运行 → 立刻撤销注册
 *         bool running = R_FAILED(smRegisterService(&handle, name, false, 1));
 *         if (!running) smUnregisterService(name);
 *         return running;
 *     }
 *
 * ⚠ 上面这段上游写法**漏了关句柄**: smRegisterService 成功时会返回一个
 *   服务端口句柄（见下方 isServiceRunning 的说明），本文件补上了
 *   svcCloseHandle —— 探测函数会被反复调用，句柄不能泄漏。
 *
 * 关键在于: `smRegisterService` 只是往 sm 的名字表里写一条，
 * **不建立客户端会话、不接触目标进程**。所以无论目标服务在不在，
 * 它都只是返回一个错误码 —— 这正是"纯探测"该有的样子。
 *
 * 而 `smGetService` 会真的去建立会话、拿句柄，涉及目标进程的状态，
 * 那才是不可预期的部分。
 *
 * ═══════════════════════════════════════════════════════════════════════════
 * ⚠ 一个必须小心的语义陷阱
 * ═══════════════════════════════════════════════════════════════════════════
 * `smRegisterService` 失败**不一定**因为"服务在运行"—— 也可能因为
 * **sm 会话根本没初始化**。两种情况都是 R_FAILED，但含义完全相反。
 *
 * 所以必须先确认 sm 会话有效，否则会把"sm 没起来"误判成"Fizeau 在运行"，
 * 然后去 `fzInitialize()` —— 那正是我们想避开的路径。
 *
 * ═══════════════════════════════════════════════════════════════════════════
 * GPLv2，详见 LICENSE。
 */

#pragma once

#include <switch.h>

namespace fnx {

// sm 会话是否可用
inline bool smSessionReady() {
    Service *s = smGetServiceSession();
    return s && serviceIsActive(s);
}

/*
 * 服务是否正在运行。
 *
 * 返回:
 *   false —— sm 会话不可用，或注册成功（名字空闲 ⇒ 服务没在运行）
 *   true  —— 注册失败（判为"名字已被占用" ⇒ 服务在运行）
 *
 * ⚠ 关于"不确定"的情况 —— 与直觉相反，务必看清:
 *   smRegisterService 失败时**不区分**原因是"名字已被占用"还是别的
 *   （权限等），两种情况都返回 true（判为在运行）。这是 sys-clk overlay
 *   同款探测的既有语义，这里刻意保持不变，因为两个方向的代价不对称:
 *     误判成"在运行"  → 多走一次 smGetService，那条路径有失败处理，不会崩
 *     误判成"没运行"  → Fizeau 明明开着也永远只显示引导页（插件彻底失效）
 *   （唯一的例外是 sm 会话本身无效 —— 那由 smSessionReady() 提前挡掉，
 *     因为把"sm 没起来"当成"服务在运行"才是真正危险的方向。）
 */
inline bool isServiceRunning(const char *name) {
    // 先确认 sm 会话有效，避免把"sm 没起来"误判成"服务在运行"
    if (!smSessionReady())
        return false;

    const SmServiceName enc = smEncodeName(name);
    Handle handle = INVALID_HANDLE;

    const Result rc = smRegisterService(&handle, enc, false, 1);
    if (R_SUCCEEDED(rc)) {
        // 注册成功 = 这个名字没人用 = 服务没在运行。
        //
        // ⚠ 必须**先关句柄、再撤销注册**，两步缺一不可:
        //   smRegisterService 成功时会把一个**服务端口句柄**写进 handle
        //   （libnx sm.h: "handle_out Variable containing IPC port handle"），
        //   这个句柄归调用方所有。不关 = 每探测一次泄漏一个句柄，而本函数
        //   的调用方是常驻的特斯拉菜单进程 —— 反复开关插件会把句柄表耗光。
        //   上游 ipc_server.c 的 ipcServerExit() 同样是"先关全部句柄，
        //   再 smUnregisterService"（_ovlres/fizeau/ipc_server.c:33-41）。
        if (handle != INVALID_HANDLE)
            svcCloseHandle(handle);
        smUnregisterService(enc);
        return false;
    }

    // 注册失败 = 判为"名字已被占用"（理由见上方说明）
    return true;
}

/*
 * Fizeau 是否在运行。
 *
 * ⚠ 这是**唯一**用来判断"能不能用"的依据 —— 它不建立任何会话。
 */
inline bool isFizeauRunning() {
    return isServiceRunning("fizeau");
}

} // namespace fnx
