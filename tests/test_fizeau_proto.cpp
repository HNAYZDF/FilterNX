// FilterNX — Fizeau IPC 协议布局测试
//
// 目的: 验证我方结构体与 Fizeau 服务端的期望布局完全一致。
//
// 为什么这是关键测试:
//   Fizeau 的 IPC 用 serviceDispatchIn 把**整个 FizeauProfile 结构体**原样
//   发给服务端。只要有一处字段偏移或大小不同，服务端收到的就是错位数据 ——
//   设置无效还算轻的，写入异常数值可能导致画面异常（例如伽马为负、范围倒置）。
//   这类错误在真机上的表现是"设置没反应"或"画面怪怪的"，极难定位。
//
// ★ 关于预期值的来源
//   本文件里的预期偏移不是照抄文档，而是按 C 语言结构体布局规则从字段声明
//   独立推算出来的：
//
//   FizeauSettings（32 字节）:
//       0  temperature uint32
//       4  saturation  float
//       8  hue         float
//      12  contrast    float
//      16  gamma       float
//      20  luminance   float
//      24  range       ColorRange{float lo, hi}  → 8 字节
//      32  = 结束
//   注意: 第一版我把这里算成 40，误以为 range 之后还有填充。实际上结构体
//   总大小只需满足最宽成员对齐（4），32 已是 4 的倍数，无需尾部填充。
//   这个错误被本测试当场抓出——这正是它存在的意义。
//
//   FizeauProfile（92 字节）:
//       0  day_settings    FizeauSettings (32)
//      32  night_settings  FizeauSettings (32)
//      64  components      Component (4)
//      68  filter          Component (4)
//      72  dusk_begin      Time (4, aligned(4))
//      76  dusk_end        Time (4)
//      80  dawn_begin      Time (4)
//      84  dawn_end        Time (4)
//      88  dimming_timeout Time (4)
//      92  = 结束
//
//   SetProfileRequest（96 字节，对应 fizeau.c 中 fizeauSetProfile 的匿名 struct）:
//       0  id      FizeauProfileId (4)
//       4  profile FizeauProfile (92)
//      96  = 结束

#include <cstdio>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <cmath>
#include <string>

#include "fizeau_proto.h"

using namespace fz;

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

template <typename T>
static void check_size(std::size_t want, const char *name) {
    char buf[96];
    std::snprintf(buf, sizeof(buf), "sizeof(%s) == %zu (实际 %zu)",
                  name, want, sizeof(T));
    check(sizeof(T) == want, buf);
}

// offsetof 的第二个参数必须是编译期成员名，不能用字符串，故用宏
#define CHECK_OFFSET(Type, Member, Want)                                   \
    do {                                                                   \
        char _buf[128];                                                    \
        std::snprintf(_buf, sizeof(_buf),                                  \
                      "offsetof(%s, %s) == %zu (实际 %zu)",                \
                      #Type, #Member, (std::size_t)(Want),                 \
                      offsetof(Type, Member));                             \
        check(offsetof(Type, Member) == (std::size_t)(Want), _buf);         \
    } while (0)

