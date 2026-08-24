import sys
import os
import json
import time
import threading
import logging
import traceback
from utils.common_utils import get_directory_size

from core.paths import LOG_DIR

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, 'download.log'), encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger('download_model')


def _read_status_file(status_file_path):
    if not os.path.exists(status_file_path):
        return {}
    try:
        with open(status_file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error("读取状态文件失败: %s, file = %s", e, status_file_path)
        return {}


def _write_status_file(status_file_path, data):
    data["timestamp"] = time.time()
    _persist_data = {}
    if os.path.exists(status_file_path):
        try:
            with open(status_file_path, 'r', encoding='utf-8') as f:
                _persist_data = json.load(f)
        except Exception as e:
            logger.error("读取状态文件失败: %s, file = %s", e, status_file_path)
            _persist_data = {}
    _persist_data.update(data)
    with open(status_file_path, 'w', encoding='utf-8') as f:
        json.dump(_persist_data, f, indent=2, ensure_ascii=False)
    return


def download_model(model_name, save_dir, status_file_path, source="modelscope", stop_event=None, on_status_update=None):
    """
    下载模型的核心函数，可直接代码调用。

    Args:
        model_name: 模型名称（如 Qwen/Qwen2-0.5B-Instruct）
        save_dir: 保存目录
        status_file_path: 状态文件路径
        source: 下载源（modelscope 或 huggingface）
        stop_event: threading.Event，用于取消下载
        on_status_update: 状态更新回调函数，接收 status dict 作为参数

    Returns:
        dict: {"success": bool, "path": str, "error": str}
    """
    if stop_event is None:
        stop_event = threading.Event()

    logger.info("=" * 60)
    logger.info("下载任务启动")
    logger.info("模型名称: %s", model_name)
    logger.info("保存目录: %s", save_dir)
    logger.info("状态文件: %s", status_file_path)
    logger.info("下载源: %s", source)

    def update_status(data):
        _write_status_file(status_file_path, data)
        if on_status_update:
            try:
                on_status_update(data)
            except Exception as e:
                logger.error("状态更新回调异常: %s", e)

    os.makedirs(save_dir, exist_ok=True)
    logger.info("保存目录已创建")

    previous_size = 0
    total_size_estimate = 0
    download_error = None
    is_canceled = False
    result = None
    progress_stop_event = threading.Event()

    def _check_cancel_signal():
        nonlocal is_canceled
        logger.info("取消信号检查线程启动")
        while not progress_stop_event.is_set():
            try:
                if stop_event.is_set():
                    logger.info("[下载线程] 检测到取消信号（stop_event）")
                    is_canceled = True
                    return
                status = _read_status_file(status_file_path)
                if status.get("status") == "canceled":
                    logger.info("[下载线程] 检测到取消信号（状态文件）")
                    is_canceled = True
                    stop_event.set()
                    return
            except Exception as e:
                logger.info("检查取消信号失败: %s", e)
            time.sleep(1)
        logger.info("取消信号检查线程停止")

    def update_progress_loop():
        nonlocal previous_size, total_size_estimate
        logger.info("进度更新线程启动")
        last_update_time = time.time()
        last_size = 0
        while not progress_stop_event.is_set():
            try:
                current_size = get_directory_size(save_dir)
                current_time = time.time()

                if current_size > previous_size:
                    previous_size = current_size

                    time_diff = current_time - last_update_time
                    if time_diff > 0 and current_size > last_size:
                        speed_bytes_per_sec = (current_size - last_size) / time_diff
                    else:
                        speed_bytes_per_sec = 0
                    last_update_time = current_time
                    last_size = current_size

                    if total_size_estimate > 0:
                        progress = min(99, int(current_size / total_size_estimate * 100))
                        remaining_bytes = total_size_estimate - current_size
                        if speed_bytes_per_sec > 0:
                            eta_seconds = remaining_bytes / speed_bytes_per_sec
                        else:
                            eta_seconds = 0
                    else:
                        progress = min(99, int(current_size / (3 * 1024 * 1024 * 1024) * 100))
                        eta_seconds = 0

                    if speed_bytes_per_sec < 1024:
                        speed_str = f"{speed_bytes_per_sec:.0f} B/s"
                    elif speed_bytes_per_sec < 1024 * 1024:
                        speed_str = f"{speed_bytes_per_sec / 1024:.1f} KB/s"
                    else:
                        speed_str = f"{speed_bytes_per_sec / (1024 * 1024):.1f} MB/s"

                    if eta_seconds > 0:
                        if eta_seconds < 60:
                            eta_str = f"剩余 {eta_seconds:.0f} 秒"
                        elif eta_seconds < 3600:
                            eta_str = f"剩余 {eta_seconds / 60:.1f} 分钟"
                        else:
                            eta_str = f"剩余 {eta_seconds / 3600:.1f} 小时"
                    else:
                        eta_str = "计算中..."

                    status_data = {
                        "status": "downloading",
                        "progress": progress,
                        "message": f"正在下载... {progress}%",
                        "model_name": model_name,
                        "downloaded_bytes": current_size,
                        "total_bytes": total_size_estimate,
                        "speed": speed_bytes_per_sec,
                        "speed_str": speed_str,
                        "eta": eta_seconds,
                        "eta_str": eta_str,
                        "path": save_dir
                    }
                    try:
                        update_status(status_data)
                        logger.info("进度更新: %d%% (%d bytes, %s)", progress, current_size, speed_str)
                    except Exception as e:
                        logger.error("写入状态文件失败: %s", e)
            except Exception as e:
                logger.error("进度更新异常: %s", e)
            time.sleep(2)
        logger.info("进度更新线程停止")

    cancel_thread = threading.Thread(target=_check_cancel_signal, daemon=True)
    cancel_thread.start()
    logger.info("取消信号检查线程已启动")

    progress_thread = threading.Thread(target=update_progress_loop, daemon=True)
    progress_thread.start()
    logger.info("进度线程已启动")

    def _download_func():
        nonlocal result, download_error, is_canceled
        try:
            if source.lower() == "huggingface":
                logger.info("使用 huggingface 下载源")
                logger.info("尝试导入 huggingface_hub...")
                from huggingface_hub import snapshot_download
                logger.info("成功导入 snapshot_download")

                logger.info("开始下载模型: %s", model_name)
                logger.info("调用 snapshot_download，参数: local_dir=%s", save_dir)

                result = snapshot_download(
                    model_name,
                    local_dir=save_dir,
                    local_dir_use_symlinks=False,
                )

                logger.info("下载完成，结果路径: %s", result)
            else:
                logger.info("使用 modelscope 下载源")
                logger.info("尝试导入 modelscope...")
                import modelscope
                logger.info("modelscope 版本: %s", modelscope.__version__)

                from modelscope import snapshot_download
                logger.info("成功导入 snapshot_download")

                logger.info("开始下载模型: %s", model_name)
                logger.info("调用 snapshot_download，参数: local_dir=%s", save_dir)

                result = snapshot_download(
                    model_name,
                    local_dir=save_dir,
                )

                logger.info("下载完成，结果路径: %s", result)
        except Exception as e:
            if is_canceled or stop_event.is_set():
                logger.info("下载因取消而中断")
            else:
                logger.error("下载异常: %s", e)
                logger.error("完整堆栈:\n%s", traceback.format_exc())
                download_error = str(e)

    logger.info("下载无超时限制")

    download_thread = threading.Thread(target=_download_func, daemon=True)
    download_thread.start()

    while download_thread.is_alive():
        if is_canceled or stop_event.is_set():
            logger.info("收到取消信号，等待下载线程退出...")
            download_thread.join(timeout=10)
            is_canceled = True
            break
        time.sleep(0.5)

    progress_stop_event.set()
    cancel_thread.join(timeout=5)
    progress_thread.join(timeout=5)

    if is_canceled:
        logger.info("下载已被取消")
        final_size = get_directory_size(save_dir)
        logger.info("取消时已下载大小: %d bytes", final_size)

        status = {
            "status": "canceled",
            "message": "下载已取消",
        }
        try:
            update_status(status)
        except Exception as e:
            logger.error("写入取消状态失败: %s", e)

        return {"success": False, "error": "下载已取消", "canceled": True}

    if download_error:
        logger.error(f"下载失败: {download_error}")
        status = {
            "status": "error",
            "message": f"下载失败: {download_error}",
            "error": download_error,
        }
        try:
            update_status(status)
        except Exception as e:
            logger.error("写入错误状态失败: %s", e)

        return {"success": False, "error": download_error}

    if result is None:
        logger.error("下载结果为空")
        status = {
            "status": "error",
            "message": "下载结果为空",
            "error": "下载结果为空",
        }
        try:
            update_status(status)
        except Exception as e:
            logger.error("写入状态失败: %s", e)

        return {"success": False, "error": "下载结果为空"}

    final_size = get_directory_size(save_dir)
    logger.info("最终文件大小: %d bytes", final_size)

    status = {
        "status": "ready",
        "progress": 100,
        "message": "下载完成",
        "size_bytes": final_size,
        "total_bytes": final_size
    }
    try:
        update_status(status)
        logger.info("写入完成状态")
    except Exception as e:
        logger.error("写入完成状态失败: %s", e)

    logger.info("下载任务正常结束")
    return {"success": True, "message": f"模型 {model_name} 下载成功", "path": result}


def main():
    logger.info("=" * 60)
    logger.info("下载进程启动")

    if len(sys.argv) < 4:
        logger.error("参数不足，期望至少4个参数，实际: %d", len(sys.argv))
        print(json.dumps({"success": False, "error": "参数不足"}))
        sys.exit(1)

    model_name = sys.argv[1]
    save_dir = sys.argv[2]
    status_file_path = sys.argv[3]
    source = sys.argv[4] if len(sys.argv) > 4 else "modelscope"

    result = download_model(model_name, save_dir, status_file_path, source)

    if result.get("success"):
        print(json.dumps({"success": True, "message": result.get("message", ""), "path": result.get("path", "")}))
        sys.exit(0)
    else:
        print(json.dumps({"success": False, "error": result.get("error", "下载失败")}))
        sys.exit(1)


if __name__ == "__main__":
    main()
