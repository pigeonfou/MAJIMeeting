"""Persistent PCM and VAD on copies, preserving the original recording timeline."""
import math
import wave
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

from majimeeting.analysis_cache import cached_stage, file_digest, fingerprint
from majimeeting.transcription import check_cancel

RATE = 16000


@dataclass(frozen=True)
class PreparationOptions:
    normalize: bool = False
    vad_threshold: float = .5
    min_silence_ms: int = 500

    def validate(self):
        if not isinstance(self.normalize, bool) or not math.isfinite(self.vad_threshold):
            raise ValueError('Réglages audio invalides.')
        if not .1 <= self.vad_threshold <= .9 or not 100 <= self.min_silence_ms <= 2000:
            raise ValueError('Seuil VAD entre 0,1 et 0,9 ; silence entre 100 et 2000 ms.')
        return self


def level_audio(source, destination, normalize, cancel=None):
    """Peak target -3 dBFS, gain limited to +/-6 dB; never denoise the original."""
    import numpy as np
    peak, energy, count, clipped = 0., 0., 0, 0
    with wave.open(str(source), 'rb') as audio:
        while block := audio.readframes(65536):
            check_cancel(cancel)
            data = np.frombuffer(block, dtype='<i2').astype(np.float64)
            peak = max(peak, float(np.abs(data).max(initial=0)))
            energy += float(np.dot(data, data))
            clipped += int((np.abs(data) >= 32767).sum())
            count += len(data)
    gain = min(2., max(.5, 32768 * 10**(-3 / 20) / peak)) if normalize and peak else 1.
    with wave.open(str(source), 'rb') as audio, wave.open(str(destination), 'wb') as target:
        target.setparams(audio.getparams())
        while block := audio.readframes(65536):
            check_cancel(cancel)
            data = np.frombuffer(block, dtype='<i2').astype(np.float64)
            target.writeframesraw(np.rint(data * gain).clip(-32768, 32767).astype('<i2').tobytes())
    return dict(gain=gain, peak_before=peak / 32768,
                rms_before=math.sqrt(energy / count) / 32768 if count else 0.,
                clipped_samples_before=clipped)


def merge_intervals(intervals, gap=0.):
    merged = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if merged and start <= merged[-1][1] + gap:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def detect_speech(audio, options, cancel=None, detector=None):
    """Bound VAD RAM to ten minutes; overlap blocks without shifting timestamps."""
    import numpy as np
    if detector is None:
        from faster_whisper.vad import VadOptions, get_speech_timestamps
        vad = VadOptions(threshold=options.vad_threshold,
                         min_silence_duration_ms=options.min_silence_ms,
                         speech_pad_ms=200)
        def detector(samples):
            return get_speech_timestamps(samples, vad_options=vad)
    intervals = []
    with wave.open(str(audio), 'rb') as source:
        total = source.getnframes()
        if source.getframerate() != RATE or source.getnchannels() != 1:
            raise ValueError('Le VAD nécessite un PCM mono 16 kHz.')
        block_size = 600 * RATE
        for core in range(0, total, block_size):
            check_cancel(cancel)
            first, last = max(0, core - RATE), min(total, core + block_size + RATE)
            source.setpos(first)
            samples = np.frombuffer(source.readframes(last - first), dtype='<i2').astype(np.float32) / 32768
            for region in detector(samples):
                start, end = float(region['start']), float(region['end'])
                if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end <= len(samples)):
                    raise ValueError('Bornes VAD invalides.')
                a = max(core, first + start)
                b = min(core + block_size, total, first + end)
                if b > a:
                    intervals.append((a / RATE, b / RATE))
            check_cancel(cancel)
    return merge_intervals(intervals, gap=.03)


