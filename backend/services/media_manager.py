"""媒体文件管理器。

目录结构:
  media/{category}/{module}/{filename}
  例如: media/image/bing/bing_2026-07-04.jpg

category: note/audio/image/video/document (顶层分类)
module: 子目录,用于区分不同模块产生的文件(如 bing, tts, chat 等)
"""

import os
from typing import List, Dict, Optional, Tuple
from datetime import datetime

MEDIA_CATEGORIES = {
    "note": {
        "name": "笔记",
        "icon": "fa-sticky-note",
        "extensions": [".txt"],
        "description": "文本笔记文件"
    },
    "audio": {
        "name": "音频",
        "icon": "fa-volume-up",
        "extensions": [".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg"],
        "description": "音频文件"
    },
    "image": {
        "name": "图片",
        "icon": "fa-image",
        "extensions": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"],
        "description": "图片文件"
    },
    "video": {
        "name": "视频",
        "icon": "fa-video",
        "extensions": [".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv"],
        "description": "视频文件"
    },
    "document": {
        "name": "文档",
        "icon": "fa-file-alt",
        "extensions": [".txt", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".md", ".srt", ".epub"],
        "description": "文档文件"
    }
}

# 模块名 -> 中文显示名的映射
MODULE_NAMES = {
    "bing": "必应壁纸",
    "tts": "语音合成",
    "chat": "对话",
    "call": "通话",
    "avatar": "形象",
    "user": "用户上传",
}


