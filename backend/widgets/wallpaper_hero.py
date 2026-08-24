"""每日必应壁纸组件。

显示 Bing 每日推荐壁纸,底部偏下位置展示壁纸标题和作者(类似 Bing 首页)。
组件内部管理 WallpaperManager,支持最近 7 天壁纸循环播放(从新到旧,每 10 秒切换),
切换时使用渐隐渐现动画过渡。
"""

import os
import threading

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.graphics import Color, Rectangle
from kivy.animation import Animation
from kivy.clock import Clock

from .top_widgets import _FONT_NAME

_SWITCH_INTERVAL = 10
_FADE_DURATION = 0.8


class WallpaperHero(BoxLayout):
    """每日必应壁纸区域,底部显示标题和作者。

    特性:
    - 循环播放最近 7 天的 Bing 壁纸(从新到旧)
    - 每 10 秒自动切换一张
    - 切换时使用渐隐渐现动画
    - 组件内部持有 WallpaperManager
    """

    def __init__(self, base_dir=None, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.size_hint = (1, 1)
        info_height = 96
        title_font_size = 22
        author_font_size = 14

        # 初始化壁纸管理器
        if base_dir is None:
            base_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "..",
                "media",
            )
        from wallpaper_manager import WallpaperManager
        self._wallpaper_mgr = WallpaperManager(base_dir)

        # 壁纸播放列表
        self._wallpaper_list = self._wallpaper_mgr.get_recent_wallpapers(7)
        self._current_index = 0
        self._switch_event = None
        self._fade_anim = None

        # 背景:双层 Color + Rectangle 实现渐隐渐现
        with self.canvas.before:
            # 底层(新图):始终完全不透明
            self._color_bottom = Color(1, 1, 1, 1)
            self._bg_bottom = Rectangle(source="", pos=self.pos, size=self.size)
            # 顶层(旧图):透明度可动画
            self._color_top = Color(1, 1, 1, 1)
            self._bg_top = Rectangle(source="", pos=self.pos, size=self.size)

        # 渐变蒙层
        with self.canvas:
            self.gradient_start = Color(0, 0, 0, 0)
            self.gradient_end = Color(0, 0, 0, 0.7)
            self.fade_rect = Rectangle(pos=self.pos, size=self.size)

        self.bind(pos=self._update_bg, size=self._update_bg)

        # 底部信息区域(标题 + 作者)
        info_layout = BoxLayout(
            orientation="vertical",
            size_hint=(1, None),
            height=info_height,
            padding=[24, 18],
            spacing=6,
        )
        self._title_label = Label(
            text="",
            font_name=_FONT_NAME,
            font_size=title_font_size,
            color=(1, 1, 1, 1),
            bold=True,
            size_hint=(1, 0.5),
            halign="right",
            valign="bottom",
        )
        self._title_label.bind(
            size=lambda instance, val: setattr(instance, "text_size", val)
        )
        self._author_label = Label(
            text="",
            font_name=_FONT_NAME,
            font_size=author_font_size,
            color=(0.8, 0.8, 0.9, 0.8),
            size_hint=(1, 0.5),
            halign="right",
            valign="top",
        )
        self._author_label.bind(
            size=lambda instance, val: setattr(instance, "text_size", val)
        )
        info_layout.add_widget(self._title_label)
        info_layout.add_widget(self._author_label)
        self.add_widget(info_layout)

        # 显示第一张壁纸(如果有缓存)
        self._show_wallpaper(0, animate=False)

        # 若缓存中已有多张壁纸,立即启动自动切换
        self._start_auto_switch()

        # 启动后后台拉取壁纸
        Clock.schedule_once(self._start_fetch_thread, 0.1)

    def _start_fetch_thread(self, dt):
        threading.Thread(target=self._fetch_wallpapers, daemon=True).start()

    def _fetch_wallpapers(self):
        """后台线程:拉取最近 7 天壁纸,完成后刷新播放列表。"""
        self._wallpaper_mgr.fetch_recent_wallpapers()
        # 无论是否有新下载,都刷新播放列表(确保定时器启动)
        Clock.schedule_once(self._refresh_playlist, 0)

    def _refresh_playlist(self, dt):
        """刷新播放列表并(重新)启动轮播。"""
        new_list = self._wallpaper_mgr.get_recent_wallpapers(7)
        if not new_list:
            return

        # 如果当前没有壁纸,直接显示第一张
        if not self._wallpaper_list:
            self._wallpaper_list = new_list
            self._current_index = 0
            self._show_wallpaper(0, animate=False)
        else:
            self._wallpaper_list = new_list
            # 确保当前索引有效
            if self._current_index >= len(new_list):
                self._current_index = 0

        # 启动/重启自动切换
        self._start_auto_switch()

    def _start_auto_switch(self):
        """启动自动切换定时器。"""
        if len(self._wallpaper_list) <= 1:
            return
        if self._switch_event:
            self._switch_event.cancel()
        self._switch_event = Clock.schedule_interval(
            self._switch_to_next, _SWITCH_INTERVAL
        )

    def _switch_to_next(self, dt):
        """切换到下一张壁纸(从新到旧循环)。"""
        if len(self._wallpaper_list) <= 1:
            return
        next_idx = (self._current_index + 1) % len(self._wallpaper_list)
        self._show_wallpaper(next_idx, animate=True)

    def _show_wallpaper(self, index, animate=False):
        """显示指定索引的壁纸。"""
        if not self._wallpaper_list or index >= len(self._wallpaper_list):
            return

        self._current_index = index
        wp = self._wallpaper_list[index]
        path = os.path.join(self._wallpaper_mgr.image_dir, wp["filename"])
        title = wp.get("title", "")
        copyright_text = wp.get("copyright", "")

        if animate:
            # 渐隐渐现:bottom 显示新图(始终不透明),top 从 1.0 渐隐到 0.0
            self._bg_bottom.source = path
            # 先重置顶层为完全不透明,然后动画渐隐
            self._color_top.a = 1.0
            anim = Animation(a=0.0, duration=_FADE_DURATION, t="in_out_quad")
            self._fade_anim = anim
            anim.start(self._color_top)
            # 动画结束后:顶层切到新图并恢复不透明,为下一次切换做准备
            def _on_complete(*args):
                self._bg_top.source = path
                self._color_top.a = 1.0
            anim.bind(on_complete=_on_complete)
        else:
            # 无动画:直接显示
            self._bg_bottom.source = path
            self._bg_top.source = path
            self._color_top.a = 1.0

        # 更新文字信息
        self._title_label.text = title
        self._author_label.text = copyright_text

    def _update_bg(self, instance, value):
        self._bg_bottom.pos = instance.pos
        self._bg_bottom.size = instance.size
        self._bg_top.pos = instance.pos
        self._bg_top.size = instance.size
        if self.fade_rect:
            self.fade_rect.pos = instance.pos
            self.fade_rect.size = instance.size

    def update_wallpaper(self, path, info=None):
        """外部手动更新壁纸(兼容旧接口)。"""
        self._bg_bottom.source = path
        self._bg_top.source = path
        self._color_top.a = 1.0
        if info:
            self._title_label.text = info.get("title", "")
            self._author_label.text = info.get("copyright", "")

    def on_stop(self):
        """清理定时器。"""
        if self._switch_event:
            self._switch_event.cancel()
            self._switch_event = None
        if self._fade_anim:
            self._fade_anim.stop_all(self._color_top)
            self._fade_anim = None


__all__ = ["WallpaperHero"]
