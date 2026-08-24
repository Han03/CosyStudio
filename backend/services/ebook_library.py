"""电子书库服务。

负责电子书入库、章节拆分与查询。入库流程：
1. 通过 MediaManager 保存文件到 media/document/books/ 目录
2. 计算文件 MD5（去重依据）
3. 识别文件编码并读取文本内容
4. 统计字数
5. 拆分章节（记录字节偏移，便于后续直接按位置读取）
6. 写入 ebook_library 与 ebook_chapters 表

章节拆分支持常见标题格式：
- 中文：第一章/第1章/第一回/第一节/第一卷/楔子/序章/前言/后记/尾声
- 英文：Chapter 1 / CHAPTER I / Prologue / Epilogue

支持的文件格式：
- TXT：纯文本，按字节偏移读取
- EPUB：使用 ebooklib 解析
"""

import os
import re
import time
import hashlib
from typing import Optional, List, Dict, Any, Tuple

from utils.logger import logger
from repositories import (
    get_ebook_by_md5, add_ebook, add_chapters, get_ebooks_paged,
    get_chapter_count, get_ebook, get_chapters, get_chapter, delete_ebook,
    get_scripts_by_book, get_script_chapter
)
from services.media_manager import get_media_manager


# 章节标题正则（行首匹配）
# 中文数字映射，用于匹配"第一章"等
_CN_NUM = r"[一二三四五六七八九十百千零〇两]"
_CHAPTER_PATTERNS = [
    # 带 §§ 前缀的章节标题（EPUB常见格式）
    re.compile(rf"^§§第\s*({_CN_NUM}+|\d+)\s*[章回节卷篇]\s*[^\n]*"),
    re.compile(r"^§§(序章|楔子|前言|序言|后记|尾声|引子|楔章|引言|跋)\s*[^\n]*"),
    re.compile(r"^§§chapter\s+[\dIVXLCDM]+\b.*", re.IGNORECASE),
    re.compile(r"^§§\s*[^\d].*"),
    # 第X章/节/回/卷/篇  支持中文数字、阿拉伯数字、纯数字
    re.compile(rf"^第\s*({_CN_NUM}+|\d+)\s*[章回节卷篇]\s*[^\n]*"),
    # 序章/楔子/前言/序言/后记/尾声/引子/楔章
    re.compile(r"^(序章|楔子|前言|序言|后记|尾声|引子|楔章|引言|跋)\s*[^\n]*"),
    # Chapter X / CHAPTER X  支持罗马数字与阿拉伯数字
    re.compile(r"^chapter\s+[\dIVXLCDM]+\b.*", re.IGNORECASE),
    re.compile(r"^prologue\b.*", re.IGNORECASE),
    re.compile(r"^epilogue\b.*", re.IGNORECASE),
]

# 常见编码尝试顺序
_ENCODINGS = ["utf-8", "gbk", "gb18030", "big5", "utf-16", "latin-1"]

# 支持的电子书格式
_SUPPORTED_FORMATS = [".txt", ".epub"]
_BOOK_MODULE = "books"


