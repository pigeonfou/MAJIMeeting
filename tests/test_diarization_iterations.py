import copy
import json
import sys

import pytest
from test_editor import prepared
from test_speakers import runtime, turn

from majimeeting.diarization import diarize, run_worker
from majimeeting.diarization_controls import DiarizationControls
from majimeeting.diarization_options import RUNTIME_CONFIGURATION, DiarizationOptions
from majimeeting.speakers import (
    complete_run,
    history,
    latest_run,
    list_runs,
    name_group,
    select_run,
    start_run,
)
from majimeeting.transcript_library import TranscriptLibrary, saved_transcripts


class FakePipeline:
    klustering = 'VBxClustering'
    segmentation_batch_size = 3
    embedding_batch_size = 4
    embedding_exclude_overlap = True

    def __init__(self):
        self.params = dict(clustering=dict(threshold=.63, Fa=.08, Fb=.9),
                           segmentation=dict(min_duration_off=.1))
        self.changes = 0

    def parameters(self, instantiated):
        assert instantiated
        return copy.deepcopy(self.params)

    def instantiate(self, params):
        self.params = params
        self.changes += 1


def configure():
    scope = {}
    exec(RUNTIME_CONFIGURATION, scope)
    return scope['configure_pipeline']


def test_model_defaults_are_preserved_and_partial_overrides_use_real_api():
    pipeline = FakePipeline()
    counts, actual = configure()(pipeline, DiarizationOptions().for_track('track-00', 0))
    assert counts == {} and actual['parameters'] == pipeline.params
    assert pipeline.changes == 0 and actual['segmentation_batch_size'] == 3
    options = DiarizationOptions(min_speakers=2, max_speakers=4, threshold=.7,
                                 exclude_overlap=False, embedding_batch_size=16)
    counts, actual = configure()(pipeline, options.for_track('track-00', 0))
    assert counts == dict(min_speakers=2, max_speakers=4)
    assert actual['parameters']['clustering'] == dict(threshold=.7, Fa=.08, Fb=.9)
    assert actual['exclude_overlap'] is False and actual['embedding_batch_size'] == 16


@pytest.mark.parametrize('values,speakers', [
    ({'min_speakers': 4, 'max_speakers': 2}, 0), ({'min_speakers': 2}, 3),
    ({'threshold': .9}, 0), ({'fa': float('nan')}, 0), ({'fb': 0}, 0),
    ({'min_duration_off': 2}, 0), ({'embedding_batch_size': 65}, 0),
    ({'track_speakers': {'../bad': dict(speakers=1, min_speakers=0, max_speakers=0)}}, 0),
])
def test_invalid_quality_controls_fail_before_inference(values, speakers):
    with pytest.raises(ValueError):
        DiarizationOptions(**values).validate(speakers)


def test_track_counts_do_not_force_remote_count_on_microphone():
    options = DiarizationOptions(min_speakers=2, max_speakers=5,
        track_speakers={'track-00': dict(speakers=1, min_speakers=0, max_speakers=0)})
    options.validate()
    assert configure()(FakePipeline(), options.for_track('track-00', 0))[0] == {'num_speakers': 1}
    assert configure()(FakePipeline(), options.for_track('track-01', 0))[0] == {
        'min_speakers': 2, 'max_speakers': 5}


def test_controls_restore_reset_and_exact_counts_disable_bounds():
    controls = DiarizationControls(0, {'threshold': .7, 'min_speakers': 2, 'max_speakers': 4},
                                   ['track-00', 'track-01'])
    assert controls.values()['threshold'] == .7
    controls.speakers.setValue(3)
    assert controls.values()['min_speakers'] == 0 and not controls.minimum.isEnabled()
    check, exact, minimum, maximum = controls.track_controls['track-00']
    check.setChecked(True)
    exact.setValue(1)
    assert controls.values()['track_speakers']['track-00']['speakers'] == 1
    controls.reset.click()
    assert controls.values()['threshold'] is None
    assert controls.values()['track_speakers'] == {} and controls.speakers.value() == 0


