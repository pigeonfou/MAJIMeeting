"""Bounded excerpts on the meeting clock, without reconstructing a whole track."""
import json
import math
import wave
from pathlib import Path


def make_excerpt(track, start, end, destination):
    """Write at most 60 seconds of PCM; retain gaps as silence and source offsets."""
    if not all(math.isfinite(t) for t in (start, end)) or start < 0 or end <= start:
        raise ValueError('Intervalle de lecture invalide.')
    end = min(end, start + 60)
    track, destination = Path(track), Path(destination)
    info = json.loads((track / 'track.json').read_text(encoding='utf-8'))
    rate, channels, width = info['rate'], info['channels'], info['sample_width']
    first, last = round(start * rate), round(end * rate)
    if last <= first:
        raise ValueError('Intervalle de lecture trop court.')
    # Allocate only the bounded excerpt, never meeting-length PCM.
    pcm = bytearray((last - first) * channels * width)
    found = False
    previous_end = None
    for fragment in sorted(track.glob('*.wav')):
        timing = json.loads(fragment.with_suffix('.json').read_text(encoding='utf-8'))
        offset = round(timing['start_seconds'] * rate)
        count = timing['frames']
        if previous_end is not None and offset < previous_end:
            raise ValueError('Fragments audio en chevauchement : lecture interrompue.')
        previous_end = offset + count
        left, right = max(first, offset), min(last, offset + count)
        if right <= left:
            continue
        with wave.open(str(fragment), 'rb') as audio:
            if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth(),
                    audio.getnframes()) != (rate, channels, width, count):
                raise ValueError('Fragment audio incomplet ou format incohérent.')
            audio.setpos(left - offset)
            data = audio.readframes(right - left)
            expected = (right - left) * channels * width
            if len(data) != expected:
                raise ValueError('Fragment audio tronqué.')
            position = (left - first) * channels * width
            pcm[position:position + expected] = data
            found = True
    if not found:
        raise ValueError('Aucun fragment disponible pour ce passage.')
    with wave.open(str(destination), 'wb') as output:
        output.setnchannels(channels)
        output.setsampwidth(width)
        output.setframerate(rate)
        output.writeframes(pcm)
    return (last - first) / rate
