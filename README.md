# 微信本地群聊消息总结器

基于微信 Windows 版（XWeChatFiles）本地数据库的群聊消息读取与智能总结工具。

## 功能

- 🔓 **数据库解密**: 自动读取 sqlcipher 加密的数据库文件
- 📊 **群聊总结**: 提取最近 N 条消息，发送给 LLM 生成中文摘要
- 🖼️ **图片 OCR**: 自动提取群聊图片中的文字内容
- 📄 **文档解析**: 自动读取群聊分享的 docx/pdf/md/txt 文件内容
- 🤖 **Bot 集成**: 已对接微信机器人，支持 `/summary <群名>` 指令

## 技术栈

- `sqlcipher3` - 数据库解密
- `zstandard` - 消息内容 zstd 解压
- `rapidocr-onnxruntime` - 本地图片 OCR（无需联网）
- `python-docx` - Word 文档解析
- `PyMuPDF` / `pymupdf4llm` - PDF 解析

## 项目结构

```
├── wechat_db_reader.py          # 核心：DB 读取 + 消息解析
├── wechat_media_extractor.py    # 媒体提取：图片 OCR + 文档解析
├── wechatapp.py                 # Bot 入口：/summary 指令处理
└── wechat_keys.json             # 数据库密钥（需自行提取）
```

## 使用方法

### 1. 环境准备

```bash
pip install sqlcipher3 zstandard rapidocr-onnxruntime python-docx pymupdf pymupdf4llm
```

### 2. 配置路径

设置环境变量指向你的微信数据目录：

```bash
# Windows
set WECHAT_DB_DIR=C:\Users\<用户名>\Documents\xwechat_files\<wxid>_<hash>\db_storage
set WECHAT_MSG_DIR=C:\Users\<用户名>\Documents\xwechat_files\<wxid>_<hash>\msg
```

或在代码中直接修改 `wechat_db_reader.py` 和 `wechat_media_extractor.py` 中的路径。

### 3. 提取数据库密钥

需要先从微信进程内存中提取 sqlcipher 密钥，保存为 `wechat_keys.json`：

```json
{
  "message_0.db": "0x01,0x02,...",
  "message_1.db": "..."
}
```

### 4. 运行

```python
from wechat_db_reader import get_group_summary_text

# 获取群聊总结文本（自动包含图片OCR和文档内容）
text = get_group_summary_text("群聊名称", limit=100, include_media=True)
print(text)
```

## 消息类型支持

| 类型 | 显示 | 媒体提取 |
|------|------|----------|
| 文本 | ✅ | - |
| 图片 | ✅ | OCR 提取文字 |
| 文件/文档 | ✅ | 解析 docx/pdf/md/txt |
| 表情 | ✅ | - |
| 语音 | ✅ | - |
| 视频 | ✅ | - |
| 链接 | ✅ | - |
| 应用消息 | ✅ | - |
| 拍一拍 | ✅ | - |

## 关键发现

1. **zstd 压缩**: 非文本消息内容使用 zstd 压缩（魔数 `28 b5 2f fd`），解压后得到 XML 元数据
2. **本地文件关联**: 图片通过 `local_id` 关联 `msg/cache/` 目录；文档通过文件名关联 `msg/file/` 目录
3. **消息类型映射**: `type=3` 图片, `type=49` 文件, `type=47` 表情, `type=1` 文本

## 免责声明

本项目仅供学习和研究使用。请遵守相关法律法规，尊重用户隐私。使用本工具需获得相关群聊成员的知情同意。

## License

MIT License
