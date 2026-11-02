"""Reference propagation safety with simulated embeddings; not a speaker accuracy benchmark."""
import json
import threading
import wave
from concurrent.futures import CancelledError
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import majimeeting.guided_voice as guided
from majimeeting.guided_store import (
    add_reference,
    apply_proposals,
    decisions,
    guided_history,
    references,
    remove_reference,
)
from majimeeting.speakers import complete_run, history, select_run, start_run
from majimeeting.storage import FragmentWriter, MeetingStore
from majimeeting.transcription import TranscriptionOptions


@pytest.fixture
def scene(tmp_path, monkeypatch):
    store = MeetingStore(tmp_path/'data')
    meeting = store.create('Deux voix dans un seul groupe')
    track = store.root/meeting/'track-00'
    writer = FragmentWriter(track,16000,1,{})
    writer.write(np.r_[np.full(16*16000,1000),np.full(16*16000,-1000)].astype('<i2').tobytes(),0.)
    writer.close()
    store.finish(meeting,'completed')
    store.start_transcription('job',meeting,TranscriptionOptions('unused'))
    sids = []
    for i in range(8):
        words = [dict(start=4*i+k+.1,end=4*i+k+.9,word=(' ' if k else '')+f'mot{4*i+k}',probability=.95)
                 for k in range(4)]
        sids.append(store.add_segment('job','track-00',4*i,4*i+4,''.join(w['word'] for w in words),words))
    store.finish_transcription('job','completed')
    base = start_run(store,'job',{})
    complete_run(store,base,[dict(track='track-00',start=0.,end=32.,label='MIXED')])
    alice = add_reference(store,'job','track-00',2.,8.,'Alice')
    bob = add_reference(store,'job','track-00',20.,26.,'Bob')
    python = tmp_path/'python.exe'
    python.write_text('simulated runtime')
    model = tmp_path/'community'
    (model/'embedding').mkdir(parents=True)
    (model/'embedding/pytorch_model.bin').write_bytes(b'local embedding double')
    calls = []
    def extractor(python,model,audio,windows,stage,device,cancel,progress):
        calls.append(len(windows))
        result = []
        with wave.open(str(audio),'rb') as source:
            for first,last in windows:
                source.setpos(round(first*16000))
                values = np.frombuffer(source.readframes(round((last-first)*16000)),dtype='<i2')
                mean = float(values.mean())
                result.append([max(0,mean),max(0,-mean),1.])
        np.save(stage/'vectors.npy',np.asarray(result,dtype=np.float32).reshape(len(windows),3))
        return dict(device=device,dimension=3)
    original_prepare = guided.prepare_meeting
    monkeypatch.setattr(guided,'prepare_meeting',lambda store,meeting,options,cancel,progress:
        original_prepare(store,meeting,options,cancel,progress,detector=lambda _: []))
    def propose(options=None,scope='track-00:MIXED',**kw):
        return guided.propose_guided(store,'job','track-00',scope,python,model,'cpu',
            options or guided.GuidedOptions(),extractor=extractor,**kw)
    return SimpleNamespace(store=store,meeting=meeting,track=track,base=base,sids=sids,alice=alice,bob=bob,
                           python=python,model=model,calls=calls,extractor=extractor,propose=propose)


def accepted(store,run):
    return {r['id'] for r in decisions(store,run) if r['target'] and r['group_id'] and not r['reason']}


def test_reference_guidance_splits_merged_group_without_rewriting_text_and_can_restore(scene,monkeypatch):
    import majimeeting.transcription as transcription
    monkeypatch.setattr(transcription,'transcribe_meeting',lambda *a,**kw: pytest.fail('Whisper must not run'))
    before = scene.store.segments('job')
    run = scene.propose()
    assert scene.store.segments('job') == before  # preview has no side effects on displayed analysis
    assert accepted(scene.store,run)
    analysis = apply_proposals(scene.store,run,accepted(scene.store,run))
    after = scene.store.segments('job')
    assert {r['speaker'] for r in after if r['speaker']} == {'Alice','Bob'}
    assert ''.join(r['text'] for r in after) == ''.join(r['text'] for r in before)
    assert any(r['speaker_reason']=='guided_transition' for r in after)
    with scene.store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM transcription_jobs').fetchone()[0] == 1
    assert history(scene.store,'job')[-1]['id'] == analysis
    select_run(scene.store,'job',scene.base)
    assert scene.store.segments('job') == before
    assert guided_history(scene.store,'job')[0]['status']=='applied'


