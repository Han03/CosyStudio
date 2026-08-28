import uvicorn
import sys
import os
import threading
import socket

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.paths import APP_NAME

HOST = "0.0.0.0"


def get_server_port():
    """从配置文件获取服务端口"""
    try:
        from core.config_manager import get_server_port
        return get_server_port()
    except:
        return 8000


def get_local_ip():
    """获取本机局域网IP地址"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return "127.0.0.1"


def start_uvicorn():
    """在守护线程中运行 uvicorn 服务。"""
    port = get_server_port()
    local_ip = get_local_ip()
    
    print("=" * 60)
    print(f"{APP_NAME} 服务启动信息")
    print("=" * 60)
    print(f"服务端口: {port}")
    print(f"本地访问: http://localhost:{port}")
    print(f"本机访问: http://{local_ip}:{port}")
    print(f"局域网访问: http://{local_ip}:{port}")
    print("=" * 60)
    
    uvicorn.run("main:app", host=HOST, port=port, reload=False, workers=1)


def start_kivy(server_thread):
    """在主线程中运行 Kivy 界面;Kivy 未安装时回退为阻塞等待服务线程。"""
    try:
        from kivy_app import run_kivy_app
    except ImportError as e:
        print(f"[start_server] Kivy 首页模块导入失败,错误信息: {e}。")
        if server_thread is not None:
            server_thread.join()
        return
    run_kivy_app(server_thread=server_thread)


if __name__ == "__main__":
    try:
        from hot_reload import start_watching
        start_watching()
    except ImportError:
        print("[start_server] hot_reload 模块不可用,跳过热重载")

    # 守护线程运行 uvicorn,主线程运行 Kivy (GUI 通常需在主线程)
    server_thread = threading.Thread(target=start_uvicorn, daemon=True)
    server_thread.start()
    start_kivy(server_thread)
