// FilterNX — 界面布局约束测试
//
// 目的: 从源码层面强制"文字不会超出可用宽度"这条约束。
//
// ═══════════════════════════════════════════════════════════════════════════
// 为什么需要这个测试
// ═══════════════════════════════════════════════════════════════════════════
// 真机实测发现:「单色暖黄」在界面里被显示成「单色」，且触发了滚动动画。
//
// 原因在 libultrahand 的 ListItem::calculateWidths:
//     m_maxWidth  = getWidth() - valueWidth - 66
//     m_truncated = textWidth > m_maxWidth + 20
// 说明文字越长，名字可用宽度越小。
//
// 精确宽度无法在电脑上复现（字形 xAdvance 来自运行时加载的系统共享字体），
// 所以本测试改为在**源码层面**守住字符数上限。这比估算像素宽度可靠得多:
// 它完全不依赖字体，只要文案守规矩就不可能截断。
//
// 覆盖两处:
//   1. 预设表的 name / desc 字段
//   2. gui.cpp / presets.hpp 里所有 ListItem("名字", "说明") 调用点
// ═══════════════════════════════════════════════════════════════════════════

#include "fizeau_ipc.hpp"
#include "presets.hpp"
#include "layout.hpp"

#include <cstdio>
#include <cstring>
#include <fstream>
#include <regex>
#include <sstream>
#include <string>
#include <vector>

using namespace fnx;
using namespace fnx::ui;   // 布局常量（VISIBLE_HEIGHT / MAIN_HEADERS 等）

static int g_checks = 0;
static int g_failures = 0;

static void check(bool cond, const std::string &label) {
    ++g_checks;
    if (cond) {
        printf("  PASS  %s\n", label.c_str());
    } else {
        printf("  FAIL  %s\n", label.c_str());
        ++g_failures;
    }
}

// 按 UTF-8 编码统计字符数（不是字节数）。
// 界面的宽度约束是按"字符"计的，中文每字 3 字节，用 size() 会误判。
//
// 注意: presets.hpp 里已经有一个内联的 utf8_length，这里不再重复定义 ——
// 重复定义会造成重载歧义（compiler: call of overloaded ... is ambiguous）。
#define utf8_length fnx::utf8_length

/*
 * 显示宽度，单位是"全角字宽"（1.0 = 一个汉字）。
 *
 * 为什么不用字符个数:
 *   数字/ASCII 是半宽（约占全角 0.6），「259121473」9 位数字
 *   实际比「超能滤镜」4 个汉字还窄。只数字符会把正常的 QQ 群号误判为超限。
 *
 * 判定规则（不影响 ASCII，够用且保守）:
 *   · CJK / 全角标点 → 1.0
 *   · 其它（ASCII 字母数字符号）→ 0.6
 */
static double display_width(const char *s) {
    if (!s)
        return 0.0;
    double w = 0.0;
    const unsigned char *p = reinterpret_cast<const unsigned char *>(s);
    while (*p) {
        if (*p < 0x80) {
            w += 0.6;                       // ASCII
            ++p;
        } else {
            w += 1.0;                       // 多字节（CJK 等），算全角
            ++p;
            while (*p && (*p & 0xC0) == 0x80) ++p;   // 跳过后续字节
        }
    }
    return w;
}

// 从源码里提取 ListItem("名字", "说明") 的参数
struct ListItemCall {
    std::string text;
    std::string value;
    std::string file;
    int         line;
};

static std::vector<ListItemCall> extract_list_items(const std::string &path) {
    std::vector<ListItemCall> out;
    std::ifstream in(path);
    if (!in)
        return out;

    // ListItem(  "..."  ,  "..."  )   —— 允许参数里有中文与转义引号
    //
    // 注意: 正则里含 `)"` 序列，直接用 R"(...)" 会提前终止字面量，
    // 因此改用自定义分隔符 RE。
    std::regex re(R"RE(ListItem\s*\(\s*"((?:[^"\\]|\\.)*)"\s*,\s*"((?:[^"\\]|\\.)*)")RE");

    // ── 跳过只在诊断构建里编译的代码块 ──
    //
    // #ifdef FNX_NO_FIZEAU ... #endif 之间的界面**不在正式版产物里**，
    // 所以不该用正式版的宽度/高度预算去约束它。
    // （诊断页的文案较长是刻意的，它只在排障时用。）
    //
    // ⚠ 不用"放宽阈值"来绕过 —— 那会让正式版的真实超宽也一起放过。
    //   按条件编译边界排除才精确。
    int cond_depth = 0;

    std::string line;
    int lineno = 0;
    while (std::getline(in, line)) {
        ++lineno;

        if (line.find("#ifdef FNX_NO_FIZEAU") != std::string::npos ||
            line.find("#ifndef FNX_NO_FIZEAU") != std::string::npos) {
            ++cond_depth;
            continue;
        }
        if (line.find("#endif") != std::string::npos && cond_depth > 0) {
            --cond_depth;
            continue;
        }
        if (cond_depth > 0)
            continue;

        auto begin = std::sregex_iterator(line.begin(), line.end(), re);
        for (auto it = begin; it != std::sregex_iterator(); ++it) {
            ListItemCall c;
            c.text  = (*it)[1].str();
            c.value = (*it)[2].str();
            c.file  = path;
            c.line  = lineno;
            out.push_back(c);
        }
    }
    return out;
}