def test_threshold_change_reuses_both_embedding_stages(scene):
    first = scene.propose()
    second = scene.propose(replace(guided.GuidedOptions(),minimum_margin=.12))
    assert first != second and len(scene.calls)==2
    with scene.store.connect() as db:
        options = json.loads(db.execute('SELECT options FROM guided_runs WHERE id=?',(second,)).fetchone()[0])
    assert options['clips_reused'] and options['references_reused']


def test_added_reference_reuses_candidate_embeddings(scene):
    scene.propose()
    add_reference(scene.store,'job','track-00',9.,13.,'Alice')
    second = scene.propose()
    assert len(scene.calls)==3
    with scene.store.connect() as db:
        options = json.loads(db.execute('SELECT options FROM guided_runs WHERE id=?',(second,)).fetchone()[0])
    assert options['clips_reused'] and not options['references_reused']


def test_existing_piece_and_source_corrections_are_protected(scene):
    from majimeeting.speaker_pieces import edit_piece
    row = scene.store.segments('job')[0]
    edit_piece(scene.store,row['piece_id'],'Correction humaine','Nom confirmé')
    scene.store.edit_segment(scene.sids[1],'Autre correction','Autre nom')
    run = scene.propose()
    assert all(r['segment_id'] not in scene.sids[:2] for r in decisions(scene.store,run))
    apply_proposals(scene.store,run,accepted(scene.store,run))
    rows = scene.store.segments('job')
    assert rows[0]['corrected_text']=='Correction humaine' and rows[0]['speaker']=='Nom confirmé'
    assert rows[1]['corrected_text']=='Autre correction' and rows[1]['speaker']=='Autre nom'


def test_unknown_or_unchecked_proposals_never_force_a_name(scene):
    run = scene.propose()
    selection = accepted(scene.store,run)
    dropped = min(selection)
    decision = next(r for r in decisions(scene.store,run) if r['id']==dropped)
    selection.remove(dropped)
    apply_proposals(scene.store,run,selection)
    row = next(r for r in scene.store.segments('job') if r['start']==decision['start'])
    assert not row['speaker'] and row['speaker_reason']=='guided_unselected'


@pytest.mark.parametrize('change',['edit','reference','analysis','audio'])
def test_stale_preview_refuses_changes_atomically(scene,change):
    run = scene.propose()
    before_count = len(history(scene.store,'job'))
    if change=='edit':
        scene.store.edit_segment(scene.sids[0],'Nouvelle correction','Alice')
    elif change=='reference':
        remove_reference(scene.store,'job',scene.alice)
    elif change=='analysis':
        other = start_run(scene.store,'job',{})
        complete_run(scene.store,other,[dict(track='track-00',start=0,end=32,label='OTHER')])
        before_count += 1
    else:
        path = next(scene.track.glob('*.wav'))
        content = path.read_bytes()
        path.write_bytes(content[:-2]+b'\x12\x00')
    with pytest.raises(ValueError,match='chang'):
        apply_proposals(scene.store,run,accepted(scene.store,run))
    assert len(history(scene.store,'job'))==before_count


def test_known_overlap_is_never_used_as_clean_reference_or_named_by_propagation(scene):
    overlapping = start_run(scene.store,'job',{})
    complete_run(scene.store,overlapping,[dict(track='track-00',start=0,end=32,label='A'),
                                        dict(track='track-00',start=12,end=15,label='B')])
    run = scene.propose(scope='')
    overlap = [r for r in decisions(scene.store,run) if r['reason']=='overlap']
    assert overlap and not any(r['group_id'] for r in overlap)
    apply_proposals(scene.store,run,accepted(scene.store,run))
    assert any(r['speaker_reason']=='overlap' and not r['speaker'] for r in scene.store.segments('job'))
    add_reference(scene.store,'job','track-00',11.,16.,'Alice')
    with pytest.raises(ValueError,match='simultanées'):
        scene.propose(scope='')


