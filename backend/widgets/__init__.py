"""CosyWritter Kivy 桌面端自定义组件模块。

每个组件一个文件,便于维护和扩展。
"""

from .top_widgets import COLORS, _FONT_NAME, apply_theme, _icon_image, TopBar
from .wallpaper_hero import WallpaperHero
from .unread_mail import UnreadMailBadge
from .pull_to_refresh import PullToRefreshView
from .log_viewer import LogViewer

__all__ = [
    "COLORS",
    "_FONT_NAME",
    "apply_theme",
    "_icon_image",
    "TopBar",
    "WallpaperHero",
    "UnreadMailBadge",
    "PullToRefreshView",
    "LogViewer",
]
