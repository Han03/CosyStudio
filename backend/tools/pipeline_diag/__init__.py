# -*- coding: utf-8 -*-
"""全流程诊断工具包。"""

from .recorder import PipelineDiagRecorder
from .instrument import install, uninstall

__all__ = ["PipelineDiagRecorder", "install", "uninstall"]