def test_identical_references_block_propagation_outside_human_anchors():
    names={'a':'Alice','b':'Bob'}
    scores,warnings,close = guided.compare_vectors(np.array([[1.,0.]],dtype=np.float32),
        np.array([[1.,0.],[1.,0.]],dtype=np.float32),['a','b'],names)
    assert close=={'a','b'} and warnings
    result = guided.choose_word(dict(start=10,end=11),[],scores,{13:0,12:0,14:0},0,[],guided.GuidedOptions(),close)
    assert result['reason']=='guided_close_references' and not result['group_id']


def test_zero_or_nonfinite_embeddings_never_create_identity():
    with pytest.raises(ValueError,match='exploitable'):
        guided.compare_vectors(np.zeros((1,3),np.float32),np.zeros((2,3),np.float32),['a','b'],{'a':'A','b':'B'})
    scores,_,_ = guided.compare_vectors(np.array([[np.nan,0],[0,0]],np.float32),np.eye(2,dtype=np.float32),['a','b'],{'a':'A','b':'B'})
    assert scores==[None,None]


def test_references_validate_names_bounds_and_conflicting_labels(scene):
    with pytest.raises(ValueError,match='chevauchent'):
        add_reference(scene.store,'job','track-00',3.,7.,'Bob')
    with pytest.raises(ValueError,match='3 à 20'):
        add_reference(scene.store,'job','track-00',9.,10.,'Alice')
    with pytest.raises(ValueError,match='nom'):
        add_reference(scene.store,'job','track-00',9.,13.,' ')
    remove_reference(scene.store,'job',scene.bob)
    assert len(references(scene.store,'job'))==1
    with pytest.raises(ValueError,match='deux personnes'):
        scene.propose()


def test_cancellation_preserves_previous_analysis_and_ready_cache(scene):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(CancelledError):
        scene.propose(cancel=cancel)
    assert len(history(scene.store,'job'))==1
    run = scene.propose()
    with pytest.raises(CancelledError):
        apply_proposals(scene.store,run,accepted(scene.store,run),cancel)
    assert len(history(scene.store,'job'))==1
    with scene.store.connect() as db:
        assert db.execute('SELECT status FROM guided_runs WHERE id=?',(run,)).fetchone()[0]=='ready'


def test_wrong_decision_ids_cannot_be_applied_and_applied_preview_is_not_repeatable(scene):
    run = scene.propose()
    with pytest.raises(ValueError):
        apply_proposals(scene.store,run,{999999})
    apply_proposals(scene.store,run,accepted(scene.store,run))
    with pytest.raises(ValueError,match='déjà appliqué'):
        apply_proposals(scene.store,run,accepted(scene.store,run))


def test_reference_outside_audio_and_missing_word_timing_are_explicit(scene):
    add_reference(scene.store,'job','track-00',33.,38.,'Alice')
    with pytest.raises(ValueError,match='limites'):
        scene.propose()
    with scene.store.connect() as db:
        db.execute('DELETE FROM transcript_words')
    with pytest.raises(ValueError,match='horodatages'):
        scene.propose()


def test_export_has_reference_history_without_vector_data(scene,tmp_path):
    from majimeeting.__main__ import MainWindow
    run = scene.propose()
    apply_proposals(scene.store,run,accepted(scene.store,run))
    window = MainWindow(scene.store,scan=False)
    path = tmp_path/'guided.json'
    window.processing.write_export('job',path)
    result = json.loads(path.read_text())
    assert len(result['voice_references'])==2
    assert result['guided_history'][0]['status']=='applied'
    assert 'vectors.npy' not in path.read_text()
    window.close()


