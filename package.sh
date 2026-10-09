#!/usr/bin/env bash
# 超能滤镜 (FilterNX) — 打包
#
# ═══════════════════════════════════════════════════════════════════════════
# 关于"名字"和"版本号"分别存在哪里（踩过坑，记下来）
# ═══════════════════════════════════════════════════════════════════════════
# Tesla/Ultrahand 菜单里显示的 overlay 名字来自**文件名**，不是 NACP:
#
#     tesla.hpp  setNextOverlay():
#         nextOverlayName = ult::getNameFromPath(ovlPath);   // ← 文件名
#     overlays.ini 以文件名作段名:  [FilterNX.ovl]
#
#   库的运行时代码**从不读取 NACP**（只在 Makefile 注释里出现）。
#   所以改名必须靠**改文件名** —— 早先只改 NACP 是无效的。
#
# 版本号则写在两处（用户直接可见的那处最重要）:
#   1. 插件界面的标题栏  ← 来自 overlay/src/version.hpp，本脚本从中读出版本
#   2. NACP 的 version 字段 ← 本脚本写入，保持元数据正确
#
# 版本号的唯一来源是 overlay/src/version.hpp，本脚本用 sed 读取，
# 避免手抄导致"界面显示 6.0.0 但 zip 叫 5.0.0"这种自相矛盾。
# ═══════════════════════════════════════════════════════════════════════════
set -e

ROOT=/c/Users/hnayz/Documents/deepseek-harness/default-workspace/filternx
DIST=$ROOT/dist
PY=/c/Users/hnayz/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/python/python.exe

# ⚠ 文件名必须是**纯 ASCII**
#
# 踩过的坑: 试过把文件命名成「超能滤镜.ovl」，结果大气层/Ultrahand 完全
# 无法识别这个 overlay —— 根本没出现在列表里。中文（非 ASCII）文件名
# 在这条链路上不被支持。
#
# 正确做法是把"显示名"和"文件名"分开:
#   DISPLAY_NAME → 写进 NACP，菜单里显示的就是它（可以是中文）
#   FILE_STEM    → 实际文件名，纯 ASCII
#
# 早期我还误判过"名字来自文件名"，那也不对 —— Ultrahand 的
# source/utils.hpp:953 getOverlayInfo() 读的是 NACP 的 lang[0].name。
DISPLAY_NAME='超能滤镜'
FILE_STEM='Chaoneng'
OUT_NAME="$FILE_STEM.ovl"

SRC="$ROOT/overlay/FilterNX.ovl"
VER_HPP="$ROOT/overlay/src/version.hpp"

if [ ! -f "$SRC" ]; then
    echo "错误: 找不到 $SRC（请先构建 overlay）"
    exit 1
fi

# ── 从 version.hpp 读出版本号（唯一来源）──
VERSION=$(sed -n 's/^#define FNX_VERSION "\([^"]*\)".*/\1/p' "$VER_HPP" | head -1)
if [ -z "$VERSION" ]; then
    echo "错误: 无法从 $VER_HPP 读出版本号"
    exit 1
fi
echo "版本号（来自 version.hpp）: $VERSION"

rm -rf "$DIST"
mkdir -p "$DIST/switch/.overlays"

# ── 1. 复制到目标文件名 ──
# 文件名就是菜单显示名，这一步决定了 Tesla 里看到什么名字。
DST="$DIST/switch/.overlays/$OUT_NAME"
cp "$SRC" "$DST"

# ── 2. 写入 NACP 应用名与版本（UTF-8）──
# 名字虽不用于菜单显示，仍要写对 —— NACP 是标准应用元数据，别的工具会读。
echo
"$PY" "$ROOT/tools/set_nacp.py" "$DST" "$DISPLAY_NAME" "$VERSION"
echo

# ── 3. 格式校验: 避免发出无法加载的文件 ──
# nx-ovlloader 在偏移 0x10 处检查 "NRO0" 魔数，不通过就 fatalThrow，
# 表现为整个 Tesla 菜单崩溃。
NRO_MAGIC_HEX=$(dd if="$DST" bs=1 skip=16 count=4 2>/dev/null | od -An -tx1 | tr -d ' \n')
if [ "$NRO_MAGIC_HEX" != "4e524f30" ]; then
    echo "错误: 偏移 0x10 处应为 NRO0 (4e524f30)，实际为 '$NRO_MAGIC_HEX'"
    exit 1
fi
echo "overlay 格式校验通过 (0x10 处为 NRO0)"

TAIL=$(tail -c 4 "$DST")
if [ "$TAIL" != "ULTR" ]; then
    echo "错误: 末尾缺少 ULTR 签名"
    exit 1
fi
echo "ULTR 签名校验通过"

# ── 4. 回读 NACP 确认写对了 ──
echo
# 回读校验: 确认 NACP 里的名字与版本真的写对了（菜单显示的就是这两个字段）
"$PY" "$ROOT/tools/check_version.py" "$DST"
echo "  （菜单显示名与版本都取自 NACP；文件名只用于分发识别）"

# ── 5. 文档 ──
#
# ⚠ 面向使用者的说明书**不再直接用 README.md**。
#   README 是仓库首页，里面混着 NACP 字段偏移、源码行号、构建链路这类
#   开发内容 —— 群友打开说明书看到的第一屏却是源码偏移表。
#   现在拆开:
#       安装说明.md  → 进分发目录（用户看的）
#       开发说明.md  → 也进分发目录（少数想自己编译的人需要它）
#       README.md    → 只留在仓库，作为仓库首页
if [ ! -f "$ROOT/安装说明.md" ]; then
    echo "错误: 找不到 $ROOT/安装说明.md"
    exit 1
fi
cp "$ROOT/安装说明.md" "$DIST/安装说明.md"
cp "$ROOT/开发说明.md" "$DIST/开发说明.md"
cp "$ROOT/CHANGELOG.md" "$DIST/更新日志.md"
cp "$ROOT/LICENSE"     "$DIST/LICENSE"

echo
echo "分发目录已生成: $DIST"
echo
find "$DIST" -type f | sed "s|$DIST|dist|" | sort
echo
echo "分发文件名          : $OUT_NAME"
echo "界面显示版本            : v$VERSION"
echo "文件总数: $(find "$DIST" -type f | wc -l)"
echo "总体积:   $(du -sh "$DIST" | cut -f1)"
