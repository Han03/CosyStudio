from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.clock import Clock

from .top_widgets import COLORS, _FONT_NAME


class LogViewer(BoxLayout):
    """实时日志查看器组件。

    功能:
      - 通过日志管理器获取实时日志
      - 自动滚动到最新日志
      - 支持最大行数限制
      - 暗色系主题适配
    """

    MAX_LINES = 500

    def __init__(self, **kwargs):
        self.scroll_view = None
        self.log_label = None
        self._lines = []
        self._log_callback = None

        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.size_hint = (1, 1)

        self._build_ui()
        self._setup_logging()

    def _build_ui(self):
        """构建日志查看器UI。"""
        header = BoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=40,
            padding=[16, 8],
        )
        header_label = Label(
            text="系统日志",
            font_name=_FONT_NAME,
            font_size=16,
            color=COLORS["text_primary"],
            size_hint=(1, 1),
            halign="left",
            valign="center",
        )
        header_label.text_size = header_label.size
        header.add_widget(header_label)
        self.add_widget(header)

        self.scroll_view = ScrollView(
            size_hint=(1, 1),
            bar_width=6,
            bar_color=COLORS["text_dark"],
            bar_inactive_color=COLORS["text_dark"],
        )

        self.log_label = Label(
            text="",
            font_name=_FONT_NAME,
            font_size=14,
            color=COLORS["text_secondary"],
            size_hint_y=None,
            halign="left",
            valign="top",
            text_size=(None, None),
            markup=False,
            padding=[12, 12, 12, 24],
        )

        self.log_label.bind(size=self._on_log_label_size)
        self.scroll_view.add_widget(self.log_label)
        self.add_widget(self.scroll_view)

        with self.canvas.before:
            from kivy.graphics import Color, RoundedRectangle

            Color(*COLORS["bg_card_tansprent"])
            self._bg_rect = RoundedRectangle(
                pos=self.pos, size=self.size, radius=[12]
            )
        self.bind(pos=self._update_bg, size=self._update_bg)

    def _on_log_label_size(self, instance, value):
        """Label尺寸变化时更新text_size宽度。

        仅在 ScrollView 宽度变化时重新设置 text_size，使文字能正确换行。
        高度更新与滚动到底部的逻辑统一在 _on_new_log 中处理，
        避免在 size 回调里调整 height 引发递归触发。
        """
        if(self.scroll_view is None or self.log_label is None):
            return

        self.log_label.text_size = (
            self.scroll_view.width - 32,
            None,
        )

    def _update_bg(self, instance, value):
        self._bg_rect.pos = instance.pos
        self._bg_rect.size = instance.size

    def _setup_logging(self):
        """设置日志捕获 - 使用日志管理器回调。"""
        from utils.logger import log_manager
        import time

        history = log_manager.get_recent_logs(limit=100)
        for log_entry in history:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(log_entry["timestamp"]))
            self._lines.append(f"{timestamp} [{log_entry['level']}] {log_entry['message']}")

        if self.log_label:
            self.log_label.text = "\n".join(self._lines)
            # 初始化后更新高度并滚动到底部
            self._update_label_height()
            Clock.schedule_once(self._scroll_to_bottom, 0.05)

        def log_callback(log_entry):
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(log_entry["timestamp"]))
            msg = f"{timestamp} [{log_entry['level']}] {log_entry['message']}"
            Clock.schedule_once(lambda dt, m=msg: self._on_new_log(m), 0)

        self._log_callback = log_callback
        log_manager.add_ws_callback(log_callback)

    def _update_label_height(self):
        """根据当前文本与 padding 重新计算 Label 高度。

        texture_size[1] 反映当前文本的实际像素高度，
        加上上下 padding 得到 Label 的最终高度，确保最后一行完全可见。
        不允许高度小于 ScrollView 高度，避免空内容时的滚动异常。
        """
        if not hasattr(self, "log_label") or not hasattr(self, "scroll_view"):
            return
        pad_top = self.log_label.padding[1]
        pad_bottom = self.log_label.padding[3]
        new_height = self.log_label.texture_size[1] + pad_top + pad_bottom
        new_height = max(new_height, self.scroll_view.height)
        self.log_label.height = new_height

    def _on_new_log(self, message):
        """收到新日志时更新显示。

        追加新日志后，调用共享的 _update_label_height 方法更新高度，
        并用 Clock 调度下一帧滚动到底部。
        仅当用户当前已在底部附近时才自动滚动，避免强制拉回
        正在查看历史的用户。
        """
        self._lines.append(message)
        if len(self._lines) > self.MAX_LINES:
            self._lines = self._lines[-self.MAX_LINES :]

        if not hasattr(self, "log_label") or not hasattr(self, "scroll_view"):
            return

        self.log_label.text = "\n".join(self._lines)
        self._update_label_height()

        # 下一帧滚动到底部，确保高度已生效
        Clock.schedule_once(self._scroll_to_bottom, 0.01)

    def _scroll_to_bottom(self, dt):
        """滚动到日志底部。

        仅当 ScrollView 当前已在底部附近（scroll_y 较小）
        时才自动滚动到底部；若用户正在查看历史日志
        （scroll_y 较大），则保持当前位置不强制拉回。
        """
        if not hasattr(self, "scroll_view"):
            return

        # scroll_y 接近 0 表示已在底部附近，此时允许跟随新日志
        if self.scroll_view.scroll_y > 0.02:
            return

        self.scroll_view.scroll_y = 0

    def on_kv_post(self, base_widget):
        """组件初始化完成后调用。"""
        super().on_kv_post(base_widget)
        if(self.log_label is None or self.scroll_view is None):
            return
        self.log_label.text_size = (
            self.scroll_view.width - 32,
            None,
        )

    def on_detach(self):
        """组件移除时清理日志回调。"""
        if self._log_callback:
            from utils.logger import log_manager
            log_manager.remove_ws_callback(self._log_callback)
            self._log_callback = None
