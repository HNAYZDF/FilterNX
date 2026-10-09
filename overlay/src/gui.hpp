/*
 * 超能滤镜 (Chaoneng / FilterNX) — 大气层游戏滤镜插件（全中文）
 *
 * gui.hpp — 界面声明
 *
 * 页面结构:
 *   MainGui   主页面 — 当前状态 + 操作入口
 *   PresetGui 预设页 — 30 个中文滤镜，A 键即时应用
 *   InfoGui   信息页 — 作者与联系方式
 *
 * 布局常量与高度预算放在 layout.hpp —— 那份不依赖 <tesla.hpp>，
 * 因此主机侧测试可以引用同一份定义来校验行数预算，
 * 而不必抄一份数字（抄的话测试就失去意义了）。
 *
 * GPLv2，详见 LICENSE。
 */

#pragma once

#include <tesla.hpp>

#include "layout.hpp"

namespace fnx::ui {

class MainGui : public tsl::Gui {
    public:
        tsl::elm::Element *createUI() override;
        void update() override;
};

class PresetGui : public tsl::Gui {
    public:
        /*
         * 析构 —— 负责结束「实时预览」会话，把设置恢复到进来之前。
         *
         * ⚠ 必须存在:
         *   展开/收起分类用 swapTo 替换栈顶，旧页面会**立即析构**；
         *   按 B 返回主页面时同样析构。两种"离开"都由它统一收尾，
         *   所以它是本页唯一的可靠收尾点。
         *
         * 用户按过 A 确认的话，commit_preview() 已把会话置为结束，
         * 这里就是空操作 —— 那是「我就要这个滤镜」，不该被撤销。
         */
        ~PresetGui() override;

        tsl::elm::Element *createUI() override;
        void update() override;

        // 用来判断「用户是否真的移动了光标」——
        // 实时预览只应在用户移动时触发，而不是框架自动聚焦时。
        // 详见 gui.cpp 里 g_userNavigated 的说明。
        bool handleInput(u64 keysDown, u64 keysHeld,
                         const HidTouchState &touchPos,
                         const HidAnalogStickState leftJoyStick,
                         const HidAnalogStickState rightJoyStick) override;
};

/*
 * InfoGui — 关于 / 联系方式页
 *
 * 为什么单独一页而不是塞进主页面:
 *   ListItem 的"值"列只有约 5 个字的显示宽度（超过会把名字挤掉，
 *   详见 presets.hpp 的说明）。QQ 群号是长数字串，放不进主页面那一行。
 *   独立一页没有这个约束，也能容纳更多说明文字。
 */
class InfoGui : public tsl::Gui {
    public:
        tsl::elm::Element *createUI() override;
        void update() override;
};


} // namespace fnx::ui

namespace fnx {
// 显式类型别名。
//
// 为什么不直接在 main.cpp 里写 ui::MainGui:
//   main.cpp 处于匿名命名空间中，且使用了 using namespace fnx。
//   此时 `ui::MainGui` 的限定名查找会先在匿名命名空间找 ui，
//   再退到 fnx::ui —— 但模板实参位置的查找规则更严格，会报
//   "parse error in template argument list"。
//   用命名空间级别的别名可以完全避免这个歧义。
using MainGuiType = ::fnx::ui::MainGui;
} // namespace fnx
