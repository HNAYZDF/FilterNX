/*
 * fnx_group_list.hpp — 可折叠的分类分组（下拉式）
 *
 * ═══════════════════════════════════════════════════════════════════════════
 * 为什么需要
 * ═══════════════════════════════════════════════════════════════════════════
 * 滤镜增加到 100 个后，平铺列表要滚很久才能找到想要的那一类。
 * 改成「分类可折叠」后:
 *
 *     未展开:  只看得到 11 个分类行 —— 一屏放得下
 *     展开后:  该类下的滤镜出现在分类行下方，再按 A 收起
 *
 * ═══════════════════════════════════════════════════════════════════════════
 * ⚠ 实现方式: 点击后**重建整个页面**，而不是动态增删列表项
 * ═══════════════════════════════════════════════════════════════════════════
 * 第一版用 `List::addItem(el, 0, index)` / `removeItem(el)` 在点击回调里
 * 动态增删子项。真机结果是**按 A 就蓝屏**。
 *
 * 原因: List 的增删是"按帧惰性生效"的（m_itemsToAdd / m_itemsToRemove），
 * 而点击回调发生在输入处理阶段、列表正处于遍历状态。在遍历中改变它的
 * 待处理队列，与 `requestFocus`（在有待处理项时**返回 nullptr**）、
 * 索引重算、滚动位置修正相互纠缠 —— 这类交互框架内部没有承诺安全。
 *
 * 现在的做法简单得多:
 *
 *     按下 A  →  切换该分类的展开状态  →  tsl::changeTo<PresetGui>()
 *
 * `changeTo` 会重新调 createUI()，按新的展开状态**从头构建**列表。
 * 配合一个**静态的展开状态表**（跨重建保留），用户看到的效果完全一样，
 * 但不再有任何"在遍历中改列表"的操作。
 *
 * ⚠ 为什么这里用 changeTo 是安全的，而 update() 里不行:
 *   · 这里在**按钮回调**里 —— 用户明确操作之后，一帧只发生一次
 *   · update() 里是**每帧**都跑 —— 状态抖动时会变成无限重建
 *   项目早期在 update() 里用过 changeTo，那才是危险用法（已由检查器禁止）。
 *
 * GPLv2，详见 LICENSE。
 */

#pragma once

#include <tesla.hpp>

#include <cstddef>
#include <functional>
#include <string>

namespace fnx::ui {

/*
 * 哪些分类处于展开状态 —— **跨页面重建保留**。
 *
 * 必须是静态的: changeTo 每次都会重新执行 createUI()，
 * 若状态存在栈上，展开后立刻会被重置回收起，用户看不到效果。
 *
 * 用位掩码而不是 vector<bool>: 分类数固定（≤32），无堆分配、无生命周期问题。
 */
inline unsigned g_expandedGroups = 0;

inline bool groupExpanded(std::size_t index) {
    return (g_expandedGroups >> index) & 1u;
}

inline void setGroupExpanded(std::size_t index, bool on) {
    if (on)
        g_expandedGroups |= (1u << index);
    else
        g_expandedGroups &= ~(1u << index);
}

class GroupHeaderItem : public tsl::elm::ListItem {
public:
    /*
     * label    —— 显示在名字列（如「风格」）
     * count    —— 该分类的项数
     * index    —— 分类序号（用于读/写展开状态）
     * onToggle —— 按下 A 时调用；调用方负责重建页面
     */
    GroupHeaderItem(const std::string &label,
                    std::size_t count,
                    std::size_t index,
                    std::function<void()> onToggle,
                    std::function<void()> onFocus = nullptr)
        : tsl::elm::ListItem(label, ""),
          m_label(label),
          m_count(count),
          m_index(index),
          m_onToggle(std::move(onToggle)),
          m_onFocus(std::move(onFocus)) {
        // 从静态状态表读初始展开态，而不是默认 false ——
        // 这样 changeTo 重建后仍保持用户上次的展开情况
        m_expanded = groupExpanded(m_index);
        refreshLabel();
    }

    /*
     * 焦点变化时上报 —— 调用方据此记住"光标在哪一行"，
     * 以便页面重建后恢复（否则会跳回列表最上面）。
     *
     * ⚠ 只上报"获得焦点"，不上报失焦 —— 失焦时调用方无需动作。
     */
    void setFocused(bool focused) override {
        tsl::elm::ListItem::setFocused(focused);
        if (focused && m_onFocus)
            m_onFocus();
    }

    bool expanded() const { return m_expanded; }

    void installClickListener() {
        setClickListener([this](u64 keys) -> bool {
            if (!(keys & HidNpadButton_A))
                return false;

            // 只切状态，界面重建交给调用方 ——
            // 本类不碰 List，避免任何"遍历中改列表"的风险
            m_expanded = !m_expanded;
            setGroupExpanded(m_index, m_expanded);
            refreshLabel();

            if (m_onToggle)
                m_onToggle();
            return true;
        });
    }

private:
    /*
     * 标签形如「▸ 风格(20)」——
     *   ▸ 收起 / ▾ 展开，一眼能看出可点
     *   数字用**半角括号**，避免全角括号占太宽
     *
     * ⚠ 长度核算（决定会不会被截断）:
     *     ▸(全角1) + 空格 + 名字(≤4全角) + (20)(4半角)
     *     ≈ 23 + 12 + 4*23 + 4*12 = 175px
     *   可用宽度 >300px，安全。
     *   最长的分组名是「色觉辅助」(4 字)，正好在约束内。
     */
    void refreshLabel() {
        // ⚠ 符号必须选**确认能显示**的码位 —— 这是踩过的坑。
        //
        //   第一版用 U+25B8 / U+25BE（▸ ▾），真机显示成缺字方块 □。
        //   排查方法: 扫卡上所有**已经在真机正常跑**的 overlay，
        //   看它们用了哪些非 ASCII 码位 —— 用过就说明字体里有字形。
        //
        //   结果:
        //     U+25B6 ▶   ✓ FPSLocker.ovl 在用
        //     U+25CF ●   ✓ 11 个 overlay 在用
        //     U+25A0 ■   ✓ StatusMonitor.ovl 在用
        //     U+25B8 ▸   ✗ 没有任何 overlay 用 → 我用的就是它，所以显示方块
        //     U+25BE ▾   ✗ 同上
        //
        //   ▼ (U+25BC) 与 ■(U+25A0) ●(U+25CF) 同属「几何图形」区段，
        //   是 ▶ 的天然配对，取它作为展开态。
        setText(std::string(m_expanded ? "\u25BC " : "\u25B6 ") + m_label +
                "(" + std::to_string(m_count) + ")");
    }

    std::string           m_label;
    std::size_t           m_count;
    std::size_t           m_index;
    bool                  m_expanded = false;
    std::function<void()> m_onToggle;
    std::function<void()> m_onFocus;
};

} // namespace fnx::ui
