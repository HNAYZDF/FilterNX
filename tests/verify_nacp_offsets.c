// verify_nacp_offsets.c — 用编译器 + libnx 官方头文件独立验证 NACP 偏移
//
// ═══════════════════════════════════════════════════════════════════════════
// 为什么需要这个
// ═══════════════════════════════════════════════════════════════════════════
// 之前出过一次严重故障: 把版本号写进了 isbn（0x3000）而不是
// display_version（0x3060），结果菜单显示 1.0.0 —— 而且回读脚本用了同样
// 错误的偏移，**两边错得一致，互相"验证"通过**。
//
// 根因是偏移量被手抄在多处。现在 tools/nacp_layout.py 是唯一来源，
// 但**它本身也是手写的**，仍可能与官方定义不符。
//
// 本程序消除这个风险: 不自己算任何数字，而是 #include libnx 的 nacp.h，
// 让编译器（真实 ABI 规则）算出 offsetof 与 sizeof，再与 nacp_layout.py
// 的值逐一比对。任何不一致都会编译失败或运行时失败。
//
// 构建方式（主机侧，用 MSYS2 的 g++，不需要 devkitA64）:
//   g++ -std=c++17 -I<libnx>/include -I<switch_shim> verify_nacp_offsets.c
//
// switch_shim.h 提供 u8/u16/u32/u64/s8 等类型定义 —— libnx 头文件
// 依赖它们，但本程序只用结构体布局，不调用任何 libnx 函数。
//
// 退出码 0 = 全部一致；非 0 = 有偏移不符（并打印出错项）。
// ═══════════════════════════════════════════════════════════════════════════

#include <stdio.h>
#include <stddef.h>
#include <string.h>

// libnx 的 nacp.h 假定调用方已引入 switch/types.h，这里用垫片补齐
// u8/u16/u32/u64/s8 等类型名。结构体定义本身仍来自官方头文件。
#include "libnx_types_shim.h"
#include <switch/nacp.h>

// ── nacp_layout.py 里声明的值（由本程序核对）──
//    改 nacp_layout.py 时必须同步改这里，否则本程序会失败 —— 这正是目的。
#define EXPECTED_LANG_STRIDE      0x300
#define EXPECTED_LANG_COUNT       16
#define EXPECTED_ISBN_OFFSET      0x3000
#define EXPECTED_DISPLAY_VER_OFF  0x3060
#define EXPECTED_NAME_SIZE        0x200
#define EXPECTED_AUTHOR_SIZE      0x100
#define EXPECTED_DISPLAY_VER_SIZE 0x10

static int g_fail = 0;
static int g_checks = 0;

static void ck(long long actual, long long expected, const char *what) {
    ++g_checks;
    if (actual == expected) {
        printf("  PASS  %-38s = 0x%llX\n", what, (unsigned long long)actual);
    } else {
        printf("  FAIL  %-38s = 0x%llX  期望 0x%llX\n",
               what, (unsigned long long)actual, (unsigned long long)expected);
        ++g_fail;
    }
}

int main(void) {
    printf("=== NACP 偏移验证（依据: libnx 官方 nacp.h，由编译器实测）===\n\n");

    // ── NacpLanguageEntry ──
    ck(sizeof(NacpLanguageEntry), EXPECTED_LANG_STRIDE,
       "sizeof(NacpLanguageEntry)");
    ck(offsetof(NacpLanguageEntry, name), 0x0, "NacpLanguageEntry.name");
    ck(offsetof(NacpLanguageEntry, author), EXPECTED_NAME_SIZE,
       "NacpLanguageEntry.author");
    ck(sizeof(((NacpLanguageEntry *)0)->name), EXPECTED_NAME_SIZE,
       "sizeof(name)");
    ck(sizeof(((NacpLanguageEntry *)0)->author), EXPECTED_AUTHOR_SIZE,
       "sizeof(author)");

    // ── 语言数组 ──
    ck(sizeof(((NacpLanguageEntryData *)0)->lang), 0x3000,
       "sizeof(lang_data.lang)  [16 * 0x300]");
    ck(sizeof(((NacpLanguageEntryData *)0)->lang[0]), EXPECTED_LANG_STRIDE,
       "sizeof(lang[0])");

    // ── 关键字段偏移 ──
    //
    // 这两个是最容易搞错的:
    //   isbn            在 0x3000 —— 曾把版本号误写到这里，菜单读不到
    //   display_version 在 0x3060 —— 真正决定菜单显示版本的字段
    ck(offsetof(NacpStruct, isbn), EXPECTED_ISBN_OFFSET, "offsetof(isbn)");
    ck(offsetof(NacpStruct, display_version), EXPECTED_DISPLAY_VER_OFF,
       "offsetof(display_version)");
    ck(sizeof(((NacpStruct *)0)->display_version), EXPECTED_DISPLAY_VER_SIZE,
       "sizeof(display_version)");

    // ── lang 数组在结构体里的位置 ──
    ck(offsetof(NacpStruct, lang_data), 0x0, "offsetof(lang_data)");
    ck(offsetof(NacpStruct, lang_data.lang[0].name), 0x0, "lang[0].name");
    ck(offsetof(NacpStruct, lang_data.lang[1].name), EXPECTED_LANG_STRIDE,
       "lang[1].name  [步长]");
    ck(offsetof(NacpStruct, lang_data.lang[15].name),
       (long long)EXPECTED_LANG_STRIDE * 15, "lang[15].name");

    // ── display_version 必须能被 0x10 字节容纳（含结尾 NUL）──
    //    版本号 "1.0.3" 是 5 字节，余量充足；但若将来写长版本号会溢出。
    ++g_checks;
    if (EXPECTED_DISPLAY_VER_SIZE >= 8) {
        printf("  PASS  display_version 字段足够放版本号 (%d 字节)\n",
               EXPECTED_DISPLAY_VER_SIZE);
    } else {
        printf("  FAIL  display_version 字段太小\n");
        ++g_fail;
    }

    // ── isbn 与 display_version 不能重叠 ──
    ++g_checks;
    if (offsetof(NacpStruct, display_version) >=
        offsetof(NacpStruct, isbn) + sizeof(((NacpStruct *)0)->isbn)) {
        printf("  PASS  isbn 与 display_version 不重叠\n");
    } else {
        printf("  FAIL  isbn 与 display_version 重叠 —— 写版本号会破坏 isbn\n");
        ++g_fail;
    }

    printf("\n============================================================\n");
    printf("检查项: %d   失败: %d\n", g_checks, g_fail);
    printf("%s\n", g_fail ? "结果: 存在不一致 —— 偏移定义有误" : "结果: 全部一致");
    return g_fail ? 1 : 0;
}
