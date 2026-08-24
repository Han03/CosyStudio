"""CosyChat Kivy 服务端日志界面。

布局(水平):
  - 右侧:ScreenManager 内容区域

首页内容:
  - 壁纸背景(必应壁纸作为背景,不拉伸,底部添加过渡效果)
  - 顶部:TopBar(更多按钮 + 系统通知)
"""

import logging
import traceback

from kivy.uix.label import Label
from kivy.config import Config
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.graphics import Color, Rectangle
from kivy.uix.floatlayout import FloatLayout

from widgets.top_widgets import COLORS

logger = logging.getLogger(__name__)

# 窗口尺寸(桌面端布局)
SIDE_NAV_WIDTH = 72
WINDOW_WIDTH = 960
WINDOW_HEIGHT = 600

Config.set("graphics", "width", str(WINDOW_WIDTH))
Config.set("graphics", "height", str(WINDOW_HEIGHT))
Config.set("graphics", "resizable", "0")


class HomePage(Screen):
    """首页:壁纸背景 + 日志。
    """

    def __init__(self,  **kwargs):
        super().__init__(**kwargs)
        self.name = "home"

        root = FloatLayout(size_hint=(1, 1))

        with root.canvas.before:
            Color(*COLORS["bg"])
            self._bg_rect = Rectangle(pos=root.pos, size=root.size)
        root.bind(pos=self._update_bg, size=self._update_bg)


        # 可滚动内容区
        self.content_box = BoxLayout(
            orientation="vertical", size_hint=(1, 1), spacing=0
        )
        self.content_box.bind(minimum_height=self.content_box.setter("height"))

        # 构建首页内容
        self._build_content()
        root.add_widget(self.content_box)

        self.add_widget(root)

    def _build_content(self):
        """构建首页内容组件。"""
        from widgets.top_widgets import TopBar, _resolve_icon
        from widgets.wallpaper_hero import WallpaperHero
        from widgets.log_viewer import LogViewer

        home_container = FloatLayout(size_hint=(1, 1))

        self.wallpaper_hero = WallpaperHero()
        self.wallpaper_hero.pos_hint = {"top": 1.0, "left": 0}
        home_container.add_widget(self.wallpaper_hero)
        top_bar = TopBar()
        top_bar.pos_hint = {"top": 1.0, "left": 0}
        home_container.add_widget(top_bar)

        self.log_viewer = LogViewer()
        self.log_viewer.pos_hint = {"center_x": 0.5, "center_y": 0.5}
        self.log_viewer.size_hint = (0.9, 0.8)
        home_container.add_widget(self.log_viewer)

        self.content_box.add_widget(home_container)


    def _update_bg(self, instance, value):
        self._bg_rect.pos = instance.pos
        self._bg_rect.size = instance.size


class CosyChatApp(App):
    """CosyChat 服务端日志界面 - 暗色系界面。
    """

    def __init__(self, server_thread=None, **kwargs):
        super().__init__(**kwargs)
        self.server_thread = server_thread
        self._current_nav_index = 0

    def build(self):
        try:
            self.title = "CosyChat 服务端"
            root = BoxLayout(orientation="horizontal", size_hint=(1, 1))
            self.screen_manager = ScreenManager(size_hint=(1, 1))
            self.home_page = HomePage()
            self.screen_manager.add_widget(self.home_page)
            root.add_widget(self.screen_manager)

            return root
        except Exception as e:
            logger.warning(f"[Kivy] 设置应用标题失败: {e}")
            error_stack = traceback.format_exc()
            return Label(text=error_stack)

    def _on_nav_switch(self, index):
       
        target_names = ["home"]
        if not (0 <= index < len(target_names)):
            return
        if index == self._current_nav_index:
            return

        direction = "up" if index > self._current_nav_index else "down"
        self.screen_manager.transition = SlideTransition(direction=direction)
        self.screen_manager.current = target_names[index]
        self._current_nav_index = index

    def on_stop(self):
        """应用停止时关闭服务器线程。"""
        if self.server_thread and self.server_thread.is_alive():
            logger.info("[Kivy] 正在关闭服务...")


def run_kivy_app(server_thread=None):
    """启动 Kivy 应用。"""
    app = CosyChatApp(server_thread=server_thread)
    app.run()