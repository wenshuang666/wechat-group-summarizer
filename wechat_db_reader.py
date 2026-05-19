"""
WeChat DB Reader - 简化实用版
直接遍历所有 Msg_ 表读取群聊消息
支持 zstd 压缩的图片/文件元数据解析
"""
import sqlcipher3
import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Dict, Optional

# 可选：zstandard 用于解压微信消息内容
try:
    import zstandard as zstd
    HAS_ZSTD = True
except ImportError:
    HAS_ZSTD = False

# ============ 配置 ============
# 微信数据目录：请修改为你的实际路径
# 格式: <XWeChat数据根目录>\db_storage
# 示例: r'C:\Users\<用户名>\Documents\xwechat_files\<wxid>_<hash>\db_storage'
DATA_DIR = os.environ.get('WECHAT_DB_DIR', r'PLEASE_SET_YOUR_DB_DIR')
KEYS_FILE = os.path.join(os.path.dirname(__file__), "wechat_keys.json")
GROUP_MAP_FILE = os.path.join(os.path.dirname(__file__), "plan_wechat_summary", "group_map.json")

# 已知表到群聊的映射（通过消息内容确认）
KNOWN_TABLE_MAP = {
    "Msg_e765e0397c9e67788aa23dcd5b3e19ba": "GenericAgent体验交流群16",
    "Msg_64f9f8ed137f012d29cd298cf20184e7": "人工智能23-2班",  # 校园卡/操场/主楼
}

