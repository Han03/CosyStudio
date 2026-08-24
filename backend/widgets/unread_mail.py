"""移动端图标组件。

显示移动端图标,点击跳转移动端首页。
"""

import webbrowser
from kivy.uix.floatlayout import FloatLayout
from kivy.graphics import Color, Ellipse
from kivy.uix.image import Image
from kivy.uix.behaviors import ButtonBehavior

from .top_widgets import COLORS, _resolve_icon


class UnreadMailBadge(FloatLayout):
    """移动端图标组件:移动端图标 + 可点击跳转。"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (None, 1)
        self.width = 40

        class _MobileBtn(ButtonBehavior, Image):
            def on_cursor_enter(self, *args):
                self.cursor = "hand"

            def on_cursor_leave(self, *args):
                self.cursor = "arrow"

        self._icon = _MobileBtn(
            source=_resolve_icon("mobile.png"),
            size_hint=(None, None),
            size=(29, 29),
            color=COLORS["text_primary"],
            pos_hint={"center_x": 0.5, "center_y": 0.5},
        )
        self._icon.bind(on_press=self._on_mobile_click)
        self.add_widget(self._icon)

        self.bind(pos=self._update_badge, size=self._update_badge)
        self._update_badge()

    def _update_badge(self, *args):
        pass

    def _on_mobile_click(self, instance):
        try:
            from core.config_manager import get_server_port
            port = get_server_port()
        except:
            port = 8000
        webbrowser.open(f"http://localhost:{port}/mobile.html")

    def set_count(self, count):
        pass


__all__ = ["UnreadMailBadge"]
