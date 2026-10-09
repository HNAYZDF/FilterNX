/*
 * FilterNX — 大气层中文滤镜插件（全中文）
 *
 * main.cpp — overlay 入口
 *
 * ═══════════════════════════════════════════════════════════════════════════
 * 本版的工作方式
 * ═══════════════════════════════════════════════════════════════════════════
 * 插件本身不驱动任何硬件。它通过 IPC 把色彩设置交给机器上常驻的 Fizeau
 * sysmodule，由后者写入 Tegra CMU。这样:
 *
 *   · 不需要自带 sysmodule      → 没有内核能力校验、没有开机加载风险
 *   · 不需要直接访问硬件        → 没有崩溃风险
 *   · 走 IPC 而非写配置文件     → 按下即生效，不需要重启
 *   · 复用已验证可工作的驱动层  → 不与已有插件冲突
 *
 * ═══════════════════════════════════════════════════════════════════════════
 * ⚠ 关于「Fizeau 未运行时菜单崩掉」这个顽固问题
 * ═══════════════════════════════════════════════════════════════════════════
 * 现状: 真机确认 —— Fizeau 没开后台时打开本插件，**整个特斯拉菜单消失**。
 *       反复试过多种方案都没根治，而每次修改都要用户重新装卡、重启、复现，
 *       代价太高。所以这一版换了策略，不再靠猜:
 *
 *   1. **把连接挪出 initServices()**
 *      initServices 是 overlay 生命周期的**最脆弱位置** —— 加载器刚完成
 *      解包与重定位就调用它，此刻任何失败都可能带走整个菜单进程。
 *      现在这里只写一行日志，不做任何 IPC。
 *
 *   2. **加逐步日志 —— 本次最重要的改动**
 *      每一步都写进 SD 卡。若再崩，**日志最后一行就是崩溃前最后执行到的
 *      地方**，不用再猜。
 *      路径: sdmc:/config/超能滤镜/日志.txt
 *
 *   3. **先建界面，再尝试连接**
 *      万一"连接"这个动作本身会让进程死掉，此时界面已经在屏幕上了，
 *      而且日志会留下对应那一行 —— 下次就能确认是它。
 *
 * GPLv2，详见 LICENSE。
 */

#define TESLA_INIT_IMPL
#include <tesla.hpp>

#include "fnx_log.hpp"
#include "gui.hpp"
#include "fizeau_ipc.hpp"

namespace {

class FilterNXOverlay : public tsl::Overlay {
    public:
        virtual void initServices() override {
            // ═══════════════════════════════════════════════════════════
            // ⚠ 这里**故意只写日志，不做任何 IPC**
            // ═══════════════════════════════════════════════════════════
            // initServices 是 overlay 生命周期里最脆弱的位置: 加载器刚完成
            // 解包与重定位就调用它，此刻任何失败都可能带走整个菜单进程。
            //
            // 曾经这里调 fzInitialize()（内部是 smGetService）。Fizeau 没
            // 运行时，真机表现为**整个特斯拉菜单消失**。
            //
            // 连接已挪到 MainGui::createUI()，并且**放在界面构建之后**。
            // 这样即便连接出问题，界面也已经存在，最坏是显示"未连接"，
            // 而不是整个菜单消失。
            // ═══════════════════════════════════════════════════════════
            fnx::fnxLog("[main] initServices 进入（本阶段不做任何 IPC）");
        }

        virtual void exitServices() override {
            fnx::fnxLog("[main] exitServices 进入");
            // fzExit() 内部只在会话有效时才 serviceClose，
            // 未连接时是空操作，可安全调用。
            fnx::fzExit();
            fnx::fnxLog("[main] exitServices 完成");
        }

        virtual std::unique_ptr<tsl::Gui> loadInitialGui() override {
            fnx::fnxLog("[main] loadInitialGui 进入");
            // 用命名空间级别的类型别名，避免匿名命名空间 +
            // using namespace 造成的模板实参查找歧义
            auto gui = initially<fnx::MainGuiType>();
            fnx::fnxLog("[main] loadInitialGui 完成");
            return gui;
        }
};

} // namespace

int main(int argc, char **argv) {
    fnx::fnxLog("──────── 超能滤镜启动 ────────");
    const int rc = tsl::loop<FilterNXOverlay>(argc, argv);
    fnx::fnxLog("[main] tsl::loop 返回（正常退出）");
    return rc;
}
