import json
import threading
import weakref
from concurrent.futures import CancelledError
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_transcription import local_options, recorded

from majimeeting.storage import MeetingStore
from majimeeting.transcription import transcribe_meeting


def test_batched_engine_receives_settings_and_keeps_absolute_times(tmp_path):
    store = MeetingStore(tmp_path / 'data')
    meeting = recorded(store, offset=13.5)
    options = replace(local_options(tmp_path), device='cuda', compute_type='float16',
                      batched=True, batch_size=8, beam_size=1)
    calls = []

    class Model:
        def __init__(self, *args, **kwargs):
            assert kwargs['device'] == 'cuda'

        def transcribe(self, *args, **kwargs):
            pytest.fail('The serial decoder must not be called')

    class Pipeline:
        def __init__(self, model):
            self.model = model

        def transcribe(self, path, **kwargs):
            calls.append(kwargs)
            return iter([SimpleNamespace(start=.5, end=1.5, text='Passage groupé')]), None

    job = transcribe_meeting(store, meeting, options, model_factory=Model,
                             pipeline_factory=Pipeline, cuda_prepare=lambda _: None)
    assert calls == [{'language': 'fr', 'beam_size': 1, 'vad_filter': True,
                      'without_timestamps': False, 'batch_size': 8}]
    segment = store.segments(job)[0]
    assert (segment['start'], segment['end']) == (14, 15)
    details = json.loads(store.transcription_jobs(meeting)[0]['options'])
    assert details['execution']['batched'] is True
    assert details['execution']['batch_size'] == 8
    assert details['execution']['beam_size'] == 1
    metrics = details['metrics']
    assert metrics['total_seconds'] > 0
    assert metrics['attempts'][0]['completed_audio_seconds'] == 3
    assert all(metrics['attempts'][0][name] >= 0 for name in (
        'model_load_seconds', 'prepare_seconds', 'inference_seconds', 'save_seconds'))


def test_gpu_memory_retry_reduces_batch_without_duplicates_or_model_overlap(tmp_path):
    store = MeetingStore(tmp_path / 'data')
    meeting = recorded(store)
    options = replace(local_options(tmp_path), device='cuda', compute_type='int8_float16',
                      batched=True, batch_size=8, allow_cpu_fallback=False)
    store.start_transcription('previous', meeting, options)
    store.add_segment('previous', 'track-00', 0, 1, 'Ancienne tentative')
    store.finish_transcription('previous', 'completed')
    references, sizes = [], []

    class Model:
        def __init__(self, *args, **kwargs):
            assert kwargs['device'] == 'cuda'
            assert all(reference() is None for reference in references)
            references.append(weakref.ref(self))

    class Pipeline:
        def __init__(self, model):
            self.model = model

        def transcribe(self, path, **kwargs):
            size = kwargs['batch_size']
            sizes.append(size)

            def generate():
                yield SimpleNamespace(start=0, end=1, text=f'Lot {size}')
                if size > 2:
                    raise RuntimeError('CUDA failed with error out of memory')
            return generate(), None

    job = transcribe_meeting(store, meeting, options, model_factory=Model,
                             pipeline_factory=Pipeline, cuda_prepare=lambda _: None)
    assert sizes == [8, 4, 2]
    assert [r['text'] for r in store.segments(job)] == ['Lot 2']
    assert store.segments('previous')[0]['text'] == 'Ancienne tentative'
    details = json.loads(store.transcription_jobs(meeting)[0]['options'])
    assert details['execution']['batch_size'] == 2
    assert details['execution']['device'] == 'cuda'
    assert len(details['metrics']['attempts']) == 3
    assert all(reference() is None for reference in references)


def test_oom_at_batch_one_tries_serial_cuda_before_cpu(tmp_path):
    store = MeetingStore(tmp_path / 'data')
    meeting = recorded(store)
    options = replace(local_options(tmp_path), device='cuda', compute_type='float16',
                      batched=True, batch_size=1)
    devices = []

    class Model:
        def __init__(self, *args, **kwargs):
            devices.append(kwargs['device'])

        def transcribe(self, *args, **kwargs):
            return iter([SimpleNamespace(start=0, end=1, text='Séquentiel GPU')]), None

    class Pipeline:
        def __init__(self, model):
            pass

        def transcribe(self, *args, **kwargs):
            raise RuntimeError('CUDA_ERROR_OUT_OF_MEMORY')

    job = transcribe_meeting(store, meeting, options, model_factory=Model,
                             pipeline_factory=Pipeline, cuda_prepare=lambda _: None)
    assert devices == ['cuda', 'cuda']
    assert store.segments(job)[0]['text'] == 'Séquentiel GPU'
    assert not json.loads(store.transcription_jobs(meeting)[0]['options'])['execution']['batched']


