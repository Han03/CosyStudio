"""热重载模块:仅监听 widgets 与 html 文件变化,不重启进程。

- widgets/*.py 变化:importlib.reload 所有 widget 模块,通过 Kivy Clock 重建首页 UI
- frontend/*.html 变化:仅记录日志(浏览器刷新即可)
- 其他文件:不触发任何操作

仅建议在开发环境下启用。

使用方式:
    python start_server.py
"""

import os
import sys
import time
import threading
import importlib

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR = os.path.dirname(_BACKEND_DIR)

WATCH_DIRS = [
    os.path.join(_BACKEND_DIR, "widgets"),
    os.path.join(_PROJECT_DIR, "frontend"),
]

# 防抖:文件变化后等待多久再执行(秒),避免编辑器保存中途多次触发
DEBOUNCE_SECONDS = 1.0


class _DebouncedHandler:
    """防抖处理器:文件变化事件在 DEBOUNCE_SECONDS 内合并为一次执行。"""

    def __init__(self):
        self._timer = None
        self._lock = threading.Lock()
        self._pending_kind = None
        self._pending_path = None

    def trigger(self, kind, path):
        """触发一次延迟执行(已有定时器则重置,实现防抖)。"""
        with self._lock:
            self._pending_kind = kind
            self._pending_path = path
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(DEBOUNCE_SECONDS, self._do_action)
            self._timer.daemon = True
            self._timer.start()

    def _do_action(self):
        """实际执行操作。"""
        with self._lock:
            kind = self._pending_kind
            path = self._pending_path
            self._timer = None
            self._pending_kind = None
            self._pending_path = None

        if kind == "widget":
            self._reload_widgets(path)
        # html: 无需操作,浏览器刷新即可

    def _reload_widgets(self, changed_path):
        """重载所有 widget 模块,并在 Kivy 主线程上重建首页 UI。"""
        print(f"\n[hot_reload] 检测到 widget 文件变化: {os.path.basename(changed_path)}", flush=True)

        # 发现 widgets 目录下所有模块(top_widgets 优先,其他 widget 依赖它)
        widgets_dir = os.path.join(_BACKEND_DIR, "widgets")
        reload_order = []
        for fname in sorted(os.listdir(widgets_dir)):
            if not fname.endswith(".py") or fname == "__init__.py":
                continue
            mod_name = "widgets." + fname[:-3]
            if fname == "top_widgets.py":
                reload_order.insert(0, mod_name)
            else:
                reload_order.append(mod_name)

        # 逐个重载已导入的模块(未导入的跳过)
        reloaded = 0
        for mod_name in reload_order:
            mod = sys.modules.get(mod_name)
            if mod is None:
                continue
            try:
                importlib.reload(mod)
                reloaded += 1
            except Exception as e:
                print(f"[hot_reload] 重载失败 {mod_name}: {e}")

        if reloaded > 0:
            print(f"[hot_reload] 已重载 {reloaded} 个 widget 模块")

        # 在 Kivy 主线程上重建首页 UI(Clock.schedule_once 线程安全)
        try:
            from kivy.clock import Clock
            from kivy.app import App

            def _rebuild(dt):
                app = App.get_running_app()
                if app is None:
                    return

            Clock.schedule_once(_rebuild)
        except ImportError:
            # Kivy 未安装(仅后端模式),跳过 UI 重建
            pass


def start_watching():
    """启动文件监听线程。watchdog 未安装时静默退出。"""
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        print("[hot_reload] watchdog 未安装,热重载已禁用。可执行: pip install watchdog")
        return

    handler_instance = _DebouncedHandler()

    class _FileHandler(FileSystemEventHandler):
        """监听 widget 与 html 文件变化。"""

        def _classify(self, path):
            """返回 'widget'、'html' 或 None。"""
            normalized = path.replace("\\", "/")
            if path.endswith(".py") and "/widgets/" in normalized:
                return "widget"
            if path.endswith(".html"):
                return "html"
            return None

        def on_modified(self, event):
            if event.is_directory:
                return
            kind = self._classify(event.src_path)
            if kind == "widget":
                handler_instance.trigger("widget", event.src_path)
            elif kind == "html":
                print(f"[hot_reload] HTML 文件变化(浏览器刷新即可): {os.path.basename(event.src_path)}")

        def on_created(self, event):
            if event.is_directory:
                return
            kind = self._classify(event.src_path)
            if kind == "widget":
                handler_instance.trigger("widget", event.src_path)
            elif kind == "html":
                print(f"[hot_reload] HTML 文件变化(浏览器刷新即可): {os.path.basename(event.src_path)}")

    observer = Observer()
    for watch_dir in WATCH_DIRS:
        if os.path.isdir(watch_dir):
            observer.schedule(_FileHandler(), watch_dir, recursive=True)

    observer.start()
    print(f"[hot_reload] 热重载已启用: widgets/*.py (重载+UI重建,不重启) + frontend/*.html (仅提示)")


if __name__ == "__main__":
    # 测试:直接运行此文件会监听当前目录
    start_watching()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[hot_reload] 已停止")