def test_reopen_old_transcript_and_previous_analysis_without_whisper(tmp_path):
    from majimeeting.__main__ import MainWindow
    from majimeeting.storage import MeetingStore
    from majimeeting.transcription import TranscriptionOptions
    store, meeting = prepared(tmp_path)
    store.start_transcription('newer', meeting, TranscriptionOptions('unused'))
    store.add_segment('newer', 'track-00', 1.75, 2.25, 'Other attempt')
    store.finish_transcription('newer', 'completed')
    first = start_run(store, 'job', {})
    complete_run(store, first, [turn(1.5, 3.5, 'A')])
    name_group(store, 'job', 'track-00:A', 'Alice')
    second = start_run(store, 'job', {})
    complete_run(store, second, [turn(1.5, 3.5, 'B')])
    select_run(store, 'job', first)
    with pytest.raises(ValueError):
        select_run(store, 'newer', first)
    assert list_runs(store, 'job')[0]['groups'] == 1
    # Both selection and human names survive restarting the application/catalogue.
    store = MeetingStore(store.root)
    window = MainWindow(store, scan=False)
    assert window.processing.activate_job('job')
    assert window.processing.jobs.currentData() == 'job'
    assert 'Alice' in window.processing.text.toPlainText()
    window.processing.reload()
    assert window.processing.jobs.currentData() == 'job'  # never silently switch to newest
    assert len(saved_transcripts(store)) == 2
    browser = TranscriptLibrary(store)
    browser.filter('no match')
    assert browser.job() is None
    browser.filter('Corrections')
    assert browser.job()
    browser.reject()
    window.close()
    restarted = MainWindow(store, scan=False)
    assert restarted.processing.jobs.currentData() == 'job'
    with store.connect() as db:
        assert latest_run(db, 'job') == first
    restarted.close()


def test_iteration_keeps_text_manual_names_and_tracks_effective_settings(tmp_path):
    store, _ = prepared(tmp_path)
    python, model = runtime(tmp_path)
    row = store.segments('job')[0]
    store.edit_segment(row['id'], 'Correction retained', 'Alice')
    calls = []
    def worker(*args):
        calls.append(args[-1])
        return dict(turns=[turn(.1, 1.9)], effective=dict(devices={'embedding': 'cuda:0'}))
    for threshold in (.6, .7):
        diarize(store, 'job', python, model, worker=worker,
                tuning=DiarizationOptions(threshold=threshold))
    assert [r['threshold'] for r in calls] == [.6, .7]
    assert store.segments('job')[0]['corrected_text'] == 'Correction retained'
    assert store.segments('job')[0]['speaker'] == 'Alice'
    runs = history(store, 'job')
    assert len(runs) == 2
    assert json.loads(runs[-1]['options'])['tracks'][0]['effective']['devices']['embedding'] == 'cuda:0'


def test_runtime_streams_phase_and_uses_isolated_request(tmp_path, monkeypatch):
    import majimeeting.diarization as module
    script = '''import json,sys,time
r=json.load(open(sys.argv[1]))
assert r['tuning']['threshold'] == .7
print('MAJI:Regroupement des voix (CPU)', flush=True)
time.sleep(.3)
json.dump({'turns': [], 'effective': {'device': r['device']}},open(r['result'],'w'))
'''
    monkeypatch.setattr(module, 'WORKER', script)
    messages = []
    result = run_worker(sys.executable, tmp_path, tmp_path / 'audio.wav', tmp_path / 'result.json',
                        'cuda', 0, None, messages.append, {'threshold': .7})
    assert result['effective']['device'] == 'cuda'
    assert 'Regroupement des voix (CPU)' in messages