class MediaManager:
    def __init__(self, base_dir: str):
        self.base_dir = os.path.abspath(base_dir)
        self._ensure_dirs()

    def _ensure_dirs(self):
        for category in MEDIA_CATEGORIES:
            dir_path = os.path.join(self.base_dir, category)
            os.makedirs(dir_path, exist_ok=True)

    def _get_category_dir(self, category: str) -> str:
        if category not in MEDIA_CATEGORIES:
            raise ValueError(f"不支持的分类: {category}")
        return os.path.join(self.base_dir, category)

    def _get_module_dir(self, category: str, module: str) -> str:
        return os.path.join(self._get_category_dir(category), module)

    def _is_valid_extension(self, filename: str, category: str) -> bool:
        ext = os.path.splitext(filename)[1].lower()
        valid_exts = MEDIA_CATEGORIES[category]["extensions"]
        return ext in valid_exts

    def _get_module_display_name(self, module: str) -> str:
        return MODULE_NAMES.get(module, module)

    def _get_file_info(self, filepath: str, category: str, module: str) -> Dict:
        filename = os.path.basename(filepath)
        stat = os.stat(filepath)
        ext = os.path.splitext(filename)[1].lower()

        size_bytes = stat.st_size
        if size_bytes < 1024:
            size_str = f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            size_str = f"{size_bytes / 1024:.1f} KB"
        else:
            size_str = f"{size_bytes / (1024 * 1024):.1f} MB"

        relative_path = f"{category}/{module}/{filename}"

        return {
            "name": filename,
            "category": category,
            "category_name": MEDIA_CATEGORIES[category]["name"],
            "module": module,
            "module_name": self._get_module_display_name(module),
            "extension": ext,
            "size": size_bytes,
            "size_str": size_str,
            "relative_path": relative_path,
            "absolute_path": filepath,
            "modified_time": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "created_time": datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S"),
            "icon": MEDIA_CATEGORIES[category]["icon"]
        }

    def _scan_module_files(self, category: str, module_dir: str, module: str,
                           keyword: Optional[str] = None) -> List[Dict]:
        """扫描单个模块目录下的文件。"""
        files = []
        if not os.path.isdir(module_dir):
            return files

        for filename in os.listdir(module_dir):
            filepath = os.path.join(module_dir, filename)
            if not os.path.isfile(filepath):
                continue

            if not self._is_valid_extension(filename, category):
                continue

            if keyword and keyword.lower() not in filename.lower():
                continue

            files.append(self._get_file_info(filepath, category, module))

        return files

    def list_files(
        self,
        category: Optional[str] = None,
        module: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        keyword: Optional[str] = None,
        sort_by: str = "modified_time",
        sort_order: str = "desc"
    ) -> Tuple[List[Dict], int, int]:
        all_files = []

        categories = [category] if category else list(MEDIA_CATEGORIES.keys())

        for cat in categories:
            if cat not in MEDIA_CATEGORIES:
                continue
            cat_dir = self._get_category_dir(cat)
            if not os.path.exists(cat_dir):
                continue

            if module:
                # 指定模块,只扫描该模块目录
                mod_dir = os.path.join(cat_dir, module)
                all_files.extend(
                    self._scan_module_files(cat, mod_dir, module, keyword)
                )
            else:
                # 未指定模块,扫描分类下所有模块子目录
                for entry_name in os.listdir(cat_dir):
                    entry_path = os.path.join(cat_dir, entry_name)
                    if os.path.isdir(entry_path):
                        all_files.extend(
                            self._scan_module_files(cat, entry_path, entry_name, keyword)
                        )
                    elif os.path.isfile(entry_path):
                        # 兼容旧格式:直接放在分类根目录下的文件,module 设为 "default"
                        if self._is_valid_extension(entry_name, cat):
                            if not keyword or keyword.lower() in entry_name.lower():
                                all_files.append(
                                    self._get_file_info(entry_path, cat, "default")
                                )

        if sort_by == "name":
            all_files.sort(key=lambda x: x["name"], reverse=(sort_order == "desc"))
        elif sort_by == "size":
            all_files.sort(key=lambda x: x["size"], reverse=(sort_order == "desc"))
        elif sort_by == "modified_time":
            all_files.sort(key=lambda x: x["modified_time"], reverse=(sort_order == "desc"))
        else:
            all_files.sort(key=lambda x: x["name"], reverse=(sort_order == "desc"))

        total = len(all_files)
        total_pages = (total + page_size - 1) // page_size

        start = (page - 1) * page_size
        end = start + page_size
        files_page = all_files[start:end]

        return files_page, total, total_pages

    def get_modules(self, category: Optional[str] = None) -> List[Dict]:
        """获取模块列表。

        返回每个模块的 key、显示名、文件数量。
        如果指定 category,只返回该分类下的模块;否则返回所有分类的模块。
        """
        modules_dict = {}

        categories = [category] if category else list(MEDIA_CATEGORIES.keys())

        for cat in categories:
            if cat not in MEDIA_CATEGORIES:
                continue
            cat_dir = self._get_category_dir(cat)
            if not os.path.exists(cat_dir):
                continue

            for entry_name in os.listdir(cat_dir):
                entry_path = os.path.join(cat_dir, entry_name)
                if os.path.isdir(entry_path):
                    module = entry_name
                    if module not in modules_dict:
                        modules_dict[module] = {
                            "key": module,
                            "name": self._get_module_display_name(module),
                            "count": 0,
                        }
                    # 统计该模块下的文件数
                    count = 0
                    for fname in os.listdir(entry_path):
                        fpath = os.path.join(entry_path, fname)
                        if os.path.isfile(fpath) and self._is_valid_extension(fname, cat):
                            count += 1
                    modules_dict[module]["count"] += count

        return list(modules_dict.values())

    def get_file_by_path(self, relative_path: str) -> Optional[Dict]:
        parts = relative_path.split('/')
        if len(parts) < 2:
            return None

        category = parts[0]
        if category not in MEDIA_CATEGORIES:
            return None

        if len(parts) == 2:
            # 旧格式: category/filename -> 使用 default 模块
            module = "default"
            filename = parts[1]
        else:
            # 新格式: category/module/filename
            module = parts[1]
            filename = '/'.join(parts[2:])

        mod_dir = self._get_module_dir(category, module)
        filepath = os.path.join(mod_dir, filename)

        if not os.path.exists(filepath) or not os.path.isfile(filepath):
            return None

        if not self._is_valid_extension(filename, category):
            return None

        return self._get_file_info(filepath, category, module)

    def get_file_content(self, relative_path: str) -> Optional[bytes]:
        file_info = self.get_file_by_path(relative_path)
        if not file_info:
            return None

        try:
            with open(file_info["absolute_path"], "rb") as f:
                return f.read()
        except Exception:
            return None

    def get_categories(self) -> List[Dict]:
        result = []
        for key, info in MEDIA_CATEGORIES.items():
            cat_dir = self._get_category_dir(key)
            count = 0
            if os.path.exists(cat_dir):
                for entry in os.listdir(cat_dir):
                    entry_path = os.path.join(cat_dir, entry)
                    if os.path.isdir(entry_path):
                        # 模块目录:统计目录内文件
                        for fname in os.listdir(entry_path):
                            fpath = os.path.join(entry_path, fname)
                            if os.path.isfile(fpath) and self._is_valid_extension(fname, key):
                                count += 1
                    elif os.path.isfile(entry_path):
                        if self._is_valid_extension(entry, key):
                            count += 1

            result.append({
                "key": key,
                "name": info["name"],
                "icon": info["icon"],
                "description": info["description"],
                "count": count
            })
        return result

    def ensure_module_dir(self, category: str, module: str) -> str:
        """确保指定分类下的模块目录存在,返回目录路径。"""
        mod_dir = self._get_module_dir(category, module)
        os.makedirs(mod_dir, exist_ok=True)
        return mod_dir

    def save_file(self, module: str, filename: str, content: bytes,
                  category: Optional[str] = None) -> str:
        """保存文件到媒体管理器。

        参数:
            module: 模块名(如 bing, wiki, tts 等)
            filename: 文件名(含扩展名)
            content: 文件内容(bytes)
            category: 分类(可选),如果不指定则根据文件扩展名自动推断

        返回:
            文件的相对路径(category/module/filename)

        自动推断分类规则:
            .jpg, .jpeg, .png, .gif, .bmp, .webp, .svg -> image
            .wav, .mp3, .flac, .m4a, .aac, .ogg -> audio
            .mp4, .avi, .mov, .mkv, .flv, .wmv -> video
            .txt, .md -> note
            .pdf, .doc, .docx, .xls, .xlsx, .ppt, .pptx -> document
        """
        if category is None:
            ext = os.path.splitext(filename)[1].lower()
            category = self._infer_category(ext)

        if category not in MEDIA_CATEGORIES:
            raise ValueError(f"不支持的分类: {category}")

        mod_dir = self.ensure_module_dir(category, module)
        filepath = os.path.join(mod_dir, filename)

        with open(filepath, "wb") as f:
            f.write(content)

        relative_path = f"{category}/{module}/{filename}"
        return relative_path

    def _infer_category(self, ext: str) -> str:
        """根据文件扩展名推断分类。"""
        ext = ext.lower()

        if ext in [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"]:
            return "image"
        elif ext in [".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg"]:
            return "audio"
        elif ext in [".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv"]:
            return "video"
        elif ext in [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".srt"]:
            return "document"
        elif ext in [".txt", ".md"]:
            return "note"
        else:
            return "note"

    def get_file_path(self, module: str, filename: str,
                      category: Optional[str] = None) -> str:
        """获取文件的绝对路径。"""
        if category is None:
            ext = os.path.splitext(filename)[1].lower()
            category = self._infer_category(ext)

        mod_dir = self._get_module_dir(category, module)
        return os.path.join(mod_dir, filename)

    def file_exists(self, module: str, filename: str,
                    category: Optional[str] = None) -> bool:
        """检查文件是否存在。"""
        filepath = self.get_file_path(module, filename, category)
        return os.path.exists(filepath) and os.path.isfile(filepath)


_media_manager = None


def get_media_manager() -> MediaManager:
    global _media_manager
    if _media_manager is None:
        base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "media")
        _media_manager = MediaManager(base_dir)
    return _media_manager
