import os
import sys

_current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _current_dir)
sys.path.insert(0, os.path.join(_current_dir, 'third_party', 'Matcha-TTS'))
sys.path.insert(0, os.path.join(_current_dir, 'third_party', 'AcademiCodec'))

__all__ = ['CosyVoice', 'CosyVoice2', 'CosyVoice3', 'AutoModel', 'CosyVoiceFrontEnd']

def __getattr__(name):
    if name in __all__:
        if name == 'CosyVoiceFrontEnd':
            from cosyvoice.cli.frontend import CosyVoiceFrontEnd
            return CosyVoiceFrontEnd
        else:
            from cosyvoice.cli.cosyvoice import CosyVoice, CosyVoice2, CosyVoice3, AutoModel
            if name == 'CosyVoice':
                return CosyVoice
            elif name == 'CosyVoice2':
                return CosyVoice2
            elif name == 'CosyVoice3':
                return CosyVoice3
            elif name == 'AutoModel':
                return AutoModel
    raise AttributeError(f"module 'cosyvoice' has no attribute '{name}'")
