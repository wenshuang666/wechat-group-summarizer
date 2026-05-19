# WeChat Group Summarizer

> 微信数据库读取 + 消息总结工具，需要有自己的Agent，以GA为例子： [GenericAgent](https://github.com/lsdefine/GenericAgent#chinese) 。前置需求是成功配置agent，并连接微信clawbot。这里不多赘述。

## 快速开始

```bash
# 1. 克隆项目到 GA 的 temp 目录
git clone https://github.com/wenshuang666/wechat-group-summarizer.git

# 2. 让 GA 自动配置
# 对 GA 说："请按照 ga_sop/wechat_summary_setup.md 帮我配置微信消息总结"
```

GA 会自动完成：路径发现 → 密钥提取 → 依赖安装 → 测试连接。

## 项目结构

```
wechat-group-summarizer/
├── wechat_db_reader.py          # 核心：微信数据库读取
├── wechat_media_extractor.py    # 媒体提取（图片 OCR、文档解析）
├── requirements.txt             # 依赖
├── ga_sop/
│   └── wechat_summary_setup.md  # GA 自动配置 SOP
└── README.md                    # 本文件
```

## 核心功能

- **自动发现群聊**：无需手动配置 `group_map.json`，自动扫描所有 `Msg_*` 表
- **zstd 解压**：解析微信消息内容的压缩格式
- **媒体提取**：图片 OCR（rapidocr）、文档解析（docx/pdf/md/txt）
- **灵活配置**：通过环境变量或参数传入路径和密钥

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `WECHAT_DB_DIR` | 微信 db_storage 根目录 | `PLEASE_SET_YOUR_DB_DIR` |
| `WECHAT_KEYS_FILE` | 密钥 JSON 文件路径 | `./wechat_keys.json` |
| `WECHAT_GROUP_MAP` | 群聊映射文件路径（可选） | `./group_map.json` |

## 使用示例

```python
from wechat_db_reader import WeChatDBReader

reader = WeChatDBReader()

# 发现所有群聊
groups = reader.list_groups()
print(groups)

# 读取消息（支持模糊匹配群名）
msgs = reader.get_group_messages("GenericAgent", limit=100)
for m in msgs:
    print(f"[{m['time']}] {m['sender_name']}: {m['content']}")

reader.close()
```

## 依赖

- `sqlcipher3` - 加密数据库连接
- `zstandard` - zstd 解压
- `rapidocr_onnxruntime` - 图片 OCR（可选）
- `python-docx` - Word 文档解析（可选）
- `pymupdf` - PDF 解析（可选）

## 致谢

本项目的设计和实现离不开 **[GenericAgent](https://github.com/lsdefine/GenericAgent#chinese)** 框架的支持。GA 的自主执行能力（进程内存扫描、文件系统自动发现、代码自动执行）让普通用户无需手动配置即可享受微信消息总结功能。感谢 GA 团队和所有开源贡献者！

## 免责声明

本项目仅供学习研究使用。使用本项目需遵守相关法律法规和微信用户协议。开发者不对任何滥用行为负责。

## License

MIT
