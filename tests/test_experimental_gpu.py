import json
import threading
import wave
import weakref
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_transcription import local_options, recorded

from majimeeting.storage import FragmentWriter, MeetingStore
from majimeeting.transcription import audio_batches, transcribe_meeting


def test_flash_unsupported_retries_cuda_without_flash_not_cpu(tmp_path):
    store = MeetingStore(tmp_path / 'data')
    meeting = recorded(store)
    options = replace(local_options(tmp_path), device='cuda', compute_type='float16',
                      flash_attention=True, allow_cpu_fallback=False)
    calls = []

    class Model:
        def __init__(self, *args, **kwargs):
            calls.append(kwargs)
            if kwargs.get('flash_attention'):
                raise ValueError('FlashAttention is not supported by this build')

        def transcribe(self, *args, **kwargs):
            return iter([SimpleNamespace(start=0, end=1, text='Sans Flash')]), None

    job = transcribe_meeting(store, meeting, options, model_factory=Model,
                             cuda_prepare=lambda _: None)
    details = json.loads(store.transcription_jobs(meeting)[0]['options'])
    assert [c['device'] for c in calls] == ['cuda', 'cuda']
    assert details['flash_attention'] is True
    assert details['execution']['flash_attention'] is False
    assert len(details['metrics']['attempts']) == 2
    assert store.segments(job)[0]['text'] == 'Sans Flash'


def test_two_workers_overlap_keep_files_and_offsets_and_one_model(tmp_path, monkeypatch):
    import majimeeting.transcription as transcription
    store = MeetingStore(tmp_path / 'data')
    meeting = store.create('Concurrency')
    writer = FragmentWriter(store.root / meeting / 'track-00', 100, 1, {})
    for value in (100, 200, 300, 400):
        writer.write(value.to_bytes(2, 'little') * 100, .4)
    writer.close()
    store.finish(meeting, 'completed')
    monkeypatch.setattr(transcription, 'audio_batches', lambda track, dest, cancel, **kw:
                        audio_batches(track, dest, cancel, max_seconds=1))
    barrier = threading.Barrier(2)
    lock = threading.Lock()
    active, maximum, model_count = 0, 0, 0

    class Model:
        def __init__(self, *args, **kwargs):
            nonlocal model_count
            model_count += 1
            assert kwargs['num_workers'] == 2

    class Pipeline:
        def __init__(self, model):
            self.observed_batch_sizes = []

        def transcribe(self, path, **kwargs):
            nonlocal active, maximum
            with lock:
                active += 1
                maximum = max(maximum, active)
            try:
                barrier.wait(timeout=5)
                with wave.open(path, 'rb') as audio:
                    value = int.from_bytes(audio.readframes(1), 'little')
                self.observed_batch_sizes.append(1)
                return iter([SimpleNamespace(start=0, end=.8, text=str(value))]), None
            finally:
                with lock:
                    active -= 1

    options = replace(local_options(tmp_path), device='cuda', compute_type='float16',
                      batched=True, gpu_workers=2, batch_size=16, window_seconds=600)
    job = transcribe_meeting(store, meeting, options, model_factory=Model,
                             pipeline_factory=Pipeline, cuda_prepare=lambda _: None)
    assert maximum == 2 and model_count == 1
    assert [r['text'] for r in store.segments(job)] == ['100', '200', '300', '400']
    assert [r['start'] for r in store.segments(job)] == pytest.approx([.4, 1.4, 2.4, 3.4])
    metrics = json.loads(store.transcription_jobs(meeting)[0]['options'])['metrics']['attempts'][0]
    assert metrics['completed_audio_seconds'] == 4
    assert metrics['decoder_batches'] == 4
    assert metrics['decoder_requests'] == 4
    assert metrics['decoder_capacity'] == 64


