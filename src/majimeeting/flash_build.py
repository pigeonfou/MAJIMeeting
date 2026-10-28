"""Capability check for the separately compiled experimental native engine."""
import ctypes
import json
from pathlib import Path


def verify_native_flash():
    import ctranslate2
    folder = Path(ctranslate2.__file__).parent
    metadata = json.loads((folder / 'majimeeting_flash_build.json').read_text(encoding='utf-8'))
    library = ctypes.CDLL(str(folder / 'ctranslate2.dll'))
    library.majimeeting_flash_compiled.restype = ctypes.c_int
    if library.majimeeting_flash_compiled() != 1:
        raise RuntimeError('The native DLL does not report Flash Attention compiled')
    if metadata['source_commit'] != '5de572ef60b67a0276c5989ee73d0072808ff4c3':
        raise RuntimeError('Unexpected CTranslate2 source revision')
    return {'native_flash_compiled': True, 'build': metadata,
            'gpu_inference_verified': False}
