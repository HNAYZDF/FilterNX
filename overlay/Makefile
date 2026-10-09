#-------------------------------------------------------------------------------
# FilterNX - 大气层游戏滤镜插件（全中文）
#
# overlay/Makefile
#
# 本版本为"稳妥方案"：overlay 只编辑 Fizeau 的配置文件，不驱动任何硬件。
# 因此不再需要与 sysmodule 共享的 shared/ 目录。
#
# 用法（MSYS2 bash）:
#     export DEVKITPRO=/opt/devkitpro
#     make
#
# 产物:
#     FilterNX.ovl  ->  SD:/switch/.overlays/FilterNX.ovl
#
# 依赖:
#     devkitA64 + libnx
#     switch-curl / switch-zlib / switch-minizip / switch-mbedtls
#     libultrahand（已收编在 ../third_party/libultrahand）
#-------------------------------------------------------------------------------

ifeq ($(strip $(DEVKITPRO)),)
$(error "请先设置 DEVKITPRO。在 MSYS2 bash 中执行: export DEVKITPRO=/opt/devkitpro")
endif

# libultrahand 路径。
#
# 必须使用【相对路径】——devkitA64 的 g++ 是 Windows 原生程序：
#   · "/c/Users/..." 这类 MSYS2 虚拟路径依赖 MSYS2 参数转换
#   · 中间带 ".." 的绝对路径在转换后会解析失败
# 相对路径是最稳的形式，前提是 make 在 overlay/ 目录下运行。
LIBULTRAHAND ?= ../third_party/libultrahand

TARGET      := FilterNX
BUILD       := build
OUTPUT      := FilterNX.ovl

OVERLAY_NAME     := FilterNX
UI_OVERRIDE_PATH := /config/$(OVERLAY_NAME)/

#-------------------------------------------------------------------------------
# NACP 里写入的版本号 —— 从 overlay/src/version.hpp 读出（唯一来源），不手抄。
#
# ⚠ 这里曾经硬编码 "1.0.0"。源码升到 3.0.0 之后，菜单读 NACP 的
#   display_version 显示 v1.0.0，而插件界面显示 v3.0.0 —— 正是 version.hpp
#   开头警告的那种自相矛盾（"界面显示一个版本、菜单写着另一个"）。
#   证据: tools/check_version.py 对本 Makefile 产出的 overlay/FilterNX.ovl
#         报 "FAIL display_version = '1.0.0', 期望 '3.0.0'"。
#
# 读法与 package.sh 完全一致（同样是 sed 取 FNX_VERSION），两处不会漂移。
# ⚠ '\#' 的转义不能省 —— make 会把裸 # 当成注释起始，后面的 sed 全部丢失。
#-------------------------------------------------------------------------------
FNX_VERSION := $(shell sed -n 's/^\#define FNX_VERSION "\([^"]*\)".*/\1/p' src/version.hpp | head -1)

#-------------------------------------------------------------------------------
# 源文件
#
# 注意: 必须用相对路径。规则是 $(BUILD)/%.cpp.o: %.cpp，
#       若源文件是绝对路径，目标名会变成 build//c/Users/... 这种非法路径。

SOURCES     := src
SOURCES     += $(LIBULTRAHAND)/common
SOURCES     += $(LIBULTRAHAND)/libultra/source
SOURCES     += $(LIBULTRAHAND)/libtesla/source

INCLUDES    := $(LIBULTRAHAND)/common \
               $(LIBULTRAHAND)/libtesla/include \
               $(LIBULTRAHAND)/libultra/include \
               $(DEVKITPRO)/libnx/include \
               $(DEVKITPRO)/portlibs/switch/include

#-------------------------------------------------------------------------------
# 编译选项

ARCH        := -march=armv8-a+crc+crypto -mtune=cortex-a57 -mtp=soft -fPIE

# UI_OVERRIDE_PATH: 让 /config/FilterNX/ 下的 theme/lang 生效
# INITIALIZE_IN_GUI_DIRECTIVE: 确保在 GUI 目录下也能完成初始化
DEFINES     := -D__SWITCH__ \
               -DUI_OVERRIDE_PATH="\"$(UI_OVERRIDE_PATH)\"" \
               -DINITIALIZE_IN_GUI_DIRECTIVE=1

# EXTRA_DEFINES: 命令行追加宏，**不覆盖**上面的 DEFINES。
#
# 为什么单独开一个变量而不是让调用方直接传 DEFINES=...:
#   那样会把 __SWITCH__ / UI_OVERRIDE_PATH / INITIALIZE_IN_GUI_DIRECTIVE
#   一起覆盖掉，构建会以奇怪的方式失败或产出行为不同的产物。
#   追加式传参才是对的。
#
# 用途: 构建诊断版
#   make EXTRA_DEFINES='-DFNX_NO_FIZEAU'
EXTRA_DEFINES ?=

CXXFLAGS    := -std=gnu++23 -fno-rtti -fno-exceptions -fno-non-call-exceptions \
               -fno-threadsafe-statics -fno-use-cxa-atexit \
               -fno-asynchronous-unwind-tables -fno-unwind-tables