def test_parallel_oom_releases_shared_model_and_retries_one_worker(tmp_path):
    store = MeetingStore(tmp_path / 'data')
    meeting = recorded(store)
    references, workers = [], []

    class Model:
        def __init__(self, *args, **kwargs):
            assert all(reference() is None for reference in references)
            references.append(weakref.ref(self))
            self.workers = kwargs.get('num_workers', 1)
            workers.append(self.workers)

    class Pipeline:
        def __init__(self, model):
            self.model = model

        def transcribe(self, *args, **kwargs):
            def generate():
                yield SimpleNamespace(start=0, end=1, text='Partiel' if self.model.workers == 2 else 'Final')
                if self.model.workers == 2:
                    raise RuntimeError('CUDA out of memory')
            return generate(), None

    options = replace(local_options(tmp_path), device='cuda', compute_type='float16',
                      batched=True, gpu_workers=2, allow_cpu_fallback=False)
    job = transcribe_meeting(store, meeting, options, model_factory=Model,
                             pipeline_factory=Pipeline, cuda_prepare=lambda _: None)
    assert workers == [2, 1]
    assert [r['text'] for r in store.segments(job)] == ['Final']
    assert json.loads(store.transcription_jobs(meeting)[0]['options'])['execution']['gpu_workers'] == 1


def test_parallel_user_cancel_never_restarts_gpu_or_cpu(tmp_path):
    from concurrent.futures import CancelledError
    store = MeetingStore(tmp_path / 'data')
    meeting = recorded(store)
    cancel = threading.Event()
    calls = []

    class Model:
        def __init__(self, *args, **kwargs):
            calls.append(kwargs['device'])

    class Pipeline:
        def __init__(self, model):
            pass

        def transcribe(self, *args, **kwargs):
            cancel.set()
            return iter([SimpleNamespace(start=0, end=1, text='À ignorer')]), None

    options = replace(local_options(tmp_path), device='cuda', compute_type='float16',
                      batched=True, gpu_workers=2)
    with pytest.raises(CancelledError):
        transcribe_meeting(store, meeting, options, cancel, model_factory=Model,
                           pipeline_factory=Pipeline, cuda_prepare=lambda _: None)
    assert calls == ['cuda']
    assert store.transcription_jobs(meeting)[0]['status'] == 'cancelled'


def test_experimental_controls_submit_and_report_actual_batch_sizes(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from majimeeting.__main__ import MainWindow
    app = QApplication.instance() or QApplication([])
    store = MeetingStore(tmp_path / 'data')
    meeting = recorded(store)
    window = MainWindow(store, scan=False)
    window.meetings.setCurrentRow(0)
    panel = window.processing
    panel.device.setCurrentText('cuda')
    panel.batched.setChecked(True)
    panel.flash.setChecked(True)
    panel.workers.setCurrentIndex(1)
    panel.audio_window.setCurrentIndex(1)
    panel.batch_size.setCurrentText('32')
    submitted = []
    monkeypatch.setattr(panel, 'submit', lambda *args, **kwargs: submitted.append(args))
    monkeypatch.setattr(panel, 'settings', SimpleNamespace(setValue=lambda *args: None))
    panel.transcribe()
    options = submitted[0][4]
    assert options.flash_attention and options.gpu_workers == 2
    assert options.window_seconds == 600 and options.batch_size == 32
    store.start_transcription('report', meeting, options)
    store.finish_transcription('report', 'completed')
    store.set_execution('report', 'cuda', 'float16', batched=True, batch_size=32,
                        flash_attention=True, gpu_workers=2, window_seconds=600)
    store.set_transcription_metrics('report', {'total_seconds': 1, 'attempts': [{
        'gpu_workers': 2, 'completed_audio_seconds': 3, 'decoder_batches': 2,
        'decoder_requests': 40, 'decoder_capacity': 64, 'decoder_batch_sizes': {'32': 1, '8': 1}}]})
    panel.reload()
    assert '62.5 %' in panel.performance.text()
    assert 'workers=2' in panel.execution.text()
    assert 'Flash Attention=oui' in panel.execution.text()
    panel.set_busy(True)
    assert not panel.flash.isEnabled() and not panel.workers.isEnabled()
    panel.set_busy(False)
    panel.device.setCurrentText('cpu')
    panel.transcribe()
    assert submitted[-1][4].gpu_workers == 1 and not submitted[-1][4].flash_attention
    window.close()
    app.processEvents()
