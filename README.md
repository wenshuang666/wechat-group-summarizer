# WeChat Group Summarizer

> 微信数据库读取 + 消息总结工具，支持 GenericAgent 自动配置。

## 快速开始

### 方式一：GA 用户（推荐）

如果你正在使用 [GenericAgent](https://github.com/...)：

```bash
# 1. 克隆项目到 GA 的 temp 目录
git clone https://github.com/wenshuang666/wechat-group-summarizer.git

# 2. 让 GA 自动配置
# 对 GA 说："请按照 ga_sop/wechat_summary_setup.md 帮我配置微信消息总结"
```

GA 会自动完成：路径发现 → 密钥提取 → 依赖安装 → 测试连接。

### 方式二：手动配置

```bash
# 1. 克隆
pip install -r requirements.txt

# 2. 设置环境变量
set WECHAT_DB_DIR=C:\Users\<用户名>\Documents\xwechat_files\<wxid>_<hash>\db_storage
set WECHAT_KEYS_FILE=.\wechat_keys.json

# 3. 准备密钥文件（手动提取或参考社区方法）
# wechat_keys.json 格式：
# {
#   "message_0": "32位十六进制密钥",
#   "contact_0": "32位十六进制密钥"
# }

# 4. 运行
python -c "from wechat_db_reader import WeChatDBReader; r = WeChatDBReader(); print(r.list_groups())"
```

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

## 免责声明

本项目仅供学习研究使用。使用本项目需遵守相关法律法规和微信用户协议。开发者不对任何滥用行为负责。

## License

MIT