def test_worker_protocol_preserves_window_order_and_uses_local_embedding_only(tmp_path,monkeypatch):
    import sys
    import types

    audio = tmp_path/'audio échantillon.wav'
    with wave.open(str(audio),'wb') as output:
        output.setparams((1,2,16000,0,'NONE','not compressed'))
        output.writeframes(np.arange(6*16000,dtype=np.int32).clip(1,16000).astype('<i2').tobytes())
    calls = []
    class Device:
        def __init__(self,name): self.name=name
        def __str__(self): return self.name
    class Embedding:
        sample_rate=16000
        dimension=3
        def __init__(self,path,device):
            assert Path(path).parts[-2:] == ('embedding','pytorch_model.bin')
            self.device=device
        def __call__(self,batch):
            calls.append(batch.shape)
            assert batch.shape[1]==1 and batch.dtype==np.float32
            return np.column_stack([np.full(len(batch),batch.shape[-1]),batch[:,0,:].mean(axis=1),np.ones(len(batch))]).astype(np.float32)
    verification = types.ModuleType('pyannote.audio.pipelines.speaker_verification')
    verification.PyannoteAudioPretrainedSpeakerEmbedding=Embedding
    fake_torch=types.ModuleType('torch')
    fake_torch.device=Device
    fake_torch.from_numpy=lambda array: array
    fake_torch.cuda=SimpleNamespace(is_available=lambda: False)
    for name,module in [('torch',fake_torch),('pyannote.audio.pipelines.speaker_verification',verification)]:
        monkeypatch.setitem(sys.modules,name,module)
    # The isolated worker deliberately blocks sockets; use a fake module in this in-process test.
    monkeypatch.setitem(sys.modules,'socket',SimpleNamespace(socket=type('Socket',(),{}),create_connection=None))
    for key in ('HF_HUB_OFFLINE','HF_HUB_DISABLE_TELEMETRY','PYANNOTE_METRICS_ENABLED','OTEL_SDK_DISABLED'):
        monkeypatch.setenv(key,'1')
    request=tmp_path/'request.json'
    result=tmp_path/'result.json'
    request.write_text(json.dumps(dict(model=str(tmp_path/'local model'),audio=str(audio),result=str(result),
        device='cpu',windows=[[0,3],[3,5],[1,4]])),encoding='utf-8')
    monkeypatch.setattr(sys,'argv',['worker',str(request)])
    exec(compile(guided.EMBEDDING_WORKER,'guided-worker','exec'),{})
    vectors=np.load(tmp_path/'vectors.npy',allow_pickle=False)
    assert vectors[:,0].tolist()==[48000,32000,48000]
    assert sorted(calls)==[(1,1,32000),(2,1,48000)]
    assert json.loads(result.read_text())['device']=='cpu'
    request.write_text(json.dumps(dict(model='local',audio=str(audio),result=str(result),device='cuda',windows=[])))
    with pytest.raises(RuntimeError,match='CUDA PyTorch'):
        exec(compile(guided.EMBEDDING_WORKER,'guided-worker','exec'),{})


def test_telemetry_is_disabled_through_native_runtime_api(monkeypatch):
    import sys

    from majimeeting.offline_runtime import disable_onnx_telemetry
    calls=[]
    monkeypatch.setitem(sys.modules,'onnxruntime',SimpleNamespace(disable_telemetry_events=lambda: calls.append('off')))
    disable_onnx_telemetry()
    assert calls==['off']


def test_guided_dialog_requires_clean_reference_and_explicit_scope(scene,monkeypatch,tmp_path):
    from PySide6.QtCore import QSettings

    import majimeeting.guided_ui as ui
    settings=QSettings(str(tmp_path/'guided.ini'),QSettings.Format.IniFormat)
    monkeypatch.setattr(ui,'application_settings',lambda: settings)
    dialog=ui.GuidedVoiceDialog(scene.store,'job')
    dialog.first.setValue(9.)
    dialog.last.setValue(13.)
    dialog.name.setText('Alice')
    dialog.add_sample()
    assert len(references(scene.store,'job'))==2
    assert 'confirmez' in dialog.status.text()
    dialog.clean.setChecked(True)
    dialog.add_sample()
    assert len(references(scene.store,'job'))==3
    assert dialog.scope.currentData() is None
    dialog.calculate()
    assert dialog.future is None and 'Choisissez' in dialog.status.text()
    dialog.close()