int main() {
    printf("=== Fizeau IPC 协议布局测试 ===\n\n");

    // ── 基础类型 ──
    printf("[基础类型]\n");
    check_size<Temperature>(4, "Temperature");
    check_size<Saturation>(4, "Saturation");
    check_size<Hue>(4, "Hue");
    check_size<Contrast>(4, "Contrast");
    check_size<Gamma>(4, "Gamma");
    check_size<Luminance>(4, "Luminance");
    check_size<ColorRange>(8, "ColorRange");
    check_size<Component>(4, "Component");
    check_size<Time>(4, "Time (aligned(4))");
    check(alignof(Time) == 4, "alignof(Time) == 4");

    // ── FizeauSettings: 32 字节 ──
    printf("\n[FizeauSettings]\n");
    check_size<FizeauSettings>(32, "FizeauSettings");
    CHECK_OFFSET(FizeauSettings, temperature, 0);
    CHECK_OFFSET(FizeauSettings, saturation, 4);
    CHECK_OFFSET(FizeauSettings, hue, 8);
    CHECK_OFFSET(FizeauSettings, contrast, 12);
    CHECK_OFFSET(FizeauSettings, gamma, 16);
    CHECK_OFFSET(FizeauSettings, luminance, 20);
    CHECK_OFFSET(FizeauSettings, range, 24);
    check(alignof(FizeauSettings) == 4, "alignof(FizeauSettings) == 4");

    // ── FizeauProfile: 92 字节 ──
    printf("\n[FizeauProfile]\n");
    check_size<FizeauProfile>(92, "FizeauProfile");
    CHECK_OFFSET(FizeauProfile, day_settings, 0);
    CHECK_OFFSET(FizeauProfile, night_settings, 32);
    CHECK_OFFSET(FizeauProfile, components, 64);
    CHECK_OFFSET(FizeauProfile, filter, 68);
    CHECK_OFFSET(FizeauProfile, dusk_begin, 72);
    CHECK_OFFSET(FizeauProfile, dusk_end, 76);
    CHECK_OFFSET(FizeauProfile, dawn_begin, 80);
    CHECK_OFFSET(FizeauProfile, dawn_end, 84);
    CHECK_OFFSET(FizeauProfile, dimming_timeout, 88);

    // ── SetProfile 请求结构: 96 字节 ──
    printf("\n[SetProfileRequest（fizeauSetProfile 实际发送的内容）]\n");
    check_size<SetProfileRequest>(96, "SetProfileRequest");
    CHECK_OFFSET(SetProfileRequest, id, 0);
    CHECK_OFFSET(SetProfileRequest, profile, 4);

    // ── 枚举值 ──
    printf("\n[命令号（必须与 Fizeau 服务端一致）]\n");
    check(FizeauCommandId_GetIsActive        == 0, "GetIsActive = 0");
    check(FizeauCommandId_SetIsActive        == 1, "SetIsActive = 1");
    check(FizeauCommandId_GetProfile         == 2, "GetProfile = 2");
    check(FizeauCommandId_SetProfile         == 3, "SetProfile = 3");
    check(FizeauCommandId_GetActiveProfileId == 4, "GetActiveProfileId = 4");
    check(FizeauCommandId_SetActiveProfileId == 5, "SetActiveProfileId = 5");

    printf("\n[档位编号]\n");
    check(FizeauProfileId_Profile1 == 0, "Profile1 = 0");
    check(FizeauProfileId_Profile2 == 1, "Profile2 = 1");
    check(FizeauProfileId_Profile3 == 2, "Profile3 = 2");
    check(FizeauProfileId_Profile4 == 3, "Profile4 = 3");
    check(FizeauProfileId_Total    == 4, "Total = 4");

    printf("\n[Component 位掩码]\n");
    check(Component_None  == 0, "None = 0");
    check(Component_Red   == 1, "Red = 1");
    check(Component_Green == 2, "Green = 2");
    check(Component_Blue  == 4, "Blue = 4");
    check(Component_All   == 7, "All = 7");

    // ── 取值边界 ──
    printf("\n[取值范围（越界会被 Fizeau sanitize 静默改写）]\n");
    check(MIN_TEMP == 1000 && MAX_TEMP == 10000, "色温 1000..10000");
    check(MIN_SAT == 0.0f && MAX_SAT == 2.0f, "饱和度 0..2");
    check(MIN_HUE == -1.0f && MAX_HUE == 1.0f, "色相 -1..1");
    check(MIN_CONTRAST == 0.0f && MAX_CONTRAST == 2.0f, "对比度 0..2");
    check(MIN_GAMMA == 0.0f && MAX_GAMMA == 5.0f, "伽马 0..5");
    check(MIN_LUMA == -1.0f && MAX_LUMA == 1.0f, "亮度 -1..1");
    check(MIN_RANGE == 0.0f && MAX_RANGE == 1.0f, "范围 0..1");
    check(MIN_LIMITED_RANGE > 0.0627f && MIN_LIMITED_RANGE < 0.0628f,
          "MIN_LIMITED_RANGE ≈ 16/255");
    check(MAX_LIMITED_RANGE > 0.9215f && MAX_LIMITED_RANGE < 0.9217f,
          "MAX_LIMITED_RANGE ≈ 235/255");

    // ── 端到端：模拟真实发送，逐字段回读 ──
    printf("\n[端到端：构造请求后逐字段回读校验]\n");
    {
        SetProfileRequest req{};
        req.id = FizeauProfileId_Profile1;
        req.profile.day_settings.temperature   = 5000;
        req.profile.day_settings.gamma         = 2.2f;
        req.profile.day_settings.saturation    = 1.35f;
        req.profile.day_settings.range.lo      = 0.0f;
        req.profile.day_settings.range.hi      = 0.45f;
        req.profile.night_settings.temperature = 5100;
        req.profile.night_settings.gamma       = 2.25f;
        req.profile.components = Component_All;
        req.profile.filter     = Component_None;

        const auto *raw = reinterpret_cast<const std::uint8_t *>(&req);

        auto rd_u32 = [&](std::size_t off) {
            std::uint32_t v = 0;
            std::memcpy(&v, raw + off, 4);
            return v;
        };
        auto rd_f32 = [&](std::size_t off) {
            float v = 0;
            std::memcpy(&v, raw + off, 4);
            return v;
        };

        // 位置用真实的 offsetof 计算，而非硬编码数字：
        // 这样即使字段顺序将来变化，测试也会自动跟随并保持语义正确。
        constexpr std::size_t base = offsetof(SetProfileRequest, profile);

        check(rd_u32(offsetof(SetProfileRequest, id)) == 0, "id 位置正确");

        check(rd_u32(base + offsetof(FizeauProfile, day_settings)
                          + offsetof(FizeauSettings, temperature)) == 5000,
              "day_settings.temperature 位置正确");

        check(std::fabs(rd_f32(base + offsetof(FizeauProfile, day_settings)
                                    + offsetof(FizeauSettings, gamma)) - 2.2f) < 1e-5f,
              "day_settings.gamma 位置正确");

        check(std::fabs(rd_f32(base + offsetof(FizeauProfile, day_settings)
                                    + offsetof(FizeauSettings, saturation)) - 1.35f) < 1e-5f,
              "day_settings.saturation 位置正确");

        check(std::fabs(rd_f32(base + offsetof(FizeauProfile, day_settings)
                                    + offsetof(FizeauSettings, range)
                                    + offsetof(ColorRange, hi)) - 0.45f) < 1e-5f,
              "day_settings.range.hi 位置正确");

        check(rd_u32(base + offsetof(FizeauProfile, night_settings)
                          + offsetof(FizeauSettings, temperature)) == 5100,
              "night_settings.temperature 位置正确（值刻意与 day 不同，排除串位）");

        check(rd_u32(base + offsetof(FizeauProfile, components)) == Component_All,
              "components 位置正确");

        check(rd_u32(base + offsetof(FizeauProfile, filter)) == Component_None,
              "filter 位置正确");

        // 区分性检查: components 与 filter 必须落在不同偏移。
        // 否则上面两条可能因数值巧合而"误通过"（第一版就踩过这个陷阱）。
        check(offsetof(FizeauProfile, components) != offsetof(FizeauProfile, filter),
              "components 与 filter 偏移不同（排除巧合通过）");
    }

    printf("\n========================================================\n");
    printf("检查项: %d   失败: %d\n", g_checks, g_failures);
    printf("%s\n", g_failures == 0 ? "结果: 全部通过" : "结果: 存在失败");
    return g_failures == 0 ? 0 : 1;
}