class EbookLibraryService:
    """电子书库服务。"""

    def __init__(self):
        self._media = get_media_manager()

    def ingest(self, filename: str, content: bytes,
               title: Optional[str] = None,
               author: str = "",
               description: str = "") -> Dict[str, Any]:
        """电子书入库。

        参数:
            filename: 原始文件名（含扩展名）
            content: 文件二进制内容
            title: 书名（可选，默认从文件名推导）
            author: 作者（可选）
            description: 简介（可选）

        返回:
            {"success": bool, "book_id": int, "message": str, ...}
            MD5 重复时 success=True 但返回已存在的 book_id 与 duplicated=True
        """
        ext = os.path.splitext(filename)[1].lower()
        fmt = ext.lstrip(".") if ext else "txt"
        if fmt == "":
            fmt = "txt"

        book_title = title or os.path.splitext(filename)[0]
        md5 = hashlib.md5(content).hexdigest()

        # 去重检查
        existing = get_ebook_by_md5(md5)
        if existing is not None:
            logger.info(f"[EbookLibrary] 文件已存在（MD5 重复）: {filename} -> book_id={existing['id']}")
            return {
                "success": True,
                "duplicated": True,
                "book_id": existing["id"],
                "message": f"电子书已存在（MD5 重复）: {existing['title']}",
            }

        # 通过媒体管理器保存文件到 media/document/books/
        relative_path = self._media.save_file(
            module=_BOOK_MODULE, filename=filename, content=content,
            category="document",
        )
        file_size = len(content)
        logger.info(f"[EbookLibrary] 文件已保存: {relative_path} ({file_size} bytes)")

        # 解析文本内容并拆分章节
        encoding, text, word_count, chapters = self._parse_and_split(content, fmt)

        # 写入电子书记录
        book_id = add_ebook(
            title=book_title,
            file_path=relative_path,
            file_size=file_size,
            word_count=word_count,
            md5=md5,
            fmt=fmt,
            encoding=encoding,
            author=author,
            description=description,
        )
        if book_id is None:
            return {
                "success": False,
                "message": "电子书入库失败（MD5 冲突）",
            }

        # 写入章节记录
        chapter_count = 0
        if chapters:
            chapter_count = add_chapters(book_id, chapters)

        logger.info(
            f"[EbookLibrary] 入库成功: {book_title} (id={book_id}, "
            f"字数={word_count}, 章节={chapter_count})"
        )

        return {
            "success": True,
            "duplicated": False,
            "book_id": book_id,
            "title": book_title,
            "file_path": relative_path,
            "file_size": file_size,
            "word_count": word_count,
            "md5": md5,
            "format": fmt,
            "encoding": encoding,
            "chapter_count": chapter_count,
            "message": "电子书入库成功",
        }

    def _parse_and_split(self, content: bytes, fmt: str) -> Tuple[str, str, int, List[Dict[str, Any]]]:
        """解析文本内容并拆分章节。

        返回: (encoding, text, word_count, chapters)
        chapters 元素: {"chapter_index", "title", "start_pos", "end_pos", "content", "word_count"}
        start_pos/end_pos 为字节偏移（基于原始 content，仅 TXT 格式使用）
        content 字段存储章节正文（非 TXT 格式使用）
        """
        if fmt == "epub":
            return self._parse_epub(content)

        encoding, text = self._decode_text(content)
        if text is None:
            return encoding, "", 0, []

        word_count = self._count_words(text)
        chapters = self._split_chapters(content, text, encoding)
        return encoding, text, word_count, chapters

    def _parse_epub(self, content: bytes) -> Tuple[str, str, int, List[Dict[str, Any]]]:
        """解析 EPUB 格式电子书。直接使用 zipfile 解析，避免 ebooklib 的路径问题。"""
        import io
        import zipfile
        import xml.etree.ElementTree as ET

        try:
            zf = zipfile.ZipFile(io.BytesIO(content))
            
            container_content = zf.read('META-INF/container.xml').decode('utf-8')
            root = ET.fromstring(container_content)
            
            ns = {'c': 'urn:oasis:names:tc:opendocument:xmlns:container'}
            rootfile_elem = root.find('.//c:rootfile', ns)
            if rootfile_elem is None:
                logger.error("[EbookLibrary] EPUB 解析失败: 找不到 rootfile")
                zf.close()
                return "utf-8", "", 0, []
            
            opf_path = rootfile_elem.get('full-path')
            
            opf_content = zf.read(opf_path).decode('utf-8')
            opf_root = ET.fromstring(opf_content)
            
            ns = {
                'opf': 'http://www.idpf.org/2007/opf',
                'dc': 'http://purl.org/dc/elements/1.1/'
            }
            
            spine_elem = opf_root.find('.//opf:spine', ns)
            if spine_elem is None:
                logger.error("[EbookLibrary] EPUB 解析失败: 找不到 spine")
                zf.close()
                return "utf-8", "", 0, []
            
            manifest = {}
            for item in opf_root.findall('.//opf:manifest/opf:item', ns):
                manifest[item.get('id')] = item.get('href')
            
            all_text = []
            chapters = []
            
            for itemref in spine_elem.findall('.//opf:itemref', ns):
                item_id = itemref.get('idref')
                if item_id not in manifest:
                    continue
                
                href = manifest[item_id]
                if not href:
                    continue
                
                if not href.startswith('/') and '/' in opf_path:
                    base_path = opf_path.rsplit('/', 1)[0]
                    full_path = f"{base_path}/{href}"
                else:
                    full_path = href
                
                try:
                    chapter_content = zf.read(full_path).decode('utf-8')
                except KeyError:
                    try:
                        chapter_content = zf.read(href).decode('utf-8')
                    except KeyError:
                        continue
                
                text = self._clean_html_content(chapter_content.encode('utf-8'))
                if not text.strip():
                    continue
                
                word_count = self._count_words(text)
                if word_count < 50:
                    continue
                
                title = self._extract_chapter_title(chapter_content, href, len(chapters) + 1)
                
                if self._is_non_chapter(title, word_count):
                    continue
                
                all_text.append(text)
                chapters.append({
                    "chapter_index": len(chapters) + 1,
                    "title": title,
                    "start_pos": 0,
                    "end_pos": 0,
                    "content": text,
                    "word_count": word_count,
                })
            
            zf.close()
            
            full_text = "\n\n".join(all_text)
            word_count = self._count_words(full_text)
            
            if not chapters:
                chapters.append({
                    "chapter_index": 1,
                    "title": "正文",
                    "start_pos": 0,
                    "end_pos": 0,
                    "content": full_text,
                    "word_count": word_count,
                })

            logger.info(f"[EbookLibrary] EPUB 解析完成: {len(chapters)} 个章节")
            return "utf-8", full_text, word_count, chapters

        except Exception as e:
            logger.error(f"[EbookLibrary] EPUB 解析失败: {e}")
            return "utf-8", "", 0, []

    def _extract_chapter_title(self, html_content: str, href: str, index: int) -> str:
        """从 HTML 内容中提取章节标题。"""
        import re
        
        title_patterns = [
            r'<h1[^>]*>(.*?)</h1>',
            r'<h2[^>]*>(.*?)</h2>',
            r'<h3[^>]*>(.*?)</h3>',
            r'<title[^>]*>(.*?)</title>',
        ]
        
        for pattern in title_patterns:
            match = re.search(pattern, html_content, re.IGNORECASE | re.DOTALL)
            if match:
                title = match.group(1).strip()
                title = re.sub(r'<[^>]+>', '', title)
                title = title.replace('\n', ' ').replace('\r', '').strip()
                title = title.replace('§§', '').strip()
                if title and len(title) < 100:
                    return title
        
        fallback = href.replace(".xhtml", "").replace(".html", "").replace("/", "_").strip()
        if fallback:
            return fallback
        return f"章节{index}"

    def _is_non_chapter(self, title: str, word_count: int) -> bool:
        """判断是否为非正文章节（版权页、目录等）。"""
        non_chapter_keywords = [
            '版权', '版权信息', 'copyright', 'contents', '目录', '前言', '序言',
            '写在基石之前', '序', 'introduction', 'foreword', 'preface',
            'titlepage', 'cover', 'unknown', '未知'
        ]
        title_lower = title.lower()
        for keyword in non_chapter_keywords:
            if keyword.lower() in title_lower:
                return True
        if word_count < 100:
            return True
        return False

    def _clean_html_content(self, content: bytes) -> str:
        """清理 HTML 内容，提取纯文本。"""
        try:
            from html.parser import HTMLParser
        except ImportError:
            return content.decode("utf-8", errors="replace")

        class TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.text = []
                self.in_title = False
            
            def handle_starttag(self, tag, attrs):
                if tag in ('h1', 'h2', 'h3', 'title'):
                    self.in_title = True
            
            def handle_endtag(self, tag):
                if tag in ('h1', 'h2', 'h3', 'title'):
                    self.in_title = False
            
            def handle_data(self, data):
                if data.strip():
                    self.text.append(data.strip())
            
            def get_text(self):
                return "\n\n".join(self.text)

        try:
            parser = TextExtractor()
            parser.feed(content.decode("utf-8", errors="replace"))
            parser.close()
            text = parser.get_text()
            
            text = text.replace('§§', '')
            
            lines = text.split('\n')
            cleaned_lines = []
            skip_until_chapter = True
            first_chapter_line = False
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                if line == '未知':
                    continue
                
                if re.match(r'^第\s*[一二三四五六七八九十百千零〇两\d]+\s*[章回节卷篇]', line):
                    skip_until_chapter = False
                    first_chapter_line = True
                    continue
                
                if not skip_until_chapter:
                    cleaned_lines.append(line)
            
            if not cleaned_lines:
                cleaned_lines = lines
            
            return "\n\n".join(cleaned_lines)
        
        except Exception:
            return content.decode("utf-8", errors="replace")

    def _decode_text(self, content: bytes) -> Tuple[str, Optional[str]]:
        """尝试多种编码解码文本。返回 (encoding, text)。"""
        # 优先检测 BOM
        if content.startswith(b"\xef\xbb\xbf"):
            try:
                return "utf-8-sig", content[3:].decode("utf-8")
            except UnicodeDecodeError:
                pass
        if content.startswith(b"\xff\xfe") or content.startswith(b"\xfe\xff"):
            try:
                return "utf-16", content.decode("utf-16")
            except UnicodeDecodeError:
                pass

        for enc in _ENCODINGS:
            try:
                return enc, content.decode(enc)
            except UnicodeDecodeError:
                continue
        # 全部失败，用 latin-1 兜底（不会抛异常）
        return "latin-1", content.decode("latin-1")

    def _count_words(self, text: str) -> int:
        """统计字数：中文按字符计，英文按单词计，取两者之和的近似值。"""
        # 中文字符数
        cn_count = len(re.findall(r"[\u4e00-\u9fff]", text))
        # 英文单词数
        en_count = len(re.findall(r"[a-zA-Z]+", text))
        return cn_count + en_count

    def _split_chapters(self, content: bytes, text: str, encoding: str) -> List[Dict[str, Any]]:
        """拆分章节。

        策略：逐行扫描，匹配到章节标题则记录一个章节。start_pos/end_pos
        记录的是章节正文在原始字节流中的偏移（便于后续直接 seek 读取，
        无需重新解码整个文件）。

        若全文未匹配到任何章节标题，则将整本书作为单个章节（标题"正文"）。
        """
        lines = text.splitlines(keepends=True)
        # 预计算每行在原始字节流中的偏移
        line_offsets: List[int] = []
        offset = 0
        for line in lines:
            line_offsets.append(offset)
            offset += len(line.encode(encoding))

        chapters: List[Dict[str, Any]] = []
        current_title: Optional[str] = None
        current_start_line: Optional[int] = None

        def _match_title(line: str) -> Optional[str]:
            stripped = line.strip()
            if not stripped:
                return None
            for pattern in _CHAPTER_PATTERNS:
                if pattern.match(stripped):
                    return stripped
            return None

        def _flush(end_line: int):
            """将当前累积的章节写入 chapters。"""
            if current_title is None or current_start_line is None:
                return
            start_pos = line_offsets[current_start_line]
            end_pos = line_offsets[end_line] if end_line < len(line_offsets) else len(content)
            chapter_text = "".join(lines[current_start_line:end_line])
            chapters.append({
                "chapter_index": len(chapters) + 1,
                "title": current_title,
                "start_pos": start_pos,
                "end_pos": end_pos,
                "word_count": self._count_words(chapter_text),
            })

        for i, line in enumerate(lines):
            title = _match_title(line)
            if title is not None:
                _flush(i)
                current_title = title
                current_start_line = i

        _flush(len(lines))

        # 未匹配到任何章节标题，整本书作为一个章节
        if not chapters:
            chapters.append({
                "chapter_index": 1,
                "title": "正文",
                "start_pos": 0,
                "end_pos": len(content),
                "word_count": self._count_words(text),
            })

        return chapters

    # ===================== 查询 =====================

    def list_books(self, page: int = 1, page_size: int = 10,
                   keyword: Optional[str] = None) -> Dict[str, Any]:
        """分页获取电子书列表。"""
        result = get_ebooks_paged(page=page, page_size=page_size, keyword=keyword)
        # 附加章节计数
        for book in result["books"]:
            book["chapter_count"] = get_chapter_count(book["id"])
            book["created_at_str"] = self._format_time(book.get("created_at"))
        return result

    def get_book(self, book_id: int) -> Optional[Dict[str, Any]]:
        """获取电子书详情。"""
        book = get_ebook(book_id)
        if book is None:
            return None
        book["chapter_count"] = get_chapter_count(book_id)
        book["created_at_str"] = self._format_time(book.get("created_at"))
        book["updated_at_str"] = self._format_time(book.get("updated_at"))
        return book

    def list_chapters(self, book_id: int) -> List[Dict[str, Any]]:
        """获取电子书的章节列表。

        优先返回剧本中的章节列表，如果没有剧本则返回原始电子书章节列表。
        """
        from repositories import get_script_chapters_all

        scripts = get_scripts_by_book(book_id)
        for script in scripts:
            script_chapters = get_script_chapters_all(script["id"])
            if script_chapters:
                return [
                    {
                        "book_id": book_id,
                        "chapter_index": ch["chapter_index"],
                        "title": ch["title"],
                        "start_pos": 0,
                        "end_pos": 0,
                        "word_count": ch.get("word_count", 0),
                        "content": "",
                        "created_at": ch.get("created_at", 0),
                    }
                    for ch in script_chapters
                ]

        chapters = get_chapters(book_id)
        return chapters

    def get_chapter_content(self, book_id: int, chapter_index: int) -> Optional[Dict[str, Any]]:
        """读取指定章节的内容。

        优先返回剧本中修改后的章节内容，如果没有剧本或剧本中没有修改，则返回原始电子书内容。
        
        对于 TXT 格式：通过 start_pos/end_pos 直接 seek 读取原始文件的对应字节段。
        对于 EPUB/MOBI/AZW3 格式：直接从数据库的 content 字段读取。
        """
        book = get_ebook(book_id)
        if book is None:
            return None
        chapter = get_chapter(book_id, chapter_index)
        if chapter is None:
            return None

        scripts = get_scripts_by_book(book_id)
        for script in scripts:
            script_chapter = get_script_chapter(script["id"], chapter_index)
            if script_chapter and script_chapter.get("file_path"):
                script_file_info = self._media.get_file_by_path(script_chapter["file_path"])
                if script_file_info:
                    try:
                        with open(script_file_info["absolute_path"], "r", encoding="utf-8") as f:
                            script_content = f.read()
                        if script_content.strip():
                            return {
                                "book_id": book_id,
                                "book_title": book["title"],
                                "chapter_index": chapter["chapter_index"],
                                "chapter_title": chapter["title"],
                                "content": script_content,
                                "word_count": len(script_content),
                            }
                    except Exception as e:
                        logger.warning(f"[EbookLibrary] 读取剧本章节内容失败: {e}")

        chapter_content = chapter.get("content", "")
        if chapter_content:
            return {
                "book_id": book_id,
                "book_title": book["title"],
                "chapter_index": chapter["chapter_index"],
                "chapter_title": chapter["title"],
                "content": chapter_content,
                "word_count": chapter.get("word_count", 0),
            }

        file_info = self._media.get_file_by_path(book["file_path"])
        if file_info is None:
            return None

        try:
            with open(file_info["absolute_path"], "rb") as f:
                f.seek(chapter["start_pos"])
                raw = f.read(chapter["end_pos"] - chapter["start_pos"])
        except Exception as e:
            logger.warning(f"[EbookLibrary] 读取章节内容失败: {e}")
            return None

        encoding = book.get("encoding", "utf-8")
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="replace")

        return {
            "book_id": book_id,
            "book_title": book["title"],
            "chapter_index": chapter["chapter_index"],
            "chapter_title": chapter["title"],
            "content": text,
            "word_count": chapter["word_count"],
        }

    def delete_book(self, book_id: int) -> Tuple[bool, str]:
        """删除电子书：删除数据库记录与物理文件。"""
        book = get_ebook(book_id)
        if book is None:
            return False, "电子书不存在"

        file_info = self._media.get_file_by_path(book["file_path"])
        deleted = delete_ebook(book_id)
        if not deleted:
            return False, "删除失败"

        # 删除物理文件
        if file_info and os.path.exists(file_info["absolute_path"]):
            try:
                os.remove(file_info["absolute_path"])
            except Exception as e:
                logger.warning(f"[EbookLibrary] 删除物理文件失败: {e}")

        logger.info(f"[EbookLibrary] 已删除电子书: {book['title']} (id={book_id})")
        return True, f"已删除电子书: {book['title']}"

    @staticmethod
    def _format_time(ts: Optional[float]) -> str:
        if not ts:
            return ""
        try:
            return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
        except Exception:
            return ""


_ebook_library_service: Optional[EbookLibraryService] = None


def get_ebook_library_service() -> EbookLibraryService:
    global _ebook_library_service
    if _ebook_library_service is None:
        _ebook_library_service = EbookLibraryService()
    return _ebook_library_service
