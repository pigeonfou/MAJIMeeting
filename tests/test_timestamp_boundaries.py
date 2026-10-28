import math

import pytest
from test_transcription import local_options

from majimeeting.selftest import timestamp_boundary_smoke
from majimeeting.storage import MeetingStore
from majimeeting.transcription import normalize_timestamps


@pytest.mark.parametrize(('start', 'end', 'duration', 'expected', 'warning'), [
    (0, 10, 10, (0, 10), None),
    (9.5, 30, 10, (9.5, 10), 'clipped'),
    (-.02, 2, 10, (0, 2), 'clipped'),
    (10, 30, 10, None, 'outside_audio'),
    (10.000000001, 30, 10, None, 'outside_audio'),
    (-2, -.01, 10, None, 'outside_audio'),
    (5, 5, 10, None, 'outside_audio'),
    (9, 2, 10, None, 'invalid_timestamp'),
    (float('nan'), 2, 10, None, 'invalid_timestamp'),
    (0, float('inf'), 10, None, 'invalid_timestamp'),
    (None, 2, 10, None, 'invalid_timestamp'),
])
def test_timestamps_stay_within_source(start, end, duration, expected, warning):
    result, actual_warning = normalize_timestamps(start, end, duration)
    assert result == expected
    assert actual_warning == warning
    if result:
        assert 0 <= result[0] < result[1] <= duration
        assert all(math.isfinite(value) for value in result)



def test_complete_meeting_survives_short_last_batch_after_1200_seconds(tmp_path):
    store = MeetingStore(tmp_path / 'data')
    timestamp_boundary_smoke(store, local_options(tmp_path))


def test_restart_clears_only_current_attempt_warnings(tmp_path):
    store = MeetingStore(tmp_path / 'data')
    meeting = store.create('Test')
    options = local_options(tmp_path)
    for job in ('previous', 'retry'):
        store.start_transcription(job, meeting, options)
        store.add_segment(job, 'track-00', 0, 1, 'Texte')
        store.add_transcription_warning(job, 'track-00', 0, 0, 30, 'clipped', 'Texte')
    store.set_execution('retry', 'cpu', 'int8', 'CUDA unavailable', reset_segments=True)
    assert store.segments('retry') == []
    assert store.transcription_warnings('retry') == []
    assert len(store.segments('previous')) == 1
    assert len(store.transcription_warnings('previous')) == 1


def test_adding_warning_storage_preserves_existing_data(tmp_path):
    store = MeetingStore(tmp_path / 'data')
    meeting = store.create('Ancienne base')
    store.start_transcription('old', meeting, local_options(tmp_path))
    store.add_segment('old', 'track-00', 0, 1, 'Conservé')
    with store.connect() as db:
        db.execute('DROP TABLE transcription_warnings')
    migrated = MeetingStore(store.root)
    assert migrated.segments('old')[0]['text'] == 'Conservé'
    assert migrated.warning_counts('old') == {}
