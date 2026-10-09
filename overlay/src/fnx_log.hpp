/*
 * fnx_log.hpp — 逐步日志（超能滤镜）
 *
 * ═══════════════════════════════════════════════════════════════════════════
 * 为什么需要它
 * ═══════════════════════════════════════════════════════════════════════════
 * 真机故障: Fizeau 没运行时打开插件 → **整个特斯拉菜单消失**。
 *
 * 这类"进程直接死掉"的问题，屏幕上什么都不剩，没法调试。
 * 反复猜测都没根治，而每次验证都要用户装卡、重启、复现 —— 代价太高。
 *
 * 所以加这个日志: 每一步写一行到 SD 卡。
 * 崩了之后，**日志最后一行就是崩溃前最后执行到的地方**。
 *
 * ═══════════════════════════════════════════════════════════════════════════
 * ⚠ 路径必须全部是 ASCII —— 这是踩过的坑
 * ═══════════════════════════════════════════════════════════════════════════
 * 第一版把日志放在 `sdmc:/config/超能滤镜/日志.txt`（中文目录名）。
 * 结果可能是: mkdir 对非 ASCII 路径失败 → fopen 也失败 → 日志文件根本
 * 不存在 → **我们什么证据都拿不到，等于白加**。
 *
 * 现在用纯 ASCII:
 *     sdmc:/config/filternx/log.txt
 *
 * 并且**同时尝试多个路径**，只要有一个能写就成功 —— 这样即便某个
 * 目录权限异常，也还有退路:
 *     1. sdmc:/config/filternx/log.txt   （常规位置）
 *     2. sdmc:/filternx_log.txt          （卡根目录，一定可写）
 *
 * ═══════════════════════════════════════════════════════════════════════════
 * 设计取舍
 * ═══════════════════════════════════════════════════════════════════════════
 * · 每行 fclose —— 保证崩溃前那一行已经落盘。只写几次，性能无所谓。
 * · 不用 libultrahand 的 logMessage —— 早期它自身是否可用不确定，
 *   而这里要的正是**最早阶段**的记录。
 * · 任何失败都静默忽略 —— 日志不能成为新的崩溃点。
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * GPLv2，详见 LICENSE。
 */

#pragma once

#include <cstdio>
#include <cstring>
#include <sys/stat.h>

namespace fnx {

inline constexpr const char *LOG_DIR   = "sdmc:/config/filternx";
inline constexpr const char *LOG_PATH  = "sdmc:/config/filternx/log.txt";
inline constexpr const char *LOG_FALLBACK = "sdmc:/filternx_log.txt";

/*
 * 写一行日志。
 *
 * ⚠ 刻意**不做任何可能失败并抛异常的事**:
 *   · mkdir 失败就放弃
 *   · fopen 失败就换下一个候选路径
 *   · 全部用 C 的 stdio，不涉及 C++ 异常
 */
inline void fnxLog(const char *msg) {
    static bool dir_tried = false;
    if (!dir_tried) {
        dir_tried = true;
        // 只建一层。返回 -1 表示"已存在"或"建不了"，都不影响后面。
        ::mkdir(LOG_DIR, 0777);
    }

    // 依次尝试候选路径，第一个能打开的就用
    static const char *candidates[] = { LOG_PATH, LOG_FALLBACK };

    for (const char *path : candidates) {
        std::FILE *f = std::fopen(path, "a");
        if (!f)
            continue;
        std::fputs(msg, f);
        std::fputc('\n', f);
        std::fclose(f);   // ← 立即落盘: 崩溃前那一行必须保住
        return;
    }
    // 全部失败: 静默返回。日志不能成为新的崩溃点。
}

/*
 * 记录一个 Result（错误码）。
 * 用十六进制打印，方便对照 Atmosphère / libnx 的错误码表。
 */
inline void fnxLogRc(const char *what, unsigned rc) {
    char buf[160];
    std::snprintf(buf, sizeof(buf), "%s 0x%08X", what, rc);
    fnxLog(buf);
}

} // namespace fnx