class WeChatDBReader:
    """微信数据库读取器"""
    
    def __init__(self):
        with open(KEYS_FILE, "r", encoding="utf-8") as f:
            self.keys = json.load(f)
        
        # 加载群聊名称映射
        with open(GROUP_MAP_FILE, "r", encoding="utf-8") as f:
            self.group_map = json.load(f)
        
        self._msg_conn = None
        self._contact_conn = None
        self._msg_tables = None
    
    def _get_conn(self, db_relative_path: str, key_only: bool = False):
        """通用数据库连接方法
        db_relative_path: 如 'message/message_0.db'
        key_only: True=只用key不加salt, False=key+salt (仅message_0.db需要)
        """
        db_path = os.path.join(DATA_DIR, db_relative_path.replace('/', os.sep))
        key = self.keys[db_relative_path]
        conn = sqlcipher3.connect(db_path)
        conn.execute("PRAGMA cipher_page_size = 4096;")
        conn.execute("PRAGMA cipher_kdf_algorithm = PBKDF2_HMAC_SHA512;")
        if key_only:
            conn.execute(f"PRAGMA key = \"x'{key}'\";")
        else:
            salt = 'a8efc2ab103c6ebc97997be725286b5b'
            conn.execute(f"PRAGMA key = \"x'{key}{salt}'\";")
        return conn
    
    def _get_msg_conn(self):
        if self._msg_conn is None:
            # message_0.db 兼容 key+salt 模式
            self._msg_conn = self._get_conn('message/message_0.db', key_only=False)
        return self._msg_conn
    
    def _get_media_conn(self):
        """连接 media_0.db (需要key_only)"""
        return self._get_conn('message/media_0.db', key_only=True)
    
    def _get_msg_resource_conn(self):
        """连接 message_resource.db (需要key_only)"""
        return self._get_conn('message/message_resource.db', key_only=True)
    
    def get_msg_tables(self) -> List[str]:
        """获取所有消息表名"""
        if self._msg_tables is None:
            conn = self._get_msg_conn()
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'Msg_%';")
            self._msg_tables = [row[0] for row in cur.fetchall()]
        return self._msg_tables
    
    def _get_table_by_group_name(self, group_name: str) -> str:
        """通过群名找到对应的 Msg_ 表名。规则: Msg_{MD5(chatroom_id)}"""
        import hashlib
        # 1. 从 group_map 找到 chatroom_id（群名 -> chatroom_id）
        chatroom_id = None
        for cid, name in self.group_map.items():
            if group_name.lower() in name.lower() or name.lower() in group_name.lower():
                chatroom_id = cid
                break
        if not chatroom_id:
            return None
        # 2. 计算 MD5 得到表名
        table_name = f"Msg_{hashlib.md5(chatroom_id.encode()).hexdigest()}"
        # 3. 验证表存在
        if table_name in self.get_msg_tables():
            return table_name
        return None
    
    def _decode_content(self, raw: bytes, msg_type: int) -> Optional[str]:
        """解压并解析 zstd 压缩的消息内容，返回可读文本"""
        if not raw:
            return None
        
        # 1. 如果是纯文本（str），直接返回
        if isinstance(raw, str):
            return raw
        
        # 2. 尝试 zstd 解压（微信消息常用压缩）
        data = raw
        if HAS_ZSTD and len(data) >= 4 and data[:4] == b'\x28\xb5\x2f\xfd':
            try:
                decompressor = zstd.ZstdDecompressor()
                data = decompressor.decompress(data)
            except Exception:
                pass  # 解压失败，继续尝试原始数据
        
        # 3. 转为文本（去掉可能的 sender 前缀）
        text = None
        if isinstance(data, bytes):
            for enc in ('utf-8', 'gbk', 'gb2312', 'latin-1'):
                try:
                    text = data.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
        else:
            text = data
        
        if not text:
            return None
        
        # 去掉 sender 前缀（格式: wxid_xxx:\n<xml>...）
        text = re.sub(r'^wxid_[a-z0-9]+:\s*', '', text, flags=re.IGNORECASE)
        
        # 4. 解析 XML 提取关键信息
        content = self._parse_xml_content(text, msg_type)
        return content if content else text[:500]
    
    def _parse_xml_content(self, text: str, msg_type: int) -> Optional[str]:
        """解析微信 XML 消息，提取可读信息"""
        if '<msg>' not in text and '<appmsg' not in text:
            return text  # 纯文本直接返回
        
        try:
            # 图片
            if '<img ' in text:
                m = re.search(r'<img[^>]+>', text)
                if m:
                    return "[图片]"
            
            # 语音
            if '<voicemsg ' in text:
                return "[语音]"
            
            # 视频
            if '<videomsg ' in text:
                return "[视频]"
            
            # 表情/动画表情
            if '<emoji ' in text or msg_type == 47:
                return "[表情]"
            
            # 文件/应用消息 (<appmsg 开头，注意没有 >)
            if '<appmsg' in text:
                title = re.search(r'<title>(<\!\[CDATA\[)?(.*?)(\]\]>)?</title>', text, re.DOTALL)
                app_type = re.search(r'<type>(\d+)</type>', text)
                file_ext = re.search(r'<fileext>(<\!\[CDATA\[)?(.*?)(\]\]>)?</fileext>', text, re.DOTALL)
                
                type_num = int(app_type.group(1)) if app_type else 0
                title_text = (title.group(2) if title else "").strip()
                ext_text = (file_ext.group(2) if file_ext else "").strip()
                
                if type_num == 6 or ext_text:
                    # 文件
                    filename = title_text or f"未知文件.{ext_text}"
                    return f"[文件: {filename}]"
                elif type_num == 5:
                    # 链接/公众号
                    return f"[链接: {title_text}]" if title_text else "[链接]"
                elif type_num == 33 or type_num == 36:
                    # 小程序
                    return f"[小程序: {title_text}]" if title_text else "[小程序]"
                elif type_num == 2000:
                    # 转账
                    return "[转账]"
                elif title_text:
                    return f"[应用消息: {title_text}]"
                return "[应用消息]"
            
            return text
        except Exception:
            return text[:500]
    
    def get_group_messages(self, group_name: str, limit: int = 100, 
                           include_system: bool = False) -> List[Dict]:
        """
        获取指定群聊的消息
        :param group_name: 群聊名称（支持部分匹配）
        :param limit: 消息数量限制
        :param include_system: 是否包含系统消息
        :return: 消息列表
        """
        conn = self._get_msg_conn()
        
        # 核心查找：通过 group_map -> chatroom_id -> MD5 -> 表名
        target_table = self._get_table_by_group_name(group_name)
        
        if not target_table:
            # fallback：尝试 KNOWN_TABLE_MAP（旧兼容）
            for table, known_name in KNOWN_TABLE_MAP.items():
                if group_name.lower() in known_name.lower() or known_name.lower() in group_name.lower():
                    target_table = table
                    break
        
        if not target_table:
            print(f"[WARN] 找不到群聊 '{group_name}' 对应的消息表")
            return []
        
        # 读取目标表的消息
        # type: 1=text, 3=image, 34=voice, 43=video, 47=sticker, 49=app/link
        # 大整数类型通常是带标志位的文件/应用消息，如 25769803825
        base_types = (1, 3, 34, 43, 47, 49)
        type_filter = f"(local_type IN {base_types} OR local_type > 10000000000)" if not include_system else "1=1"
        
        msgs = []
        cur = conn.execute(
            f"SELECT local_id, create_time, message_content, real_sender_id, local_type, source "
            f"FROM {target_table} WHERE message_content IS NOT NULL "
            f"AND {type_filter} "
            f"ORDER BY local_id DESC LIMIT {limit}"
        )
        
        for row in cur.fetchall():
            raw_content = row[2]
            decoded = self._decode_content(raw_content, row[4])
            if decoded:
                msgs.append({
                    "local_id": row[0],
                    "time": row[1],
                    "content": decoded,
                    "sender_id": row[3],
                    "type": row[4],
                    "source": row[5],
                    "table": target_table
                })
        
        return msgs
    
    def list_groups(self) -> List[str]:
        """列出所有群聊名称"""
        return list(self.group_map.values())
    
    def close(self):
        if self._msg_conn:
            self._msg_conn.close()
            self._msg_conn = None


