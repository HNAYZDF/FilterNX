/*
 * nacp_offsets.c — 复刻 NACP 结构，用编译器算出精确字段偏移
 *
 * 目的: 不再手算偏移。之前把 display_version 误当成 0x3000
 *       （那其实是 isbn），导致版本写到了错误的字段。
 *
 * 结构定义严格照抄 libnx 的 switch/nacp.h:
 *     typedef struct { char name[0x200]; char author[0x100]; } NacpLanguageEntry;
 *     ... ApplicationControlProperty 的字段顺序依次照抄 ...
 */
#include <stdio.h>
#include <stddef.h>
#include <stdint.h>

typedef struct {
    char name[0x200];
    char author[0x100];
} NacpLanguageEntry;

typedef union {
    NacpLanguageEntry lang[16];
    struct {
        uint16_t buffer_size;
        uint8_t  buffer[0x2FFE];
    } compressed_data;
} NacpLanguageEntryData;

/* ApplicationControlProperty 的前半部分（到 display_version 为止） */
typedef struct {
    NacpLanguageEntryData lang_data;
    uint8_t  isbn[0x25];
    uint8_t  startup_user_account;
    uint8_t  user_account_switch_lock;
    uint8_t  add_on_content_registration_type;
    uint32_t attribute_flag;
    uint32_t supported_language_flag;
    uint32_t parental_control_flag;
    uint8_t  screenshot;
    uint8_t  video_capture;
    uint8_t  data_loss_confirmation;
    uint8_t  play_log_policy;
    uint64_t presence_group_id;
    int8_t   rating_age[0x20];
    char     display_version[0x10];
} NacpPrefix;

int main(void) {
    printf("=== NACP 字段偏移（由编译器计算）===\n\n");
    printf("  sizeof(NacpLanguageEntry)        = 0x%04zX  (%zu)\n",
           sizeof(NacpLanguageEntry), sizeof(NacpLanguageEntry));
    printf("  sizeof(lang_data)                = 0x%04zX  (%zu)\n",
           sizeof(NacpLanguageEntryData), sizeof(NacpLanguageEntryData));
    printf("\n");
    printf("  lang[N].name                     = N + 0x%03zX\n", offsetof(NacpLanguageEntry, name));
    printf("  lang[N].author                   = N + 0x%03zX\n", offsetof(NacpLanguageEntry, author));
    printf("  lang[0].name                     = 0x%04zX\n", offsetof(NacpPrefix, lang_data.lang[0].name));
    printf("  lang[0].author                   = 0x%04zX\n", offsetof(NacpPrefix, lang_data.lang[0].author));
    printf("  lang[1].name                     = 0x%04zX\n", offsetof(NacpPrefix, lang_data.lang[1].name));
    printf("  lang[14].name  (SimplifiedCN)    = 0x%04zX\n", offsetof(NacpPrefix, lang_data.lang[14].name));
    printf("\n");
    printf("  isbn                             = 0x%04zX   <-- 之前误把版本写到这里\n",
           offsetof(NacpPrefix, isbn));
    printf("  display_version                  = 0x%04zX   <-- 真正的版本位置\n",
           offsetof(NacpPrefix, display_version));
    printf("\n");
    printf("  结论: display_version 在 0x%zX，不是 0x3000\n",
           offsetof(NacpPrefix, display_version));
    return 0;
}
