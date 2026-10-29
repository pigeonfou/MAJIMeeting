"""Separate the source DEV channel from ordinary recordings and preferences."""
import os
from pathlib import Path

from PySide6.QtCore import QSettings


def is_dev():
    return os.environ.get('MAJIMEETING_CHANNEL') == 'dev'


def data_root():
    root = Path(os.environ.get('LOCALAPPDATA', str(Path.home())))
    if is_dev():
        return Path(os.environ.get('MAJIMEETING_DATA_ROOT', str(root / 'MAJIMeeting-DEV/data')))
    return root / 'MAJIMeeting/data'


def shared_models():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'MAJIMeeting/models'


def application_settings():
    settings = QSettings('MAJIMeeting', 'MAJIMeeting DEV' if is_dev() else 'MAJIMeeting')
    if is_dev() and not settings.value('_initialized_from_standard', False, type=bool):
        ordinary = QSettings('MAJIMeeting', 'MAJIMeeting')
        allowed = ['model', 'cuda_path', 'device', 'compute_type', 'batched', 'batch_size',
                   'beam_size', 'flash_attention', 'gpu_workers', 'window_seconds', 'cpu_fallback',
                   'diarization_python', 'diarization_model', 'diarization_device',
                   'diarization_speakers', 'diarization_tuning']
        for key in allowed:
            if ordinary.contains(key):
                settings.setValue(key, ordinary.value(key))
        settings.setValue('_initialized_from_standard', True)
    return settings


def window_title():
    if is_dev():
        commit = os.environ.get('MAJIMEETING_SOURCE_COMMIT', 'source inconnue')[:12]
        return f'MAJIMeeting DEV — {commit} — Enregistrement et transcription'
    return 'MAJIMeeting — Enregistrement et transcription'
