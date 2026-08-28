"""CosyWritter Kivy 桌面端基础组件。

提供全局主题 COLORS、字体注册、图标 Image 工厂 _icon_image,
以及 TopBar 等基础容器组件。
"""

import os
import webbrowser
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image
from kivy.uix.widget import Widget
from kivy.core.text import LabelBase
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.label import Label
from core.paths import APP_NAME

_ICONS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "icons",
)

# 暗色系主题颜色(参考读书软件配色:深黑背景 + 红色强调)
COLORS = {
    "bg": (0.1, 0.1, 0.1, 1),
    "bg_card": (0.2, 0.2, 0.22, 0.95),
    "bg_card_tansprent": (0.2, 0.2, 0.22, 0.65),
    "bg_card_light": (0.25, 0.25, 0.28, 0.9),
    "text_primary": (1, 1, 1, 1),
    "text_secondary": (0.65, 0.65, 0.7, 1),
    "text_dark": (0.45, 0.45, 0.5, 1),
    "accent": (1, 0.3, 0.3, 1),
    "accent_light": (1, 0.5, 0.5, 1),
    "success": (0.3, 0.8, 0.4, 1),
    "warning": (1, 0.65, 0.2, 1),
}

_FONT_PATH = r"C:\Windows\Fonts\msyh.ttc"
_FONT_NAME = "msyh" if os.path.exists(_FONT_PATH) else "Roboto"
if os.path.exists(_FONT_PATH):
    LabelBase.register(name="msyh", fn_regular=_FONT_PATH)


def apply_theme(theme_dict):
    """更新 COLORS 主题颜色(dict 的 value 可以是 list 或 tuple)。"""
    for key, value in theme_dict.items():
        if isinstance(value, (list, tuple)):
            COLORS[key] = tuple(value)


def _resolve_icon(icon_ref):
    """将图标引用解析为绝对路径。

    icon_ref 可以是:
      - 绝对路径: 直接返回
      - 文件名(含 .png): 拼 assets/icons/ 目录
      - 名称(不含后缀): 自动补 .png
    """
    if not icon_ref:
        return ""
    if os.path.isabs(icon_ref):
        return icon_ref
    if not icon_ref.lower().endswith(".png"):
        icon_ref = icon_ref + ".png"
    return os.path.join(_ICONS_DIR, icon_ref)


def _icon_image(icon_ref, size=24, color=None, **kwargs):
    """根据图标文件名构建 Image 组件。

    color 不为 None 时通过 color 属性着色(需要白色 PNG 源图)。
    """
    if not icon_ref:
        return Widget(size_hint=(None, None), size=(size, size))
    img = Image(
        source=_resolve_icon(icon_ref),
        size_hint=(None, None),
        size=(size, size),
        **kwargs,
    )
    if color is not None:
        img.color = color
    return img


class TopBar(BoxLayout):
    """顶部导航栏:首页按钮 + 标题 + 移动端图标。"""

    def __init__(self, **kwargs):
        from .unread_mail import UnreadMailBadge

        super().__init__(**kwargs)
        self.orientation = "horizontal"
        self.size_hint = (1, None)
        self.height = 60
        self.padding = [18, 12]
        self.spacing = 12

        class _HomeBtn(ButtonBehavior, BoxLayout):
            def on_cursor_enter(self, *args):
                self.cursor = "hand"

            def on_cursor_leave(self, *args):
                self.cursor = "arrow"

        home_container = _HomeBtn(
            orientation="horizontal",
            size_hint=(None, None),
            size=(160, 40),
            spacing=8,
            pos_hint={"center_y": 0.5},
        )
        home_container.bind(on_press=self._on_home_click)

        from kivy.uix.image import Image as _Img

        home_icon = _Img(
            source=_resolve_icon("home.png"),
            size_hint=(None, None),
            size=(29, 29),
            color=COLORS["text_primary"],
            pos_hint={"center_y": 0.5},
        )
        home_container.add_widget(home_icon)

        title_label = Label(
            text=APP_NAME,
            font_name=_FONT_NAME,
            font_size=18,
            color=COLORS["text_primary"],
            size_hint=(None, None),
            size=(120, 28),
            halign="left",
            valign="center",
            pos_hint={"center_y": 0.5},
        )
        title_label.text_size = title_label.size
        home_container.add_widget(title_label)

        self.add_widget(home_container)

        self.add_widget(Widget(size_hint=(1, 1)))

        self.unread_badge = UnreadMailBadge()
        self.add_widget(self.unread_badge)

    def _on_home_click(self, instance):
        try:
            from core.config_manager import get_server_port
            port = get_server_port()
        except:
            port = 8000
        webbrowser.open(f"http://localhost:{port}/index.html")


__all__ = ["COLORS", "_FONT_NAME", "apply_theme", "_icon_image", "TopBar"]
