import json
import threading
import weakref
from concurrent.futures import CancelledError
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_transcription import local_options, recorded

from majimeeting.cuda_runtime import CudaUnavailableError, cuda_directories
from majimeeting.storage import MeetingStore
from majimeeting.transcription import transcribe_meeting


def missing_cuda(path):
    raise CudaUnavailableError('cublas64_12.dll absente ou impossible à charger')


class CpuModel:
    def __init__(self, path, device, compute_type, **kwargs):
        assert device == 'cpu'
        assert compute_type == 'int8'

    def transcribe(self, *args, **kwargs):
        return iter([SimpleNamespace(start=0, end=1, text='Texte CPU')]), None


def test_missing_cuda_falls_back_and_records_actual_execution(tmp_path):
    store = MeetingStore(tmp_path / 'data')
    meeting = recorded(store)
    options = replace(local_options(tmp_path), device='cuda', compute_type='float16')
    messages = []
    job = transcribe_meeting(store, meeting, options, progress=messages.append,
                             model_factory=CpuModel, cuda_prepare=missing_cuda)
    row = store.transcription_jobs(meeting)[0]
    execution = json.loads(row['options'])['execution']
    assert row['status'] == 'completed'
    assert execution['device'] == 'cpu'
    assert execution['compute_type'] == 'int8'
    assert 'cublas64_12.dll' in execution['fallback_reason']
    assert store.segments(job)[0]['text'] == 'Texte CPU'
    assert any('Reprise complète sur CPU' in message for message in messages)


def test_cpu_fallback_can_be_disabled(tmp_path):
    store = MeetingStore(tmp_path / 'data')
    meeting = recorded(store)
    options = replace(local_options(tmp_path), device='cuda', compute_type='float16',
                      allow_cpu_fallback=False)
    with pytest.raises(RuntimeError, match='Choisissez CPU/int8'):
        transcribe_meeting(store, meeting, options, model_factory=lambda *a, **k: pytest.fail(),
                           cuda_prepare=missing_cuda)
    assert store.transcription_jobs(meeting)[0]['status'] == 'failed'


def test_lazy_cuda_failure_restarts_without_duplicate_segments_and_unloads_model(tmp_path):
    store = MeetingStore(tmp_path / 'data')
    meeting = recorded(store)
    options = replace(local_options(tmp_path), device='cuda', compute_type='int8_float16')
    store.start_transcription('previous', meeting, options)
    store.add_segment('previous', 'track-00', 0, 1, 'Ancienne transcription')
    store.finish_transcription('previous', 'completed')
    gpu_models = []

    class Model:
        def __init__(self, path, device, **kwargs):
            self.device = device
            if device == 'cuda':
                gpu_models.append(weakref.ref(self))
            else:
                assert all(reference() is None for reference in gpu_models)

        def transcribe(self, *args, **kwargs):
            def segments():
                yield SimpleNamespace(start=0, end=1, text='Partiel GPU' if self.device == 'cuda'
                                      else 'Résultat CPU')
                if self.device == 'cuda':
                    raise RuntimeError('Library cublas64_12.dll is not found or cannot be loaded')
            return segments(), None

    job = transcribe_meeting(store, meeting, options, model_factory=Model,
                             cuda_prepare=lambda path: None)
    assert [row['text'] for row in store.segments(job)] == ['Résultat CPU']
    assert store.segments('previous')[0]['text'] == 'Ancienne transcription'


def test_cancel_during_cuda_failure_does_not_start_cpu(tmp_path):
    store = MeetingStore(tmp_path / 'data')
    meeting = recorded(store)
    options = replace(local_options(tmp_path), device='cuda', compute_type='float16')
    cancel = threading.Event()

    def cancelled_preflight(path):
        cancel.set()
        missing_cuda(path)

    with pytest.raises(CancelledError):
        transcribe_meeting(store, meeting, options, cancel,
                           model_factory=lambda *a, **k: pytest.fail('CPU must not start'),
                           cuda_prepare=cancelled_preflight)
    assert store.transcription_jobs(meeting)[0]['status'] == 'cancelled'


def test_non_cuda_errors_do_not_trigger_cpu_retry(tmp_path):
    store = MeetingStore(tmp_path / 'data')
    meeting = recorded(store)
    options = replace(local_options(tmp_path), device='cuda', compute_type='float16')
    calls = []

    def failure(*args, **kwargs):
        calls.append(kwargs['device'])
        raise RuntimeError('Invalid audio format')

    with pytest.raises(RuntimeError, match='Invalid audio'):
        transcribe_meeting(store, meeting, options, model_factory=failure,
                           cuda_prepare=lambda path: None)
    assert calls == ['cuda']


def test_custom_and_environment_cuda_directories(tmp_path, monkeypatch):
    custom = tmp_path / 'custom'
    cuda = tmp_path / 'cuda' / 'bin'
    cudnn = tmp_path / 'cudnn' / 'bin' / '12.9'
    for folder in (custom, cuda, cudnn):
        folder.mkdir(parents=True)
    monkeypatch.setenv('CUDA_PATH', str(cuda.parent))
    monkeypatch.setenv('CUDNN_PATH', str(cudnn.parent.parent))
    directories = cuda_directories(str(custom))
    assert custom.resolve() in directories
    assert cuda.resolve() in directories
    assert cudnn.resolve() in directories


def test_missing_windows_dll_is_reported_before_cuda_engine_load(monkeypatch):
    import majimeeting.cuda_runtime as runtime
    monkeypatch.setattr(runtime.sys, 'platform', 'win32')
    monkeypatch.setattr(runtime, 'cuda_directories', lambda extra: [])
    loaded = []

    def missing(name):
        loaded.append(name)
        raise OSError('DLL not found')

    monkeypatch.setattr(runtime.ctypes, 'WinDLL', missing, raising=False)
    with pytest.raises(CudaUnavailableError, match='cublasLt64_12.dll'):
        runtime.prepare_cuda()
    assert loaded == ['cublasLt64_12.dll']
