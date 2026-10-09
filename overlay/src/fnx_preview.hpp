/*
 * fnx_preview.hpp — 光标悬停即时预览（实时效果预览）
 *
 * ═══════════════════════════════════════════════════════════════════════════
 * 效果
 * ═══════════════════════════════════════════════════════════════════════════
 * 在「选择滤镜」页里用方向键上下移动光标，**移到哪个滤镜就把哪个应用上去** ——
 * 特斯拉 overlay 是半透明的，游戏画面在底下透出来，所以能立刻看到效果。
 *
 *     上/下移动  →  画面实时变化（预览）
 *     按 A       →  确认这个滤镜
 *     按 B 返回  →  自动恢复进来之前的那套设置
 *
 * ═══════════════════════════════════════════════════════════════════════════
 * 为什么能这样做
 * ═══════════════════════════════════════════════════════════════════════════
 *   · Tesla overlay 是**覆盖层**，不是独占画面 —— 游戏/系统界面在它下面
 *     照常渲染，Fizeau 的滤镜作用于合成后的画面，所以预览立刻可见。
 *   · `tsl::elm::Element::setFocused(bool)` 是**虚函数**，`List` 在移动
 *     焦点时会调用它（tesla.hpp:5844 / 5926 / 5966）。
 *     重写它就有了 onFocus 钩子 —— 不需要轮询、不需要比较下标。
 *
 * ⚠ 不用"每帧比较 m_focusedIndex"的写法:
 *     那要在 update() 里做，而 update() 是每帧跑的 —— 一旦在里面触发
 *     任何重建或写入，就会变成帧率相关的间歇性故障。setFocused 是
 *     事件驱动的，一次移动只触发一次，语义也清楚得多。
 *
 * ═══════════════════════════════════════════════════════════════════════════
 * 恢复原设置: 靠 ~Gui() 析构
 * ═══════════════════════════════════════════════════════════════════════════
 * 进入页面时把当前 profile 存一份，离开页面时（Gui 被 delete）写回。
 * 这样"按 B 返回"和"按 A 确认后返回主页面"都会恢复 ——
 * 除非用户在页面里按了 A 确认（那时保留所选滤镜）。
 *
 * GPLv2，详见 LICENSE。
 */

#pragma once

#include <tesla.hpp>

#include <cstdint>
#include <functional>

namespace fnx::ui {

/*
 * 焦点变化时回调的列表项。
 *
 * 只加一个钩子，其余行为完全沿用 ListItem —— 渲染、点击、滚动都不碰。
 */
class PreviewListItem : public tsl::elm::ListItem {
public:
    PreviewListItem(const std::string &text,
                    const std::string &value,
                    bool isMini,
                    std::function<void()> onFocus)
        : tsl::elm::ListItem(text, value, isMini),
          m_onFocus(std::move(onFocus)) {}

    ~PreviewListItem() override = default;

    void setFocused(bool focused) override {
        // 先让父类完成它该做的（高亮状态、点击动画重置）
        tsl::elm::ListItem::setFocused(focused);

        // 只在「获得焦点」时触发预览 —— 失焦不动画面，
        // 否则移出这一项会先闪一下再被下一项覆盖
        if (focused && m_onFocus)
            m_onFocus();
    }

private:
    std::function<void()> m_onFocus;
};

} // namespace fnx::ui
