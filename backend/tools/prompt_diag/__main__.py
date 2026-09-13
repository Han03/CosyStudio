# -*- coding: utf-8 -*-
"""python -m tools.prompt_diag 入口。"""

import os
import sys

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from tools.prompt_diag.cli import main

if __name__ == "__main__":
    main()
