"""支持下拉刷新的容器组件。

结构: [刷新指示器] + [ScrollView]
在 ScrollView 顶部下拉时,指示器高度随下拉距离增长,
释放后若超过阈值则触发刷新回调,并播放收起动画。

Kivy 坐标系 y 轴向上,手指向下滑动时 touch.y < touch.oy,
因此下拉距离 = touch.oy - touch.y(正值表示向下拉)。
"""

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.graphics import Color, Rectangle
from kivy.animation import Animation
from kivy.clock import Clock

from .top_widgets import COLORS, _FONT_NAME


class _RefreshIndicator(BoxLayout):
    """下拉刷新指示器:文字 + 背景,高度随下拉距离变化。"""

    def __init__(self, **kwargs):
        super().__init__(orientation="horizontal", **kwargs)
        self.padding = [0, 8]

        with self.canvas.before:
            Color(*COLORS["bg_card"])
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)

        self._label = Label(
            text="下拉刷新",
            font_name=_FONT_NAME,
            font_size=13,
            color=COLORS["text_secondary"],
            halign="center",
            valign="middle",
        )
        self._label.bind(size=lambda i, v: setattr(i, "text_size", v))
        self.add_widget(self._label)

    def set_pull(self, pull, threshold):
        """下拉中:根据距离更新高度和文字。"""
        self.height = min(pull, threshold * 1.5)
        if pull >= threshold:
            self._label.text = "释放立即刷新"
            self._label.color = COLORS["text_primary"]
        else:
            self._label.text = "下拉刷新"
            self._label.color = COLORS["text_secondary"]

    def start_refresh(self):
        """刷新中:固定高度,显示加载文字。"""
        Animation.cancel_all(self)
        self.height = 50
        self._label.text = "正在刷新..."
        self._label.color = COLORS["text_primary"]

    def collapse(self):
        """收起:动画高度归零。"""
        anim = Animation(height=0, duration=0.3, t="out_quad")
        anim.bind(
            on_complete=lambda *a: setattr(self._label, "text", "下拉刷新")
        )
        anim.start(self)

    def _update_bg(self, instance, value):
        self._bg.pos = instance.pos
        self._bg.size = instance.size


class PullToRefreshView(BoxLayout):
    """下拉刷新容器。

    参数:
        refresh_callback: 下拉刷新回调函数
        threshold: 触发刷新的下拉距离阈值(像素),默认 80
    """

    def __init__(self, refresh_callback=None, threshold=80, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self._refresh_callback = refresh_callback
        self._threshold = threshold
        self._refreshing = False
        self._at_top_on_down = False
        self._pulling = False

        # 刷新指示器(顶部,高度可变)
        self._indicator = _RefreshIndicator(size_hint=(1, None), height=0)
        super().add_widget(self._indicator)

        # 内部 ScrollView(填充剩余空间)
        self._scroll = ScrollView(do_scroll_x=False, size_hint=(1, 1))
        super().add_widget(self._scroll)

    @property
    def scroll_y(self):
        return self._scroll.scroll_y

    @scroll_y.setter
    def scroll_y(self, value):
        self._scroll.scroll_y = value

    @property
    def do_scroll_y(self):
        return self._scroll.do_scroll_y

    @do_scroll_y.setter
    def do_scroll_y(self, value):
        self._scroll.do_scroll_y = value

    def add_content(self, widget):
        """添加内容到 ScrollView。"""
        self._scroll.add_widget(widget)

    def on_touch_down(self, touch):
        if self._refreshing:
            return True
        self._at_top_on_down = self._scroll.scroll_y >= 0.99
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if self._refreshing:
            return True
        if self._at_top_on_down and self._scroll.scroll_y >= 0.99:
            # Kivy y 轴向上,手指向下滑时 touch.oy > touch.y
            pull = touch.oy - touch.y
            if pull > 0:
                self._pulling = True
                self._indicator.set_pull(pull, self._threshold)
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if self._refreshing:
            return True
        if self._at_top_on_down and self._scroll.scroll_y >= 0.99:
            pull = touch.oy - touch.y
            if pull > self._threshold:
                self._trigger_refresh()
                return True
        if self._pulling:
            self._indicator.collapse()
            self._pulling = False
        return super().on_touch_up(touch)

    def _trigger_refresh(self):
        """触发刷新:显示加载状态,延迟执行回调,完成后收起。"""
        if not self._refresh_callback or self._refreshing:
            return
        self._refreshing = True
        self._pulling = False
        self._indicator.start_refresh()
        # 延迟执行刷新回调,给用户视觉反馈
        Clock.schedule_once(self._do_refresh, 0.5)

    def _do_refresh(self, dt):
        """执行刷新回调。"""
        try:
            self._refresh_callback()
        finally:
            Clock.schedule_once(self._finish_refresh, 0.3)

    def _finish_refresh(self, dt):
        """完成刷新:收起指示器。"""
        self._refreshing = False
        self._indicator.collapse()
        self._scroll.scroll_y = 1.0


__all__ = ["PullToRefreshView"]
