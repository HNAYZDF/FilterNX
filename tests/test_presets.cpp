// FilterNX — 预设表主机侧测试
//
// 目的: 保证预设"真的有效、真的不同、真的合法、真的分级合理"。
//
// 这几件事都会在不知不觉中坏掉，而且坏掉后从界面上看不出来:
//   · 数值越界 → Fizeau 的 sanitize() 会**静默钳制**，
//     表现为"写入成功但效果不对"，是最难查的一类故障
//   · 两个预设参数相同 → 用户按下去看不到变化，会以为插件坏了
//   · 预设等于中性值 → 按下去毫无效果（除了那个故意的「原色」）
//   · 分级预设差距太小 → 号称"四档"实际看不出区别

#include "fizeau_ipc.hpp"
#include "presets.hpp"

#include <cstdio>
#include <cstring>
#include <cmath>
#include <cstdint>
#include <set>
#include <string>
#include <vector>

using namespace fnx;

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

static bool settings_equal(const FzSettings &a, const FzSettings &b) {
    return a.temperature == b.temperature
        && a.saturation  == b.saturation
        && a.hue         == b.hue
        && a.contrast    == b.contrast
        && a.gamma       == b.gamma
        && a.luminance   == b.luminance
        && a.range.lo    == b.range.lo
        && a.range.hi    == b.range.hi;
}

// 统计某个分类的预设数量
static std::size_t count_group(PresetGroup g) {
    std::size_t n = 0;
    for (const auto &p : PRESETS)
        if (p.group == g) ++n;
    return n;
}

