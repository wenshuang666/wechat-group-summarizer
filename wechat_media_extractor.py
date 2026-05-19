"""
WeChat 媒体内容提取模块
- 图片: 通过 local_id 关联 cache 目录中的 thumb.jpg / hd_temp
- 文档: 通过 packed_info 中的文件名关联 msg/file/ 目录
- 支持 OCR (rapidocr) 和文档解析 (docx/pdf/md/txt)
"""
import os, re, glob, json
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# ============ 配置 ============
# 微信消息文件目录：请修改为你的实际路径
# 格式: <XWeChat数据根目录>\msg
# 示例: r'C:\Users\<用户名>\Documents\xwechat_files\<wxid>_<hash>\msg'
MSG_BASE = os.environ.get('WECHAT_MSG_DIR', r'PLEASE_SET_YOUR_MSG_DIR')
CACHE_BASE = os.path.join(MSG_BASE, 'cache') if MSG_BASE != 'PLEASE_SET_YOUR_MSG_DIR' else 'PLEASE_SET_YOUR_MSG_DIR'
FILE_BASE = os.path.join(MSG_BASE, 'file') if MSG_BASE != 'PLEASE_SET_YOUR_MSG_DIR' else 'PLEASE_SET_YOUR_MSG_DIR'

# OCR 引擎 (优先 rapidocr)
try:
    from rapidocr_onnxruntime import RapidOCR
    _ocr_engine = RapidOCR()
    HAS_OCR = True
except ImportError:
    _ocr_engine = None
    HAS_OCR = False

# 文档解析器
try:
    from docx import Document
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

try:
    import PyPDF2
    HAS_PDF = True
except ImportError:
    HAS_PDF = False


def _scan_cache_dirs() -> Dict[int, Tuple[str, str]]:
    """
    扫描所有 cache 子目录，建立 local_id -> (thumb_path, hd_path) 映射
    返回: {local_id: (thumb.jpg路径, hd_temp路径)}
    """
    mapping = {}
    if not os.path.exists(CACHE_BASE):
        return mapping
    
    # 遍历所有月份目录 (如 2026-05)
    if not os.path.exists(CACHE_BASE):
        return mapping
    for month_dir in os.listdir(CACHE_BASE):
        month_path = os.path.join(CACHE_BASE, month_dir)
        if not os.path.isdir(month_path):
            continue
        # 遍历所有 Message/<hash>/ 目录
        msg_base = os.path.join(month_path, 'Message')
        if not os.path.exists(msg_base):
            continue
        for msg_hash in os.listdir(msg_base):
            msg_hash_dir = os.path.join(msg_base, msg_hash)
            if not os.path.isdir(msg_hash_dir):
                continue
            thumb_dir = os.path.join(msg_hash_dir, 'Thumb')
            image_dir = os.path.join(msg_hash_dir, 'ImageTemp')
            
            # 扫描 thumb.jpg
            if os.path.exists(thumb_dir):
                for f in os.listdir(thumb_dir):
                    m = re.match(r'(\d+)_(\d+)_thumb\.jpg$', f)
                    if m:
                        local_id = int(m.group(1))
                        thumb_path = os.path.join(thumb_dir, f)
                        # 查找对应的 hd_temp
                        hd_path = None
                        if os.path.exists(image_dir):
                            for hf in os.listdir(image_dir):
                                if hf.startswith(f"{local_id}_") and hf.endswith('_hd_temp'):
                                    hd_path = os.path.join(image_dir, hf)
                                    break
                        mapping[local_id] = (thumb_path, hd_path)
    
    return mapping


# 全局缓存扫描结果（运行时只扫描一次）
_CACHE_MAPPING = None

def get_cache_mapping() -> Dict[int, Tuple[str, str]]:
    """获取 local_id -> 图片路径映射（带缓存）"""
    global _CACHE_MAPPING
    if _CACHE_MAPPING is None:
        _CACHE_MAPPING = _scan_cache_dirs()
    return _CACHE_MAPPING


