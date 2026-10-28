"""Discover CUDA DLL directories without modifying the machine's environment."""
import ctypes
import os
import sys
from pathlib import Path

_DLL_DIRECTORIES = []  # Keep AddDllDirectory handles alive for the process lifetime.
_REGISTERED = set()


class CudaUnavailableError(RuntimeError):
    pass


def cuda_directories(extra=''):
    roots = [Path(extra)] if extra.strip() else []
    roots.extend(Path(value) for name, value in os.environ.items()
                 if value and (name.startswith('CUDA_PATH') or name == 'CUDNN_PATH'))
    program_files = Path(os.environ.get('ProgramFiles', 'C:/Program Files'))
    roots.extend((program_files / 'NVIDIA GPU Computing Toolkit' / 'CUDA').glob('v12.*'))
    roots.extend((program_files / 'NVIDIA' / 'CUDNN').glob('v9*'))
    result = []
    for root in roots:
        candidates = [root, root / 'bin', root / 'bin' / 'x64',
                      root / 'nvidia' / 'cublas' / 'bin', root / 'nvidia' / 'cudnn' / 'bin']
        if (root / 'bin').is_dir():
            candidates.extend(p for p in (root / 'bin').iterdir() if p.is_dir())
        for directory in candidates:
            if directory.is_dir() and directory not in result:
                result.append(directory.resolve())
    return result


def prepare_cuda(extra=''):
    """Fail before inference with actionable errors; later runtime errors remain handled too."""
    if sys.platform == 'win32':
        directories = cuda_directories(extra)
        for directory in directories:
            key = str(directory).lower()
            if key not in _REGISTERED:
                _DLL_DIRECTORIES.append(os.add_dll_directory(str(directory)))
                _REGISTERED.add(key)
                # CTranslate2 also uses native LoadLibrary; process PATH is needed by that loader.
                os.environ['PATH'] = str(directory) + os.pathsep + os.environ.get('PATH', '')
        for library in ('cublasLt64_12.dll', 'cublas64_12.dll', 'cudnn64_9.dll'):
            try:
                ctypes.WinDLL(library)
            except OSError as exc:
                raise CudaUnavailableError(
                    f'{library} absente ou impossible à charger. CUDA nécessite cuBLAS CUDA 12 '
                    'et cuDNN 9 pour CUDA 12. Choisissez CPU/int8 ou indiquez le dossier '
                    'des DLL NVIDIA installées.') from exc
    import ctranslate2
    try:
        count = ctranslate2.get_cuda_device_count()
    except (RuntimeError, OSError) as exc:
        raise CudaUnavailableError(f'Le pilote CUDA est indisponible : {exc}') from exc
    if not count:
        raise CudaUnavailableError('Aucun GPU CUDA utilisable détecté. Choisissez CPU/int8 '
                                   'ou vérifiez le pilote NVIDIA.')


def is_cuda_error(exc):
    if isinstance(exc, CudaUnavailableError):
        return True
    if not isinstance(exc, (RuntimeError, OSError)):
        return False
    message = str(exc).lower()
    return any(token in message for token in (
        'cublas', 'cudnn', 'cuda failed', 'cuda error', 'cuda driver', 'cuda runtime',
        'cuda unavailable', 'no cuda-capable device', 'not compiled with cuda',
        'insufficient driver',
    ))