@pytest.mark.parametrize('device,misplaced', [('cpu', False), ('cuda', False), ('cuda', True)])
def test_complete_worker_applies_controls_and_reports_devices(tmp_path, monkeypatch, capsys, device, misplaced):
    """Execute our worker against a model double, not a claim of real GPU inference."""
    import socket
    import types
    import wave

    from majimeeting.diarization import WORKER
    audio = tmp_path / 'audio.wav'
    with wave.open(str(audio), 'wb') as target:
        target.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        target.writeframes(b'\0\0' * 16000)
    class Pipeline(FakePipeline):
        @classmethod
        def from_pretrained(cls, _):
            return cls()

        def to(self, device):
            self.device = device
            self._segmentation = types.SimpleNamespace(model=types.SimpleNamespace(device=device))
            self._embedding = types.SimpleNamespace(device='cpu' if misplaced else device)

        def __call__(self, audio, hook, **kwargs):
            assert kwargs == {'num_speakers': 2}
            assert self.params['clustering']['threshold'] == .7
            assert self.embedding_batch_size == 16
            hook('segmentation', None, total=1, completed=1)
            hook('embeddings', None, total=1, completed=1)
            annotation = types.SimpleNamespace(itertracks=lambda **kw: [
                (types.SimpleNamespace(start=0., end=.5), None, 'SPEAKER_00')])
            return types.SimpleNamespace(speaker_diarization=annotation)
    torch = types.ModuleType('torch')
    torch.device = lambda v: v
    torch.from_numpy = lambda _: types.SimpleNamespace(unsqueeze=lambda _: 'waveform')
    torch.cuda = types.SimpleNamespace(is_available=lambda: True,
        get_device_name=lambda: 'Test double GPU', max_memory_allocated=lambda: 1024**2)
    pyannote = types.ModuleType('pyannote')
    pyannote_audio = types.ModuleType('pyannote.audio')
    pyannote_audio.Pipeline = Pipeline
    monkeypatch.setitem(sys.modules, 'torch', torch)
    monkeypatch.setitem(sys.modules, 'pyannote', pyannote)
    monkeypatch.setitem(sys.modules, 'pyannote.audio', pyannote_audio)
    # Record original socket methods before the offline worker replaces them.
    monkeypatch.setattr(socket.socket, 'connect', socket.socket.connect)
    monkeypatch.setattr(socket, 'create_connection', socket.create_connection)
    request = tmp_path / 'request.json'
    output = tmp_path / 'result.json'
    request.write_text(json.dumps(dict(model='test', audio=str(audio), result=str(output),
        device=device, tuning=DiarizationOptions(threshold=.7, embedding_batch_size=16).for_track('', 2))))
    monkeypatch.setattr(sys, 'argv', ['worker', str(request)])
    if misplaced:
        with pytest.raises(RuntimeError, match='resté sur CPU'):
            exec(WORKER, {})
        assert not output.exists()
        return
    exec(WORKER, {})
    result = json.loads(output.read_text())
    assert result['effective']['devices'] == {
        'pipeline': device, 'segmentation': device, 'embedding': device}
    assert result['effective']['counts'] == {'num_speakers': 2}
    assert 'regroupement' in capsys.readouterr().out


def test_dialog_launch_sends_quality_options_without_retranscribing(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QDialog

    import majimeeting.diarization as module
    from majimeeting.__main__ import MainWindow
    from majimeeting.diarization_ui import DiarizationDialog
    store, _ = prepared(tmp_path)
    window = MainWindow(store, scan=False)
    window.processing.activate_job('job')
    monkeypatch.setattr(DiarizationDialog, 'exec', lambda _: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(DiarizationDialog, 'values', lambda _: ('python', 'model', 'cuda', 0, {'threshold': .7}))
    observed = []
    monkeypatch.setattr(module, 'diarize', lambda *args, **kwargs: observed.append(kwargs['tuning'].threshold))
    window.processing.diarize()
    window.task[1].result(timeout=5)
    assert observed == [.7]
    assert len(store.transcription_jobs(window.processing.current_meeting)) == 1
    window.poll()
    window.close()