def extract_image_text(local_id: int, use_hd: bool = True, min_confidence: float = 0.3) -> Optional[str]:
    """
    通过 local_id 提取图片中的文字（OCR）
    :param use_hd: True=优先使用高清图, False=只用缩略图
    :param min_confidence: 最低置信度过滤
    :return: 提取的文字，或 None（无OCR/无图片）
    """
    if not HAS_OCR:
        return None
    
    mapping = get_cache_mapping()
    if local_id not in mapping:
        return None
    
    thumb_path, hd_path = mapping[local_id]
    
    # 选择图片文件
    img_path = hd_path if (use_hd and hd_path and os.path.getsize(hd_path) > 1024) else thumb_path
    if not img_path or not os.path.exists(img_path):
        return None
    
    try:
        from PIL import Image
        img = Image.open(img_path)
        result, _ = _ocr_engine(img)
        if not result:
            return None
        
        # 过滤低置信度结果
        lines = []
        for item in result:
            if len(item) >= 3:
                text = item[1]
                conf = item[2] if isinstance(item[2], (int, float)) else 0.5
                if conf >= min_confidence and text.strip():
                    lines.append(text)
        
        return "\n".join(lines) if lines else None
    except Exception as e:
        print(f"[MediaExtractor] OCR failed for local_id={local_id}: {e}")
        return None


def _scan_file_dirs() -> Dict[str, str]:
    """扫描所有 msg/file/ 子目录，建立文件名 -> 完整路径映射"""
    mapping = {}
    if not os.path.exists(FILE_BASE):
        return mapping
    
    for month_dir in os.listdir(FILE_BASE):
        month_path = os.path.join(FILE_BASE, month_dir)
        if not os.path.isdir(month_path):
            continue
        for f in os.listdir(month_path):
            mapping[f] = os.path.join(month_path, f)
    
    return mapping


# 全局文件映射缓存
_FILE_MAPPING = None

def get_file_mapping() -> Dict[str, str]:
    """获取文件名 -> 路径映射（带缓存）"""
    global _FILE_MAPPING
    if _FILE_MAPPING is None:
        _FILE_MAPPING = _scan_file_dirs()
    return _FILE_MAPPING


