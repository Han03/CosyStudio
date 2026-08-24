import os
import time
import json
import ctypes
import numpy as np
import asyncio

from utils.logger import logger
from core.global_manager import global_manager

AUDIO_HEADER_MARK = b"OMNI_AUDIO:"

# Windows 默认定时器精度为 15.6ms，会导致 asyncio.sleep(0.01) 实际睡 15.6ms，
# 在流式音频场景下增加 ~100ms 的首音延迟。此处将精度提升到 1ms。
try:
    ctypes.windll.winmm.timeBeginPeriod(1)
except Exception:
    pass

cosyvoice_model = global_manager.cosyvoice_model


def add_log(message: str, level: str = "INFO"):
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    try:
        if level == "INFO":
            logger.info(message)
        elif level == "WARNING":
            logger.warning(message)
        elif level == "ERROR":
            logger.error(message)
        else:
            logger.info(message)
    except:
        pass
    print(f"[LOG][{level}] {message}")