def test_batch_cancel_does_not_reduce_or_restart_on_cpu(tmp_path):
    store = MeetingStore(tmp_path / 'data')
    meeting = recorded(store)
    cancel = threading.Event()
    options = replace(local_options(tmp_path), device='cuda', compute_type='float16',
                      batched=True)
    calls = []

    class Model:
        def __init__(self, *args, **kwargs):
            calls.append(kwargs['device'])

    class Pipeline:
        def __init__(self, model):
            pass

        def transcribe(self, *args, **kwargs):
            cancel.set()
            raise RuntimeError('CUDA out of memory')

    with pytest.raises(CancelledError):
        transcribe_meeting(store, meeting, options, cancel=cancel, model_factory=Model,
                           pipeline_factory=Pipeline, cuda_prepare=lambda _: None)
    assert calls == ['cuda']
    assert store.transcription_jobs(meeting)[0]['status'] == 'cancelled'
    assert json.loads(store.transcription_jobs(meeting)[0]['options'])['metrics']['total_seconds'] > 0


def test_non_gpu_failure_does_not_retry_batched_decode(tmp_path):
    store = MeetingStore(tmp_path / 'data')
    meeting = recorded(store)
    options = replace(local_options(tmp_path), device='cuda', compute_type='float16', batched=True)
    calls = []

    class Pipeline:
        def __init__(self, model):
            pass

        def transcribe(self, *args, **kwargs):
            calls.append(1)
            raise RuntimeError('Invalid audio format')

    with pytest.raises(RuntimeError, match='Invalid audio'):
        transcribe_meeting(store, meeting, options, model_factory=lambda *a, **k: object(),
                           pipeline_factory=Pipeline, cuda_prepare=lambda _: None)
    assert calls == [1]


@pytest.mark.parametrize('changes', [{'batch_size': 0}, {'batch_size': 64}, {'beam_size': 2}])
def test_invalid_batch_settings_do_not_start_job(tmp_path, changes):
    store = MeetingStore(tmp_path / 'data')
    meeting = recorded(store)
    with pytest.raises(ValueError, match='profil'):
        transcribe_meeting(store, meeting, replace(local_options(tmp_path), **changes))
    assert not store.transcription_jobs(meeting)


def test_ui_selects_gpu_batch_and_speed_profile_and_displays_metrics(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from majimeeting.__main__ import MainWindow
    app = QApplication.instance() or QApplication([])
    store = MeetingStore(tmp_path / 'data')
    meeting = recorded(store)
    window = MainWindow(store, scan=False)
    window.meetings.setCurrentRow(0)
    panel = window.processing
    panel.device.setCurrentText('cuda')
    panel.compute.setCurrentText('float16')
    panel.batched.setChecked(True)
    panel.batch_size.setCurrentText('8')
    panel.quality.setCurrentIndex(1)
    submitted = []
    monkeypatch.setattr(panel, 'submit', lambda *args, **kwargs: submitted.append(args))
    monkeypatch.setattr(panel, 'settings', SimpleNamespace(setValue=lambda *args: None))
    panel.transcribe()
    options = submitted[0][4]
    assert options.device == 'cuda' and options.compute_type == 'float16'
    assert options.batched and options.batch_size == 8 and options.beam_size == 1
    panel.set_busy(True)
    assert not panel.batched.isEnabled() and not panel.quality.isEnabled()
    panel.set_busy(False)
    assert panel.batched.isEnabled() and panel.quality.isEnabled()
    panel.device.setCurrentText('cpu')
    assert not panel.batched.isEnabled()
    panel.transcribe()
    assert not submitted[-1][4].batched
    store.start_transcription('metrics', meeting, options)
    store.finish_transcription('metrics', 'completed')
    store.set_execution('metrics', 'cuda', 'float16', batched=True, batch_size=4, beam_size=1)
    store.set_transcription_metrics('metrics', {'total_seconds': 10, 'attempts': [
        {'completed_audio_seconds': 40, 'model_load_seconds': 1, 'prepare_seconds': 2,
         'inference_seconds': 6, 'save_seconds': 1}]})
    panel.reload()
    assert 'lots de 4' in panel.execution.text()
    assert '4.00×' in panel.performance.text()
    panel.write_export('metrics', tmp_path / 'metrics.json')
    exported = json.loads((tmp_path / 'metrics.json').read_text(encoding='utf-8'))
    assert exported['performance']['total_seconds'] == 10
    assert exported['execution']['batch_size'] == 4
    window.close()
    app.processEvents()