def extract_document_text(filename_hint: str) -> Optional[str]:
    """
    通过文件名提示提取文档内容
    :param filename_hint: 文件名或文件名的一部分
    :return: 文档文字内容，或 None
    """
    file_mapping = get_file_mapping()
    
    # 精确匹配
    if filename_hint in file_mapping:
        fpath = file_mapping[filename_hint]
    else:
        # 部分匹配
        matched = None
        for fname, fpath in file_mapping.items():
            if filename_hint in fname or fname in filename_hint:
                matched = fpath
                break
        if not matched:
            return None
        fpath = matched
    
    if not os.path.exists(fpath):
        return None
    
    ext = os.path.splitext(fpath)[1].lower()
    
    try:
        if ext == '.docx' and HAS_DOCX:
            doc = Document(fpath)
            texts = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n".join(texts)
        
        elif ext in ('.md', '.txt', '.csv', '.json'):
            with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        
        elif ext == '.pdf' and HAS_PDF:
            with open(fpath, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                texts = []
                # 只读取前5页，避免超大PDF
                for page in reader.pages[:5]:
                    txt = page.extract_text()
                    if txt:
                        texts.append(txt)
                return "\n".join(texts)
        
        else:
            # 尝试作为文本读取
            with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                # 如果看起来是文本（可打印字符比例>80%）
                printable = sum(1 for c in content if c.isprintable() or c in '\n\r\t')
                if len(content) > 0 and printable / len(content) > 0.8:
                    return content
    except Exception as e:
        print(f"[MediaExtractor] Doc parse failed for {fpath}: {e}")
    
    return None


def get_document_filename_from_packed(packed_info: bytes) -> Optional[str]:
    """
    从 packed_info 二进制数据中提取文件名
    packed_info 中文件名格式: <filename>\x00<filename> (重复两次)
    """
    if not packed_info:
        return None
    
    # 尝试所有文本编码
    for enc in ('utf-8', 'gbk', 'gb2312', 'latin-1'):
        try:
            text = packed_info.decode(enc)
            # 查找 docx/pdf/txt/md 等扩展名
            m = re.search(r'([^\\/:*?"<>|\r\n]{3,100}\.(docx|pdf|txt|md|csv|xlsx|pptx))', text, re.IGNORECASE)
            if m:
                return m.group(1)
        except:
            continue
    
    return None


def extract_media_for_message(local_id: int, msg_type: int, packed_info: Optional[bytes] = None) -> Dict[str, any]:
    """
    提取单条消息的媒体内容
    :param local_id: 消息 local_id
    :param msg_type: 消息类型 (3=图片, 49=文件/app, 等)
    :param packed_info: 资源的 packed_info (用于文档类型)
    :return: {'type': 'image'|'document', 'text': extracted_text, 'source': path_or_desc}
    """
    result = {'type': None, 'text': None, 'source': None}
    
    # 1. 图片消息 (type=3)
    if msg_type == 3:
        ocr_text = extract_image_text(local_id, use_hd=True)
        if ocr_text:
            mapping = get_cache_mapping()
            if local_id in mapping:
                thumb, hd = mapping[local_id]
                src = hd or thumb
                result = {
                    'type': 'image',
                    'text': ocr_text,
                    'source': src,
                    'description': f'[图片OCR文字 ({len(ocr_text)}字)]'
                }
    
    # 2. 文件/应用消息 (type=49 或 large type with appmsg)
    elif msg_type == 49 or msg_type > 10000000000:
        if packed_info:
            filename = get_document_filename_from_packed(packed_info)
            if filename:
                doc_text = extract_document_text(filename)
                if doc_text:
                    result = {
                        'type': 'document',
                        'text': doc_text,
                        'source': filename,
                        'description': f'[文档: {filename}]'
                    }
    
    return result


def enrich_messages_with_media(msgs: List[Dict]) -> List[Dict]:
    """
    为消息列表添加媒体内容提取
    :param msgs: get_group_messages() 返回的消息列表
    :return: 增加了 'media_content' 字段的消息列表
    """
    from wechat_db_reader import WeChatDBReader
    
    reader = WeChatDBReader()
    conn2 = None
    try:
        conn2 = reader._get_msg_resource_conn()
        
        for msg in msgs:
            msg['media_content'] = None
            msg_type = msg.get('type', 0)
            
            # 只处理图片和文件类型
            if msg_type == 3 or msg_type == 49 or msg_type > 10000000000:
                # 尝试从 message_resource.db 获取 packed_info
                # 注意：message_resource.db 中 message_local_id 是消息的 local_id
                # 但我们没有 local_id 在 get_group_messages 的返回中... 需要修改 get_group_messages
                pass
        
        return msgs
    finally:
        if conn2:
            conn2.close()


if __name__ == '__main__':
    # 测试
    print("=== 图片缓存映射 (前5条) ===")
    mapping = get_cache_mapping()
    for lid, (thumb, hd) in list(mapping.items())[:5]:
        print(f"  local_id={lid}: thumb={os.path.basename(thumb)}, hd={os.path.basename(hd) if hd else 'None'}")
    
    print(f"\n=== 文件映射 (共 {len(get_file_mapping())} 个) ===")
    for fname in list(get_file_mapping().keys())[:5]:
        print(f"  {fname}")
    
    print("\n=== 测试OCR ===")
    if mapping:
        first_lid = list(mapping.keys())[0]
        text = extract_image_text(first_lid)
        print(f"  local_id={first_lid}: OCR结果={'有' if text else '无'}")
        if text:
            print(f"  前100字: {text[:100]}")
