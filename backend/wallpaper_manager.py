"""Bing 每日壁纸管理器。

通过 Bing HPImageArchive API 获取最近 7 天的壁纸,下载到 media/image/bing/ 目录
(媒体管理器的 image 分类下的 bing 模块),并使用 wallpapers.json 元数据文件记录所有已缓存的壁纸。
壁纸文件直接放在 media/image/bing/ 目录,可被媒体管理器识别和浏览。

特性:
- 缓存目录: media/image/bing/(文件名 bing_YYYY-MM-DD.jpg)
- 元数据: media/image/bing/wallpapers.json
- 一次拉取最近 7 天的壁纸(API n=7)
- 自动补全最近 7 天内缺失的日期
- 自动删除 7 天前的旧缓存
- 提供按日期从新到旧排序的壁纸列表
"""

import os
import json
import threading
import urllib.request
import urllib.error
from datetime import datetime, timedelta

from utils.logger import logger


class WallpaperManager:
    """Bing 每日壁纸获取、缓存、管理。"""

    BING_API = "https://cn.bing.com/HPImageArchive.aspx?format=js&idx=0&n=7&mkt=zh-CN"
    BING_BASE = "https://cn.bing.com"
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

    CACHE_DAYS = 7
    FILE_PREFIX = "bing_"
    MODULE_NAME = "bing"

    def __init__(self, base_dir=None):
        from services.media_manager import get_media_manager

        self._media_mgr = get_media_manager()
        self.image_dir = self._media_mgr.ensure_module_dir("image", self.MODULE_NAME)
        self.metadata_path = os.path.join(self.image_dir, "wallpapers.json")
        self._lock = threading.Lock()
        self.metadata = self._load_metadata()

    def _load_metadata(self):
        default = {"wallpapers": []}
        if not os.path.exists(self.metadata_path):
            return default
        try:
            with open(self.metadata_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "wallpapers" not in data:
                data["wallpapers"] = []
            return data
        except Exception as e:
            logger.warning(f"[壁纸] 加载元数据失败: {e}")
            return default

    def _save_metadata(self):
        try:
            tmp_path = self.metadata_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.metadata, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.metadata_path)
        except Exception as e:
            logger.warning(f"[壁纸] 保存元数据失败: {e}")

    @staticmethod
    def _today_str():
        return datetime.now().strftime("%Y-%m-%d")

    @staticmethod
    def _date_str(d):
        return d.strftime("%Y-%m-%d")

    def _get_cached_dates(self):
        """返回已缓存的日期集合。"""
        dates = set()
        for w in self.metadata.get("wallpapers", []):
            path = os.path.join(self.image_dir, w.get("filename", ""))
            if w.get("date") and os.path.exists(path):
                dates.add(w["date"])
        return dates

    def get_recent_wallpapers(self, count=7):
        """返回最近 count 天的壁纸列表,按日期从新到旧排序。

        只包含文件实际存在的壁纸。
        """
        all_wallpapers = []
        for w in self.metadata.get("wallpapers", []):
            path = os.path.join(self.image_dir, w.get("filename", ""))
            if os.path.exists(path):
                all_wallpapers.append(w)

        all_wallpapers.sort(key=lambda x: x.get("date", ""), reverse=True)
        return all_wallpapers[:count]

    def get_current_wallpaper_path(self):
        """返回最新缓存壁纸的本地路径,不存在则返回 None。"""
        recent = self.get_recent_wallpapers(1)
        if not recent:
            return None
        return os.path.join(self.image_dir, recent[0]["filename"])

    def get_current_wallpaper_info(self):
        """返回最新壁纸的元信息 dict,无则返回 None。"""
        recent = self.get_recent_wallpapers(1)
        return recent[0] if recent else None

    def fetch_recent_wallpapers(self):
        """拉取最近 7 天的壁纸,补全缺失,清理过期。

        返回成功下载的壁纸数量。
        """
        with self._lock:
            # 从 Bing API 拉取最近 7 天
            try:
                api_url = f"{self.BING_API}&_={int(datetime.now().timestamp())}"
                req = urllib.request.Request(
                    api_url, headers={"User-Agent": self.USER_AGENT}
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except (urllib.error.URLError, json.JSONDecodeError) as e:
                logger.warning(f"[壁纸] 调用 Bing API 失败: {e}")
                return 0
            except Exception as e:
                logger.warning(f"[壁纸] 调用 Bing API 异常: {e}")
                return 0

            images = data.get("images", [])
            if not images:
                logger.warning("[壁纸] Bing API 未返回图片")
                return 0

            # 将 API 返回的图片按 enddate 索引
            api_by_date = {}
            for img in images:
                enddate = img.get("enddate", "")
                if len(enddate) == 8:
                    date_str = f"{enddate[:4]}-{enddate[4:6]}-{enddate[6:8]}"
                else:
                    date_str = self._today_str()
                api_by_date[date_str] = img

            cached_dates = self._get_cached_dates()
            today = datetime.now().date()
            downloaded = 0

            # 遍历最近 7 天,补全缺失的日期
            for i in range(self.CACHE_DAYS):
                target_date = today - timedelta(days=i)
                date_str = self._date_str(target_date)

                if date_str in cached_dates:
                    continue

                if date_str not in api_by_date:
                    continue

                img = api_by_date[date_str]
                url = self.BING_BASE + img.get("url", "")
                title = img.get("title", "")
                copyright_text = img.get("copyright", "")
                if not url:
                    continue

                filename = f"bing_{date_str}.jpg"
                local_path = os.path.join(self.image_dir, filename)
                if not self._download_image(url, local_path):
                    continue

                entry = {
                    "date": date_str,
                    "filename": filename,
                    "url": url,
                    "title": title,
                    "copyright": copyright_text,
                    "cached_at": datetime.now().isoformat(),
                }
                self.metadata["wallpapers"].append(entry)
                downloaded += 1
                logger.info(f"[壁纸] 已缓存 {date_str}: {title}")

            # 清理过期缓存(超过 7 天的)
            self._cleanup_old_wallpapers(today)

            if downloaded > 0:
                self._save_metadata()
                logger.info(f"[壁纸] 本次新增 {downloaded} 张,共缓存 {len(self._get_cached_dates())} 张")

            return downloaded

    def _cleanup_old_wallpapers(self, today):
        """删除超过 CACHE_DAYS 天的旧壁纸。"""
        cutoff = today - timedelta(days=self.CACHE_DAYS)
        kept = []
        removed_count = 0

        for w in self.metadata.get("wallpapers", []):
            date_str = w.get("date", "")
            try:
                d = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                kept.append(w)
                continue

            if d < cutoff:
                # 删除文件
                path = os.path.join(self.image_dir, w.get("filename", ""))
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except Exception as e:
                    logger.warning(f"[壁纸] 删除过期文件失败 {path}: {e}")
                removed_count += 1
            else:
                kept.append(w)

        if removed_count > 0:
            self.metadata["wallpapers"] = kept
            logger.info(f"[壁纸] 清理过期壁纸 {removed_count} 张")

    def _download_image(self, url, path):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": self.USER_AGENT})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
            if not data:
                logger.warning("[壁纸] 下载图片数据为空")
                return False
            with open(path, "wb") as f:
                f.write(data)
            return True
        except Exception as e:
            logger.warning(f"[壁纸] 下载图片失败: {e}")
            return False

    # 兼容旧接口
    def is_today_wallpaper_cached(self):
        today = self._today_str()
        return today in self._get_cached_dates()

    def fetch_today_wallpaper(self):
        """兼容旧接口:拉取最近 7 天壁纸,返回今日壁纸路径。"""
        self.fetch_recent_wallpapers()
        return self.get_current_wallpaper_path()