int main() {
    printf("=== FilterNX 预设表测试 ===\n\n");

    // ── 1. 基本结构 ──
    printf("[预设表结构]\n");
    printf("        预设总数: %zu\n", PRESETS.size());
    check(PRESETS.size() >= 24, "预设数量充足（≥24）");
    {
        std::set<std::string> ids;
        bool uniq = true;
        for (const auto &p : PRESETS)
            if (!ids.insert(std::string(p.id)).second) uniq = false;
        check(uniq, "所有预设 id 唯一");
    }
    {
        bool named = true;
        for (const auto &p : PRESETS)
            if (!p.name || !*p.name || !p.desc || !*p.desc) named = false;
        check(named, "所有预设都有中文名与说明");
    }
    {
        // id 只允许小写字母、数字、下划线（便于将来做配置文件持久化）
        bool ok = true;
        for (const auto &p : PRESETS) {
            for (const char *c = p.id; *c; ++c) {
                if (!((*c >= 'a' && *c <= 'z') || (*c >= '0' && *c <= '9') || *c == '_')) {
                    ok = false;
                    printf("        ★ '%s' 含非法字符 '%c'\n", p.id, *c);
                }
            }
        }
        check(ok, "所有 id 仅含小写字母/数字/下划线");
    }
    {
        bool grouped = true;
        int last = -1;
        for (const auto &p : PRESETS) {
            const int g = static_cast<int>(p.group);
            if (g < last) grouped = false;
            if (g != last) last = g;
        }
        check(grouped, "预设按分类连续排列（界面小标题不会重复）");
    }
    {
        // 每个分类都要有内容，且分类名非空
        bool ok = true;
        for (int g = 0; g <= static_cast<int>(PresetGroup::Vision); ++g) {
            const auto grp = static_cast<PresetGroup>(g);
            if (count_group(grp) == 0) {
                ok = false;
                printf("        ★ 分类 '%s' 为空\n", group_name(grp));
            }
            if (!group_name(grp) || !*group_name(grp)) ok = false;
        }
        check(ok, "所有分类都有预设，且分类名非空");
    }

    // ── 2. 数值范围（关键）──
    printf("\n[数值范围（越界会被 Fizeau 静默钳制）]\n");
    {
        int bad = 0;
        for (const auto &p : PRESETS) {
            const auto &s = p.settings;
            const char *why = nullptr;

            if (s.temperature < TEMP_MIN || s.temperature > TEMP_MAX) why = "色温越界";
            else if (s.saturation < SAT_MIN || s.saturation > SAT_MAX) why = "饱和度越界";
            else if (s.hue < HUE_MIN || s.hue > HUE_MAX) why = "色相越界";
            else if (s.contrast < CONTRAST_MIN || s.contrast > CONTRAST_MAX) why = "对比度越界";
            else if (s.gamma < GAMMA_MIN || s.gamma > GAMMA_MAX) why = "伽马越界";
            else if (s.luminance < LUMA_MIN || s.luminance > LUMA_MAX) why = "亮度越界";
            else if (s.range.lo < RANGE_MIN || s.range.lo > RANGE_MAX) why = "范围下限越界";
            else if (s.range.hi < RANGE_MIN || s.range.hi > RANGE_MAX) why = "范围上限越界";
            else if (s.range.lo > s.range.hi) why = "范围下限大于上限";

            if (why) {
                ++bad;
                printf("        ★ 预设 '%s': %s\n", p.id, why);
            }
        }
        check(bad == 0, "全部预设的数值都在 Fizeau 合法范围内");
    }
    {
        // 伽马为 0 会让 Fizeau 的 regamma 计算退化，虽然合法但会产生极端画面。
        // 这里只是提示，不算失败 —— 保留灵活性。
        int extreme = 0;
        for (const auto &p : PRESETS)
            if (p.settings.gamma < 0.5f) ++extreme;
        check(extreme == 0, "没有预设使用极端伽马（<0.5）");
    }

    // ── 3. filter / components 取值合法 ──
    printf("\n[filter / components 取值]\n");
    {
        bool fok = true, cok = true;
        for (const auto &p : PRESETS) {
            if (p.filter != COMP_NONE && p.filter != COMP_RED &&
                p.filter != COMP_GREEN && p.filter != COMP_BLUE) {
                fok = false;
                printf("        ★ 预设 '%s' 的 filter = 0x%X 非法\n", p.id, p.filter);
            }
            if (p.components != COMP_ALL && p.components != COMP_NONE) {
                cok = false;
                printf("        ★ 预设 '%s' 的 components = 0x%X 非法\n",
                       p.id, p.components);
            }
        }
        check(fok, "所有 filter 均为 Fizeau 支持的 none/red/green/blue");
        check(cok, "所有 components 取值合法");
    }

    // ── 4. 查找函数（含边界）──
    printf("\n[查找函数]\n");
    check(find_preset("original") != nullptr, "能按 id 找到 'original'");
    check(find_preset("dim_deep") != nullptr, "能按 id 找到 'dim_deep'");
    check(find_preset("mono_amber") != nullptr, "能按 id 找到 'mono_amber'");
    check(find_preset("") == nullptr, "空 id 返回 nullptr");
    check(find_preset("nonexistent") == nullptr, "不存在的 id 返回 nullptr");
    check(find_preset("ORIGINAL") == nullptr, "id 区分大小写");
    check(preset_by_index(0) != nullptr, "索引 0 有效");
    check(preset_by_index(PRESETS.size() - 1) != nullptr, "末位索引有效");
    check(preset_by_index(PRESETS.size()) == nullptr, "越界索引返回 nullptr");
    check(preset_by_index(static_cast<std::size_t>(-1)) == nullptr,
          "极大索引（size_t -1）返回 nullptr，不越界");
    {
        // 每个预设都必须能按 id 反查到同一对象
        bool ok = true;
        for (std::size_t i = 0; i < PRESETS.size(); ++i) {
            const Preset *p = find_preset(PRESETS[i].id);
            if (p != &PRESETS[i]) {
                ok = false;
                printf("        ★ '%s' 反查结果不一致\n", PRESETS[i].id);
            }
        }
        check(ok, "每个预设都能按 id 反查到自身");
    }

    // ── 5. 「原色」必须是真正的中性 ──
    printf("\n[原色预设的中性性]\n");
    {
        const Preset *p = find_preset("original");
        check(p != nullptr, "'original' 预设存在");
        if (p) {
            const auto &s = p->settings;
            check(s.temperature == NEUTRAL_TEMP, "色温 = 6500K（D65）");
            check(s.saturation  == NEUTRAL_SAT, "饱和度 = 1.0");
            check(s.hue         == NEUTRAL_HUE, "色相 = 0");
            check(s.contrast    == NEUTRAL_CONTRAST, "对比度 = 1.0");
            check(s.gamma       == NEUTRAL_GAMMA, "伽马 = 2.4");
            check(s.luminance   == NEUTRAL_LUMA, "亮度 = 0");
            check(s.range.lo    == NEUTRAL_RANGE_LO, "范围下限 = 0.0");
            check(s.range.hi    == NEUTRAL_RANGE_HI, "范围上限 = 1.0");
            check(p->filter == COMP_NONE, "无单色滤镜");
            check(is_neutral(s, p->filter), "is_neutral() 判定为中性");
        }
    }

    // ── 6. 每个预设都真的会改变画面（除「原色」外）──
    printf("\n[预设有效性: 除原色外都必须改变画面]\n");
    {
        int noop = 0;
        for (const auto &p : PRESETS) {
            if (std::strcmp(p.id, "original") == 0)
                continue;
            if (is_neutral(p.settings, p.filter)) {
                ++noop;
                printf("        ★ 预设 '%s' 与中性值相同，按下去没有效果\n", p.id);
            }
        }
        check(noop == 0, "除「原色」外所有预设都会改变画面");
    }
    {
        // 只有「原色」允许是中性
        int neutral_count = 0;
        for (const auto &p : PRESETS)
            if (is_neutral(p.settings, p.filter)) ++neutral_count;
        check(neutral_count == 1, "中性预设恰好一个（「原色」）");
    }

    // ── 7. 预设之间必须真的不同 ──
    printf("\n[预设区分度: 任意两个都不同]\n");
    {
        int same = 0;
        for (std::size_t i = 0; i < PRESETS.size(); ++i) {
            for (std::size_t j = i + 1; j < PRESETS.size(); ++j) {
                const bool eq = settings_equal(PRESETS[i].settings, PRESETS[j].settings)
                             && PRESETS[i].filter == PRESETS[j].filter;
                if (eq) {
                    ++same;
                    printf("        ★ '%s' 与 '%s' 参数完全相同\n",
                           PRESETS[i].id, PRESETS[j].id);
                }
            }
        }
        check(same == 0, "没有任何两个预设的参数集相同");
    }
    {
        // 名字也不能重复（界面上会分不清）
        std::set<std::string> names;
        bool uniq = true;
        for (const auto &p : PRESETS)
            if (!names.insert(std::string(p.name)).second) {
                uniq = false;
                printf("        ★ 名字重复: '%s'\n", p.name);
            }
        check(uniq, "预设名字互不重复");
    }

    // ── 8. 护眼分级 ──
    printf("\n[护眼分级]\n");
    {
        std::vector<const Preset *> eye;
        for (const auto &p : PRESETS)
            if (p.group == PresetGroup::Eyecare) eye.push_back(&p);

        check(eye.size() >= 3, "护眼预设至少 3 档");
        if (eye.size() >= 2) {
            bool descent = true;
            for (std::size_t i = 1; i < eye.size(); ++i)
                if (eye[i]->settings.temperature >= eye[i-1]->settings.temperature)
                    descent = false;
            check(descent, "色温逐级降低（越靠后越暖）");

            // 相邻两档色温差至少 500K，否则用户看不出区别
            bool gap_ok = true;
            for (std::size_t i = 1; i < eye.size(); ++i) {
                const int diff = static_cast<int>(eye[i-1]->settings.temperature)
                               - static_cast<int>(eye[i]->settings.temperature);
                if (diff < 500) {
                    gap_ok = false;
                    printf("        ★ '%s' 与 '%s' 只差 %dK\n",
                           eye[i-1]->id, eye[i]->id, diff);
                }
            }
            check(gap_ok, "相邻护眼档色温差 ≥500K");
        }
        // 色温都不应高于中性（护眼的前提是降蓝光）
        bool all_warm = true;
        for (auto *p : eye)
            if (p->settings.temperature > NEUTRAL_TEMP) all_warm = false;
        check(all_warm, "所有护眼预设色温不超过 6500K");
    }

    // ── 9. 调光预设 ──
    printf("\n[调光预设]\n");
    {
        std::vector<const Preset *> dim;
        for (const auto &p : PRESETS)
            if (p.group == PresetGroup::Dim) dim.push_back(&p);

        check(dim.size() >= 3, "调光预设至少 3 档");
        {
            bool all = true;
            for (auto *p : dim)
                if (p->settings.range.hi >= 0.999f) {
                    all = false;
                    printf("        ★ '%s' 没有压缩色彩范围\n", p->id);
                }
            check(all, "全部调光预设都通过压缩色彩范围实现");
        }
        {
            // 调光类不应同时动 luminance —— 两处叠加会让亮度难以预期
            bool no_double = true;
            for (auto *p : dim)
                if (p->settings.luminance != 0.0f) no_double = false;
            check(no_double, "调光预设不使用 luminance（避免亮度双重叠加）");
        }
        {
            // 纯降亮度那几档的 range.hi 必须严格递减
            std::vector<float> his;
            for (auto *p : dim)
                if (p->settings.temperature == NEUTRAL_TEMP) his.push_back(p->settings.range.hi);
            bool descent = true;
            for (std::size_t i = 1; i < his.size(); ++i)
                if (his[i] >= his[i-1]) descent = false;
            check(his.size() >= 3 && descent, "纯调光档位亮度严格递减");
        }
    }

    // ── 10. 单色预设 ──
    printf("\n[单色预设]\n");
    {
        const Preset *mg = find_preset("mono_green");
        const Preset *ma = find_preset("mono_amber");
        check(mg && mg->filter == COMP_GREEN, "'mono_green' 使用绿色 filter");
        check(ma && ma->filter == COMP_GREEN, "'mono_amber' 也使用绿色 filter");
        if (mg && ma)
            check(ma->settings.temperature < mg->settings.temperature,
                  "'mono_amber' 色温低于 'mono_green'（因此偏暖）");

        const Preset *mo = find_preset("mono");
        check(mo && mo->settings.saturation == 0.0f, "'mono' 饱和度为 0（真正去色）");

        // 所有用 filter 的预设，饱和度不该同时为 0（否则 filter 无意义）
        bool ok = true;
        for (const auto &p : PRESETS) {
            if (p.filter != COMP_NONE && p.settings.saturation <= 0.001f) {
                ok = false;
                printf("        ★ '%s' 既去色又用 filter，filter 效果会被抵消\n", p.id);
            }
        }
        check(ok, "使用 filter 的预设饱和度不为 0");
    }
    // ── 10b. 分类数与声明一致 ──
    printf("\n[分类数]\n");
    {
        // PRESET_GROUP_COUNT 是 presets.hpp 里的声明值。
        // 加了新分类却忘了改它、或改了却忘了加分类，这里都会失败。
        int used = 0;
        for (std::size_t g = 0; g < PRESET_GROUP_COUNT; ++g) {
            if (count_group(static_cast<PresetGroup>(g)) > 0) ++used;
        }
        printf("        实际使用 %d 个分类，声明 %zu 个\n",
               used, PRESET_GROUP_COUNT);
        check(used == static_cast<int>(PRESET_GROUP_COUNT),
              "所有声明的分类都有预设（没有空分类）");
    }


    // ── 11. 色觉辅助分组的存在性与合理性 ──
    printf("\n[色觉辅助分组]\n");
    {
        const std::size_t n = count_group(PresetGroup::Vision);
        check(n >= 2, "色觉辅助至少 2 个预设");
        // 这组靠色相旋转起效，所以必须有非零 hue 或高饱和
        bool meaningful = true;
        for (const auto &p : PRESETS) {
            if (p.group != PresetGroup::Vision) continue;
            const bool has_hue = std::fabs(p.settings.hue) > 0.05f;
            const bool has_sat = p.settings.saturation > 1.2f ||
                                 p.settings.saturation < 0.9f;
            if (!has_hue && !has_sat) {
                meaningful = false;
                printf("        ★ '%s' 既无显著色相偏移也无饱和度变化\n", p.id);
            }
        }
        check(meaningful, "色觉辅助预设都有色相偏移或饱和度调整");
    }

    // ── 12. 摘要长度（主界面「效果」行的可用宽度很小）──
    printf("\n[摘要长度]\n");
    {
        constexpr std::size_t MAX = 10;
        int bad = 0;
        std::size_t worst = 0;
        std::string worst_s;
        for (const auto &p : PRESETS) {
            const std::string s = settings_summary(p.settings, p.filter);
            const std::size_t n = utf8_length(s);
            if (n > worst) { worst = n; worst_s = s; }
            if (n > MAX) {
                ++bad;
                printf("        ★ '%s' 摘要 %zu 字: \"%s\"\n", p.id, n, s.c_str());
            }
        }
        printf("        最长摘要: \"%s\" (%zu 字)\n", worst_s.c_str(), worst);
        check(bad == 0, "全部摘要 ≤10 字");
    }
    {
        // 极端取值下的摘要也不能超长
        constexpr std::size_t MAX = 10;
        FzSettings hi{};
        hi.temperature = TEMP_MAX; hi.saturation = SAT_MAX; hi.gamma = GAMMA_MAX;
        hi.range = { RANGE_MIN, RANGE_MAX };
        check(utf8_length(settings_summary(hi, COMP_NONE)) <= MAX,
              "取值全为上限时摘要仍 ≤10 字");

        FzSettings lo{};
        lo.temperature = TEMP_MIN; lo.saturation = SAT_MIN;
        lo.range = { RANGE_MIN, RANGE_MAX };
        check(utf8_length(settings_summary(lo, COMP_NONE)) <= MAX,
              "取值全为下限时摘要仍 ≤10 字");
    }

    printf("\n========================================================\n");
    printf("检查项: %d   失败: %d\n", g_checks, g_failures);
    printf("%s\n", g_failures == 0 ? "结果: 全部通过" : "结果: 存在失败");
    return g_failures == 0 ? 0 : 1;
}