CFLAGS      := -std=gnu17

WARNFLAGS   := -Wall -Wno-unused-parameter
OPTFLAGS    := -O3 -ffunction-sections -fdata-sections -fno-strict-aliasing \
               -frename-registers -falign-functions=16

LDFLAGS     := -specs=$(DEVKITPRO)/libnx/switch.specs $(ARCH) \
               -Wl,--gc-sections -Wl,--as-needed -Wl,-Map,$(BUILD)/$(TARGET).map

LIBDIRS     := -L$(DEVKITPRO)/libnx/lib -L$(DEVKITPRO)/portlibs/switch/lib
LIBS        := -lcurl -lz -lminizip -lmbedtls -lmbedx509 -lmbedcrypto -lnx

PREFIX      := aarch64-none-elf-
CC          := $(PREFIX)gcc
CXX         := $(PREFIX)g++
LD          := $(PREFIX)g++

export PATH := $(DEVKITPRO)/tools/bin:$(DEVKITPRO)/devkitA64/bin:$(PATH)

#-------------------------------------------------------------------------------

CFILES      := $(shell find $(SOURCES) -name '*.c' 2>/dev/null)
CPPFILES    := $(shell find $(SOURCES) -name '*.cpp' 2>/dev/null)

OFILES      := $(CFILES:%=$(BUILD)/%.o) $(CPPFILES:%=$(BUILD)/%.o)
DFILES      := $(OFILES:.o=.d)

ELF         := $(BUILD)/$(TARGET).elf
NACP        := $(BUILD)/$(TARGET).nacp

.PHONY: all clean check-libultrahand

all: check-libultrahand $(OUTPUT)
	@echo ""
	@echo "构建完成:"
	@echo "  $(OUTPUT)  -> SD:/switch/.overlays/$(OUTPUT)"

check-libultrahand:
	@if [ ! -d "$(LIBULTRAHAND)/libtesla/source" ]; then \
		echo "错误: 找不到 libultrahand: $(LIBULTRAHAND)"; \
		exit 1; \
	fi

$(BUILD)/%.c.o: %.c
	@echo " CC   $<"
	@mkdir -p $(dir $@)
	@$(CC) -MMD -MP $(ARCH) $(OPTFLAGS) $(WARNFLAGS) $(CFLAGS) $(DEFINES) $(EXTRA_DEFINES) $(addprefix -I,$(INCLUDES)) -c $< -o $@

$(BUILD)/%.cpp.o: %.cpp
	@echo " CXX  $<"
	@mkdir -p $(dir $@)
	@$(CXX) -MMD -MP $(ARCH) $(OPTFLAGS) $(WARNFLAGS) $(CXXFLAGS) $(DEFINES) $(EXTRA_DEFINES) $(addprefix -I,$(INCLUDES)) -c $< -o $@

$(ELF): $(OFILES)
	@echo " LD   $@"
	@mkdir -p $(dir $@)
	@$(LD) $(LDFLAGS) $(LIBDIRS) $(OFILES) $(LIBS) -o $@
	@aarch64-none-elf-size $@

# ⚠ 依赖声明不能省: 没有先决条件时，make 认定"文件已存在 = 已是最新"，
#   version.hpp 改了也不会重新生成 .nacp —— 于是菜单里永远显示旧版本号。
#   本文件历史上把版本硬编码成 "1.0.0"，正是靠这个"永不过期"的规则，
#   在源码升到 3.0.0 之后还继续把一个 1.0.0 的 NACP 打进产物里。
#   证据: 改掉硬编码后重跑 make，.nacp 仍不更新；rm 掉重跑才变成 3.0.0。
#   ⚠ 依赖写成字面量 src/version.hpp: 不能用 $(SOURCES)/version.hpp，
#   SOURCES 是"src + 三个 libultrahand 子目录"的列表，展开后 make 会去找
#   ../third_party/libultrahand/libtesla/source/version.hpp 并报"没有规则"。
$(NACP): src/version.hpp
	@echo " NACP $@ (display_version=$(FNX_VERSION))"
	@if [ -z "$(FNX_VERSION)" ]; then \
		echo "错误: 无法从 src/version.hpp 读出版本号 —— 拒绝用错误版本生成 NACP"; \
		exit 1; \
	fi
	@mkdir -p $(dir $@)
	@nacptool --create "$(OVERLAY_NAME)" "$(OVERLAY_NAME)" "$(FNX_VERSION)" $@

# ULTR 签名: libultrahand 靠它识别"这是本框架编译的 overlay"，
# 从而在 Ultrahand 菜单里获得一等公民待遇。必须追加在文件末尾。
$(OUTPUT): $(ELF) $(NACP)
	@echo " NRO  $@"
	@elf2nro $(ELF) $@ --icon=$(DEVKITPRO)/libnx/default_icon.jpg --nacp=$(NACP)
	@printf 'ULTR' >> $@
	@echo " 已追加 ULTR 签名"

clean:
	@echo "清理..."
	@rm -rf $(BUILD) $(OUTPUT)

-include $(DFILES)