def prepare_meeting(store, meeting, options, cancel=None, progress=lambda _: None, detector=None):
    options.validate()
    folder = store.root / meeting
    tracks = sorted(p for p in folder.glob('track-*')
                    if (p / 'track.json').is_file() and any(p.glob('*.wav')))
    if not tracks:
        raise ValueError('Aucune piste finalisée à préparer.')
    from faster_whisper.utils import get_assets_path
    vad_model = Path(get_assets_path()) / 'silero_vad_v6.onnx'
    vad_engine = dict(whisper=version('faster-whisper'), onnxruntime=version('onnxruntime'),
                      model_sha256=file_digest(vad_model, cancel))
    root = folder / 'analysis-cache' / 'v1'
    results = []
    for track in tracks:
        check_cancel(cancel)
        progress(f'{track.name} : vérification des fragments audio…')
        sources = [track / 'track.json', *track.glob('*.wav'), *track.glob('*.json')]
        inputs = dict(schema=1, track=track.name, source=fingerprint(set(sources), track, cancel),
                      normalize=options.normalize, rate=RATE)
        def build_audio(stage, track=track):
            from majimeeting.diarization import prepare_track
            origin, duration = prepare_track(track, stage / 'raw.wav', cancel)
            levels = level_audio(stage / 'raw.wav', stage / 'audio.wav', options.normalize, cancel)
            (stage / 'raw.wav').unlink()
            return dict(track=track.name, origin=origin, duration=duration, levels=levels)
        prepared = cached_stage(root, 'audio', inputs, build_audio, cancel, progress)
        vad_inputs = dict(schema=1, audio=prepared['key'], threshold=options.vad_threshold,
                          min_silence_ms=options.min_silence_ms, speech_pad_ms=200,
                          engine=vad_engine)
        def build_vad(stage, prepared=prepared):
            regions = detect_speech(prepared['path'] / 'audio.wav', options, cancel, detector)
            return dict(regions=regions, speech_seconds=sum(b - a for a, b in regions))
        progress(f'{track.name} : détection de parole locale…')
        speech = cached_stage(root, 'vad', vad_inputs, build_vad, cancel, progress)
        results.append(dict(track=track.name, audio=prepared, speech=speech))
    return results


def transcription_windows(regions, duration, exclusive=(), max_seconds=600, join_gap=20.):
    """Keep continuous source windows, grouping short turns without duplicating context."""
    if max_seconds <= 2:
        raise ValueError('Fenêtre trop courte.')
    contexts = merge_intervals([(max(0., a - .75), min(duration, b + .75))
                               for a, b in regions], gap=join_gap)
    windows = []
    for first, last in contexts:
        while last - first > max_seconds:
            limit = first + max_seconds
            boundaries = [float(t['end']) for t in exclusive
                          if limit - 5 <= float(t['end']) <= limit]
            boundary = max(boundaries, default=limit)
            windows.append((first, boundary))
            first = boundary
        if last > first:
            windows.append((first, last))
    return windows


class PreparedBatches:
    """Adapter for the existing serial/two-worker Whisper paths; no concatenated time axis."""
    def __init__(self, prepared, voices):
        self.prepared = {p['track']: p for p in prepared}
        self.voices = {v['track']: v for v in voices}
        self.has_audio = any(p['speech']['result']['regions'] for p in prepared)
        self.clips = {p['track']: transcription_windows(
            p['speech']['result']['regions'], p['audio']['result']['duration'],
            self.voices[p['track']]['stage']['result'].get('exclusive_turns', []), 29.5, join_gap=2.)
            for p in prepared}

    def decode_options(self, track, offset, duration, batched):
        origin = self.prepared[track]['audio']['result']['origin']
        first = offset - origin
        clips = [dict(start=max(0., a - first), end=min(duration, b - first))
                 for a, b in self.clips[track] if a < first + duration and b > first]
        if not clips:
            raise ValueError('Fenêtre sans zone de parole à transcrire.')
        return dict(vad_filter=False, clip_timestamps=clips if batched else
                    [value for clip in clips for value in (clip['start'], clip['end'])])

    def __call__(self, track, destination, cancel=None, max_seconds=600):
        prepared = self.prepared[track.name]
        origin = prepared['audio']['result']['origin']
        duration = prepared['audio']['result']['duration']
        exclusive = self.voices[track.name]['stage']['result'].get('exclusive_turns', [])
        windows = transcription_windows(prepared['speech']['result']['regions'], duration,
                                        exclusive, max_seconds)
        with wave.open(str(prepared['audio']['path'] / 'audio.wav'), 'rb') as source:
            for first, last in windows:
                check_cancel(cancel)
                start, end = round(first * RATE), round(last * RATE)
                with wave.open(str(destination), 'wb') as output:
                    output.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
                    source.setpos(start)
                    remaining = end - start
                    while remaining:
                        check_cancel(cancel)
                        block = source.readframes(min(65536, remaining))
                        if not block:
                            raise ValueError('Copie de travail audio tronquée.')
                        output.writeframesraw(block)
                        remaining -= len(block) // 2
                yield origin + start / RATE, (end - start) / RATE


def stage_summary(prepared):
    return [dict(track=p['track'], audio_key=p['audio']['key'], vad_key=p['speech']['key'],
                 origin=p['audio']['result']['origin'], duration=p['audio']['result']['duration'],
                 levels=p['audio']['result']['levels'],
                 speech_seconds=p['speech']['result']['speech_seconds'],
                 regions=len(p['speech']['result']['regions']),
                 audio_reused=p['audio']['reused'], vad_reused=p['speech']['reused'],
                 audio_seconds=p['audio']['seconds'], vad_seconds=p['speech']['seconds'])
            for p in prepared]