def get_group_list() -> list:
    """获取所有群聊名称列表"""
    reader = WeChatDBReader()
    try:
        return reader.list_groups()
    finally:
        reader.close()


def get_group_summary_text(group_name: str, limit: int = 100, 
                           include_media: bool = True) -> str:
    """获取群聊消息的格式化文本，用于LLM总结
    :param include_media: 是否提取图片OCR和文档内容
    """
    reader = WeChatDBReader()
    try:
        msgs = reader.get_group_messages(group_name, limit=limit)
        if not msgs:
            return f"群聊 '{group_name}' 暂无消息。"
        
        # 预加载媒体内容
        media_extras = {}
        if include_media:
            try:
                from wechat_media_extractor import get_cache_mapping, get_file_mapping, \
                    extract_image_text, extract_document_text
                cache_map = get_cache_mapping()
                file_map = get_file_mapping()
                for msg in msgs:
                    lid = msg.get('local_id')
                    mtype = msg.get('type', 0)
                    if not lid:
                        continue
                    # 图片: type=3
                    if mtype == 3 and lid in cache_map:
                        text = extract_image_text(lid)
                        if text:
                            media_extras[lid] = f"[图片内容: {text[:200]}...]"
                    # 文档: type=49 (应用消息中可能包含文件)
                    elif mtype == 49:
                        # 从消息内容中提取文件名
                        msg_content = msg.get('content', '')
                        fname = None
                        if isinstance(msg_content, str):
                            # 尝试提取 weapp_path_info
                            m = re.search(r'weapp_path_info="([^"]+)"', msg_content)
                            if m:
                                from wechat_media_extractor import get_document_filename_from_packed
                                packed = m.group(1).encode('utf-8', errors='ignore')
                                fname = get_document_filename_from_packed(packed)
                            # 回退: 尝试 title="..."
                            if not fname:
                                m2 = re.search(r'title="([^"]{3,100}\.(docx|pdf|txt|md))"', msg_content, re.I)
                                if m2:
                                    fname = m2.group(1)
                        if fname:
                            content = extract_document_text(fname)
                            if content:
                                media_extras[lid] = f"[文档内容摘要: {content[:300]}...]"
            except Exception as e:
                print(f"[WARN] 媒体提取失败: {e}")
        
        lines = [f"群聊: {group_name}", f"最近 {len(msgs)} 条消息", "=" * 40, ""]
        
        for msg in reversed(msgs):  # 按时间正序
            time_str = datetime.fromtimestamp(msg["time"]).strftime("%Y-%m-%d %H:%M:%S") if msg["time"] > 1000000000 else str(msg["time"])
            sender = f"用户{msg['sender_id']}"
            content = msg["content"]
            lines.append(f"[{time_str}] {sender}: {content}")
            
            # 追加媒体提取内容
            lid = msg.get('local_id')
            if lid and lid in media_extras:
                lines.append(f"  -> {media_extras[lid]}")
        
        return "\n".join(lines)
    finally:
        reader.close()


# ============ 测试 ============
if __name__ == "__main__":
    reader = WeChatDBReader()
    
    print("=== 群聊列表 ===")
    groups = reader.list_groups()
    for g in groups[:10]:
        print(f"  📢 {g}")
    
    print("\n=== 测试 GenericAgent体验交流群16 ===")
    try:
        msgs = reader.get_group_messages("GenericAgent体验交流群16", limit=10)
        print(f"读取到 {len(msgs)} 条消息")
        for m in msgs[:5]:
            print(f"  [{m['time']}] {m['content'][:60]}")
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
    
    reader.close()