// 定位源码文件。
//
// 不依赖运行时的当前工作目录 —— 从若干候选路径里找一个真实存在的。
// 这样从任意目录运行都能工作，避免"换个地方跑就找不到文件"的脆弱测试。
static std::string find_source(const char *rel) {
    const char *candidates[] = {
        // 从 filternx/ 目录运行
        "overlay/",
        // 从工作区根目录运行
        "filternx/overlay/",
        // 从 tests/ 目录运行
        "../overlay/",
        // 从 tests/build/ 目录运行
        "../../overlay/",
        // 绝对回退
        "C:/Users/hnayz/Documents/deepseek-harness/default-workspace/filternx/overlay/",
    };

    for (const char *c : candidates) {
        std::string p = std::string(c) + rel;
        std::ifstream probe(p);
        if (probe.good())
            return p;
    }
    return {};
}

int main(int argc, char **argv) {
    printf("=== FilterNX 界面布局约束测试 ===\n\n");

    // ── 0. 源码级的静态约束 ──
    //
    // 这几条检查的是"代码结构"，不是数值。它们守的是曾经踩过的坑。
    printf("[源码静态约束]\n");
    {
        const std::string gui = find_source("src/gui.cpp");
        if (gui.empty()) {
            printf("        ★ 找不到 src/gui.cpp\n");
            check(false, "能找到 gui.cpp");
        } else {
            std::ifstream in(gui);
            std::string src((std::istreambuf_iterator<char>(in)),
                             std::istreambuf_iterator<char>());

            // ① MainGui::update() 不能是空的
            //
            // createUI() 只在首次进入页面时调用一次，之后回到该页面走的是
            // update()（tesla.hpp:11370 每帧调用）。若 update() 为空，
            // 「当前画面」会一直显示旧值 —— 真机实测过这个 bug。
            const bool update_empty =
                src.find("void MainGui::update() {}") != std::string::npos;
            check(!update_empty,
                  "MainGui::update() 不为空（否则「当前画面」不会实时刷新）");

            // ② update() 里必须真的回读状态
            check(src.find("void MainGui::update()") != std::string::npos &&
                  src.find("refresh_state") != std::string::npos,
                  "update() 中调用了 refresh_state() 回读真实状态");

            // ③ 三项状态必须存为可更新指针，而不是一次性 addItem
            check(src.find("g_filter_item") != std::string::npos &&
                  src.find("g_effect_item") != std::string::npos &&
                  src.find("g_profile_item") != std::string::npos,
                  "「当前画面」三项存为指针，可在 update() 里 setValue");

            // ④ 必须用 setValue 更新文本（这是 ListItem 的公开接口）
            check(src.find("->setValue(") != std::string::npos,
                  "使用 ListItem::setValue() 更新显示");
        }
    }

    // ── 1. 预设表的名字与说明长度 ──
    printf("\n[预设表文案长度]\n");
    {
        int bad = 0;
        for (const auto &p : PRESETS) {
            const std::size_t n = utf8_length(p.name);
            const std::size_t d = utf8_length(p.desc);
            if (n > NAME_MAX_CHARS) {
                ++bad;
                printf("        ★ '%s' 名字 %zu 字，超过上限 %zu\n",
                       p.id, n, NAME_MAX_CHARS);
            }
            if (d > DESC_MAX_CHARS) {
                ++bad;
                printf("        ★ '%s' 说明 %zu 字，超过上限 %zu\n",
                       p.id, d, DESC_MAX_CHARS);
            }
        }
        check(bad == 0, "全部预设的名字 ≤4 字、说明 ≤5 字");
    }
    {
        // 名字非空
        bool ok = true;
        for (const auto &p : PRESETS) {
            if (utf8_length(p.name) == 0 || utf8_length(p.desc) == 0)
                ok = false;
        }
        check(ok, "名字与说明都不为空");
    }

    // ── 2. GUI 源码里的 ListItem 调用 ──
    printf("\n[界面源码的 ListItem 文案长度]\n");
    {
        const char *srcs[] = {
            "src/gui.cpp",
            "src/presets.hpp",
        };

        int total = 0, bad = 0, missing = 0;
        for (const char *s : srcs) {
            const std::string path = find_source(s);
            if (path.empty()) {
                printf("        ★ 找不到源码文件: %s\n", s);
                ++missing;
                continue;
            }
            for (const auto &c : extract_list_items(path)) {
                ++total;
                const std::size_t n = utf8_length(c.text.c_str());
                const std::size_t d = utf8_length(c.value.c_str());

                // 取值列宽度上限。
                //
                // 依据: 全角字符宽度 ≈ 字号。取值列字号 20、名字列字号 23
                // （tesla.hpp:7849 / 7435）。实测「效果」(2 字 = 46px) 在
                // value 约 240px 时被截断成「效」，说明可用宽度在 300px 上下。
                //
                // ⚠ 不能只数字符个数: 数字与 ASCII 是半宽（约占全角的 0.6），
                //   所以「259121473」(9 位数字) 比「超能滤镜」(4 个汉字) 还窄。
                //   这里按**显示宽度**换算，再用全角字数为单位比较。
                //
                // 上限取 8.0 个全角字宽（= 160px @字号20）。
                // 名字列上限 6.0。
                constexpr double VALUE_MAX_W = 8.0;
                constexpr double NAME_MAX_W  = 6.0;

                const double nw = display_width(c.text.c_str());
                const double dw = display_width(c.value.c_str());

                if (nw > NAME_MAX_W || dw > VALUE_MAX_W) {
                    ++bad;
                    printf("        ★ %s:%d  \"%s\" / \"%s\"   (宽 %.1f / %.1f 全角字)\n",
                           c.file.c_str(), c.line,
                           c.text.c_str(), c.value.c_str(), nw, dw);
                }
            }
        }
        printf("        共检查 %d 处 ListItem 调用\n", total);
        check(missing == 0, "找到了全部源码文件");
        check(total > 0, "成功从源码提取到 ListItem 调用（正则未失效）");
        check(bad == 0, "所有 ListItem 的名字 ≤6 字、取值 ≤8 字");
    }

    // ── 3. utf8_length 自身正确性 ──
    printf("\n[utf8_length 正确性]\n");
    {
        check(utf8_length("") == 0, "空串为 0 字");
        check(utf8_length("abc") == 3, "ASCII 3 字");
        check(utf8_length("黑白") == 2, "2 个汉字 = 2 字（不是 6 字节）");
        check(utf8_length("单色暖黄") == 4, "4 个汉字 = 4 字");
        check(utf8_length("复古CRT") == 5, "中英混排「复古CRT」= 5 字");
        check(utf8_length(nullptr) == 0, "nullptr 返回 0");
    }

    // ── 4. 预设名字不应互相包含（避免用户看错）──
    printf("\n[预设名字区分度]\n");
    {
        int ambiguous = 0;
        for (std::size_t i = 0; i < PRESETS.size(); ++i) {
            for (std::size_t j = 0; j < PRESETS.size(); ++j) {
                if (i == j) continue;
                const std::string a = PRESETS[i].name;
                const std::string b = PRESETS[j].name;
                // a 是 b 的前缀且长度不同 → 界面上容易混淆
                if (a.size() < b.size() && b.compare(0, a.size(), a) == 0) {
                    ++ambiguous;
                }
            }
        }
        check(ambiguous == 0, "没有预设名字是另一个的前缀");
    }

    // ── 5. 每页的高度预算 ──
    //
    // 这是真机实测踩过的第二个坑: 内容超出 List 的裁剪矩形时，
    // 屏幕底部会出现半行残影（「生效方式」被切掉）。
    //
    // 裁剪矩形来自 tesla.hpp 的 List::draw():
    //     enableScissoring(0, 88, FramebufferWidth,
    //                      FramebufferHeight - 73 - 97 + 2 + 5);
    // 720 下可见高度 = 557。
    printf("\n[每页高度预算]\n");
    {
        const int main_h = height_budget(MAIN_HEADERS, MAIN_ITEMS);
        printf("        主页面: 首项偏移%d + %d小标题*%d + %d项*%d = %d px (可见 %d)\n",
               FIRST_ITEM_OFFSET, MAIN_HEADERS, HEADER_HEIGHT,
               MAIN_ITEMS, ITEM_HEIGHT, main_h, VISIBLE_HEIGHT);

        // ① 整页必须放得下 —— 主页面是"一屏看全"的页面:
        //    它没有"滚动到底"的引导，掉到裁剪区外的行用户基本发现不了。
        //    真机/预览实测过: 页面一度是 8 项 = 692px，于是「关于本插件」
        //    （作者与 QQ 群的入口）落在裁剪区外，用户找不到。
        //    tools/check_preview_clip.py 从裁剪矩形那一侧守着同一条要求。
        check(main_h <= VISIBLE_HEIGHT,
              "主页面整页高度不超过可见区域（不会出现底部残影/入口被裁）");

        // ② 首屏还必须含全部关键入口（状态行 + 操作项）。
        //
        //    ⚠ 历史教训: layout.hpp 的常量曾经停在 5 项（实际一度是 8 项），
        //    断言于是算的是**一个不存在的页面** —— 断言"通过"，真实页面
        //    却溢出 135px。所以常量与 gui.cpp 的 addItem 数必须同步；
        //    这条按"前 5 项"的断言是第二道网:
        //       首屏内容 = 前 2 个小标题 + 前 5 个列表项
        //                = 33 + 2*33 + 5*70 = 482 ≤ 557
        //    （即 3 个状态行 + 2 个操作项一定看得见。）
        const int main_first_screen =
            FIRST_ITEM_OFFSET + 2 * HEADER_HEIGHT + 5 * ITEM_HEIGHT;
        printf("        主页面首屏（3 状态行 + 2 操作项）: %d px\n", main_first_screen);
        check(main_first_screen <= VISIBLE_HEIGHT,
              "主页面首屏含全部状态行与操作项（关键入口不会被裁掉）");

        const int preset_h = height_budget(PRESET_HEADERS, PRESET_ITEMS);
        printf("        预设页: 首项偏移%d + %d小标题*%d + %d项*%d = %d px (可见 %d)\n",
               FIRST_ITEM_OFFSET, PRESET_HEADERS, HEADER_HEIGHT,
               PRESET_ITEMS, ITEM_HEIGHT, preset_h, VISIBLE_HEIGHT);
        check(preset_h > VISIBLE_HEIGHT,
              "预设页确实需要滚动（用于验证滚动机制本身工作正常）");

        const int info_h = height_budget(INFO_HEADERS, INFO_ITEMS);
        printf("        信息页: 首项偏移%d + %d小标题*%d + %d项*%d = %d px (可见 %d)\n",
               FIRST_ITEM_OFFSET, INFO_HEADERS, HEADER_HEIGHT,
               INFO_ITEMS, ITEM_HEIGHT, info_h, VISIBLE_HEIGHT);
        // 信息页允许滚动，但要确认它不被裁剪到丢失关键信息。
        // 这里只断言"标题区能放下"（前 2 个小标题 + 前 3 项）：
        //   33 + 2*33 + 3*70 = 309 ≤ 557
        // 也就是作者与三个群号一定能在首屏看到，无需滚动。
        const int info_first_screen = FIRST_ITEM_OFFSET + 2 * HEADER_HEIGHT + 3 * ITEM_HEIGHT;
        printf("        信息页首屏（作者+3个群号）: %d px\n", info_first_screen);
        check(info_first_screen <= VISIBLE_HEIGHT,
              "信息页首屏能完整显示作者与三个 QQ 群（无需滚动即可看到）");
    }

    // ── 6. 摘要字符串长度 ──
    //
    // 主界面的「效果」行名字只有 2 字，value 过长会把名字挤掉
    // （实测被截断成「效」）。
    printf("\n[摘要字符串长度]\n");
    {
        constexpr std::size_t SUMMARY_MAX = 10;
        int bad = 0;
        std::size_t worst = 0;
        std::string worst_s;

        for (const auto &p : PRESETS) {
            const std::string s = settings_summary(p.settings, p.filter);
            const std::size_t n = utf8_length(s.c_str());
            if (n > worst) { worst = n; worst_s = s; }
            if (n > SUMMARY_MAX) {
                ++bad;
                printf("        ★ '%s' 摘要 %zu 字: \"%s\"\n", p.id, n, s.c_str());
            }
        }
        printf("        最长摘要: \"%s\" (%zu 字)\n", worst_s.c_str(), worst);
        check(bad == 0, "全部预设的摘要 ≤10 字");

        // 极端情况: 用户自己调出的设置也不该超长
        FzSettings custom{};
        custom.temperature = 10000;
        custom.saturation  = 2.0f;
        custom.gamma       = 5.0f;
        custom.range       = { 0.0f, 1.0f };
        const std::string cs = settings_summary(custom, COMP_NONE);
        printf("        最大值组合: \"%s\" (%zu 字)\n",
               cs.c_str(), utf8_length(cs.c_str()));
        check(utf8_length(cs.c_str()) <= SUMMARY_MAX,
              "取值全为上限时摘要仍不超过 10 字");
    }

    printf("\n========================================================\n");
    printf("检查项: %d   失败: %d\n", g_checks, g_failures);
    printf("%s\n", g_failures == 0 ? "结果: 全部通过" : "结果: 存在失败");
    return g_failures == 0 ? 0 : 1;
}
