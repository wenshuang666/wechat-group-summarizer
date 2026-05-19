# GA 微信消息总结配置 SOP

> 本 SOP 指导 GA 自动完成微信消息总结的配置。
> 适用对象：已安装 GenericAgent 的用户

## 前置条件

- [ ] Windows 系统
- [ ] 微信 PC 版已登录（需保持运行以提取密钥）
- [ ] 已安装 GenericAgent
- [ ] Python 3.8+

## 步骤 1：定位微信数据目录

1. 搜索用户文档目录下的微信数据文件夹：
   - 路径模式：`%USERPROFILE%\Documents\xwechat_files\wxid_*/db_storage`
   - 或：`%USERPROFILE%\Documents\WeChat Files\wxid_*/db_storage`

2. 确认目录结构包含：
   - `db_storage/message/message_0.db`
   - `db_storage/contact/contact_0.db`

3. 记录找到的 `<XWeChat数据根目录>` 路径。

## 步骤 2：提取 sqlcipher 密钥

> ⚠️ 微信数据库使用 sqlcipher 加密，密钥需要从 WeChat.exe 进程内存中提取。

1. 使用 `procmem_scanner` 扫描 WeChat.exe 进程。
2. 搜索内存中的 AES 密钥特征：
   - 密钥为 32 字节十六进制字符串
   - 通常出现在 sqlcipher 初始化后的内存区域
3. 提取密钥后，创建 `wechat_keys.json`：
   ```json
   {
     "message_0": "<message_db_key>",
     "contact_0": "<contact_db_key>"
   }
   ```

> 💡 **替代方案**：如果密钥提取困难，可参考社区方法手动获取。

## 步骤 3：配置环境变量

在 GA 会话中设置：

```bash
set WECHAT_DB_DIR=<XWeChat数据根目录>\db_storage
set WECHAT_KEYS_FILE=<本项目目录>\wechat_keys.json
```

或直接在代码中初始化：

```python
import os
os.environ['WECHAT_DB_DIR'] = r'<你的路径>\db_storage'
os.environ['WECHAT_KEYS_FILE'] = r'<你的路径>\wechat_keys.json'
```

## 步骤 4：安装依赖

```bash
pip install -r requirements.txt
```

依赖清单：
- `sqlcipher3`
- `zstandard`
- `rapidocr_onnxruntime`（可选，用于图片 OCR）
- `python-docx`（可选，用于文档解析）
- `pymupdf`（可选，用于 PDF 解析）

## 步骤 5：测试数据库连接

```python
from wechat_db_reader import WeChatDBReader

reader = WeChatDBReader()

# 列出所有群聊
groups = reader.list_groups()
print("发现群聊:", groups[:10])

# 读取指定群聊消息（支持模糊匹配）
msgs = reader.get_group_messages("你的群聊名称", limit=50)
for m in msgs:
    print(f"[{m['time']}] {m['sender_name']}: {m['content'][:50]}")

reader.close()
```

## 步骤 6：配置群聊映射（可选）

如果自动发现不能满足需求，可创建 `group_map.json`：

```json
{
  "chatroom_id_hash": "群聊显示名称",
  "another_chatroom": "另一个群"
}
```

然后通过环境变量指定：
```bash
set WECHAT_GROUP_MAP=<路径>\group_map.json
```

## 步骤 7：运行消息总结

结合 `wechat_media_extractor.py` 提取媒体内容，然后将消息发送给 LLM 生成摘要。

完整示例：

```python
from wechat_db_reader import WeChatDBReader

reader = WeChatDBReader()
msgs = reader.get_group_messages("目标群聊", limit=200)

# 构建消息文本
lines = []
for m in msgs:
    lines.append(f"[{m['time']}] {m['sender_name']}: {m['content']}")

prompt = "请总结以下群聊消息：\n\n" + "\n".join(lines)
# 将 prompt 发送给你的 LLM 获取摘要
```

## 故障排除

| 问题 | 解决方案 |
|------|---------|
| `找不到群聊` | 确认微信已同步该群聊的最近消息；尝试用 GA 自动发现功能 |
| `数据库解密失败` | 检查密钥是否正确；确认 sqlcipher3 版本兼容 |
| `图片/文件无法提取` | 检查 `IMAGE_BASE_DIR` 和 `FILE_BASE_DIR` 路径 |
| `OCR 无法识别` | 确认 `rapidocr_onnxruntime` 已安装 |

## 安全提示

- 🔐 `wechat_keys.json` 包含敏感密钥，**切勿提交到 Git**
- 🚫 已添加 `.gitignore` 忽略密钥文件
- 🛡️ 本项目不会上传任何消息到外部服务器，所有处理在本地完成