def test_gui_preview_apply_and_global_busy_lock(scene,monkeypatch,tmp_path,qt_application):
    from PySide6.QtCore import QSettings

    import majimeeting.guided_ui as ui
    from majimeeting.__main__ import MainWindow
    run=scene.propose()
    settings=QSettings(str(tmp_path/'guided.ini'),QSettings.Format.IniFormat)
    monkeypatch.setattr(ui,'application_settings',lambda: settings)
    monkeypatch.setattr(ui,'propose_guided',lambda *args: run)
    owner=MainWindow(scene.store,scan=False)
    owner.processing.activate_job('job')
    seed=scene.store.segments('job')[0]
    dialog=ui.GuidedVoiceDialog(scene.store,'job',owner.processing,seed=seed)
    assert dialog.scope.currentData()=='track-00:MIXED'
    dialog.calculate()
    assert owner.guided_busy and not owner.start_button.isEnabled()
    dialog.future.result(timeout=5)
    dialog.poll()
    assert not owner.guided_busy and owner.start_button.isEnabled()
    assert dialog.apply.isEnabled() and dialog.accepted
    dialog.select_all(False)
    assert not dialog.apply.isEnabled()
    dialog.select_all(True)
    dialog.apply_selected()
    dialog.future.result(timeout=5)
    dialog.poll()
    assert 'appliquée' in dialog.status.text()
    assert {'Alice','Bob'} <= {r['speaker'] for r in scene.store.segments('job')}
    assert len(history(scene.store,'job'))==2
    dialog.close()
    owner.close()
    qt_application.processEvents()


def test_closing_during_guided_work_cancels_and_waits(scene,monkeypatch,qt_application):
    import majimeeting.guided_ui as ui
    started=threading.Event()
    def task(*args):
        cancel=args[-2]
        started.set()
        assert cancel.wait(3)
        raise CancelledError('cancelled test')
    monkeypatch.setattr(ui,'propose_guided',task)
    dialog=ui.GuidedVoiceDialog(scene.store,'job',seed=scene.store.segments('job')[0])
    dialog.calculate()
    assert started.wait(3)
    dialog.reject()
    assert dialog.close_pending and dialog.cancel.is_set()
    with pytest.raises(CancelledError):
        dialog.future.result(timeout=3)
    dialog.poll()
    assert dialog.future is None
    assert len(history(scene.store,'job'))==1
    qt_application.processEvents()



def test_repeated_guidance_does_not_rename_an_untargeted_group(scene):
    from majimeeting.speakers import name_group
    first=scene.propose()
    apply_proposals(scene.store,first,accepted(scene.store,first))
    rows=scene.store.segments('job')
    alice=next(r['speaker_group'] for r in rows if r['speaker']=='Alice')
    bob=next(r['speaker_group'] for r in rows if r['speaker']=='Bob')
    name_group(scene.store,'job',alice,'Ally confirmé')
    second=scene.propose(scope=bob)
    apply_proposals(scene.store,second,accepted(scene.store,second))
    assert scene.store.segments('job')[0]['speaker']=='Ally confirmé'


def test_model_configuration_preserves_existing_clustering_controls(monkeypatch):
    from PySide6.QtWidgets import QDialog

    import majimeeting.diarization_ui as configuration
    from majimeeting.guided_ui import GuidedVoiceDialog
    data={'diarization_tuning':'per-track settings kept','diarization_speakers':3}
    class Dialog:
        def __init__(self,*args,**kwargs):
            self.controls=SimpleNamespace(hide=lambda: None)
            self.buttons=SimpleNamespace(button=lambda _: SimpleNamespace(setText=lambda _: None))
            self.python=SimpleNamespace(text=lambda: 'new-python.exe')
            self.model=SimpleNamespace(text=lambda: 'community-local')
            self.device=SimpleNamespace(currentText=lambda: 'cuda')
        def setWindowTitle(self,*args): pass
        def findChild(self,*args): return SimpleNamespace(setCurrentIndex=lambda _: None)
        def exec(self): return QDialog.DialogCode.Accepted
        def values(self): pytest.fail('must not overwrite unrelated tuning/counts')
    monkeypatch.setattr(configuration,'DiarizationDialog',Dialog)
    current=[]
    owner=SimpleNamespace(python='old',model='old',device=SimpleNamespace(currentText=lambda:'cpu',
        setCurrentText=lambda value: current.append(value)),settings=SimpleNamespace(setValue=lambda k,v:data.__setitem__(k,v)),
        invalidate=lambda: None)
    GuidedVoiceDialog.configure_runtime(owner)
    assert owner.python=='new-python.exe' and owner.model=='community-local'
    assert current==['cuda']
    assert data['diarization_tuning']=='per-track settings kept' and data['diarization_speakers']==3
