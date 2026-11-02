"""Immutable, verified stage results; incomplete work is never a cache hit."""
import hashlib
import json
import shutil
import time
import uuid
from pathlib import Path

from majimeeting.transcription import check_cancel


def file_digest(path, cancel=None):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        while block := source.read(1024 * 1024):
            check_cancel(cancel)
            digest.update(block)
    check_cancel(cancel)
    return digest.hexdigest()


def fingerprint(paths, root, cancel=None):
    return [(p.relative_to(root).as_posix(), file_digest(p, cancel)) for p in sorted(paths)]


def cached_stage(root, stage, inputs, build, cancel=None, progress=lambda _: None):
    key = hashlib.sha256(json.dumps(inputs, sort_keys=True, allow_nan=False).encode()).hexdigest()
    parent = Path(root) / stage
    destination = parent / key
    started = time.monotonic()
    check_cancel(cancel)
    if destination.is_dir():
        try:
            if file_digest(destination / 'stage.json', cancel) != (destination / 'ready.sha256').read_text():
                raise ValueError('Manifeste de cache modifié.')
            manifest = json.loads((destination / 'stage.json').read_text(encoding='utf-8'))
            if manifest['key'] != key or manifest['inputs'] != json.loads(json.dumps(inputs)):
                raise ValueError('Entrées de cache différentes.')
            for name, expected in manifest['files'].items():
                path = Path(name)
                if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:
                    raise ValueError('Chemin de cache invalide.')
                source = destination / path
                if source.is_symlink() or file_digest(source, cancel) != expected:
                    raise ValueError('Résultat de cache modifié.')
            progress(f'{stage} : résultat vérifié et réutilisé.')
            return dict(path=destination, key=key, result=manifest['result'], reused=True,
                        seconds=time.monotonic() - started)
        except (OSError, ValueError, KeyError, TypeError):
            # Preserve damaged evidence instead of treating it as a valid result.
            destination.rename(parent / (key + '.invalid-' + uuid.uuid4().hex))
    parent.mkdir(parents=True, exist_ok=True)
    staging = parent / ('.stage-' + uuid.uuid4().hex)
    staging.mkdir()
    try:
        result = build(staging)
        check_cancel(cancel)
        files = {p.relative_to(staging).as_posix(): file_digest(p, cancel)
                 for p in staging.rglob('*') if p.is_file()}
        manifest = dict(schema=1, key=key, inputs=inputs, result=result, files=files)
        with (staging / 'stage.json').open('w', encoding='utf-8') as target:
            json.dump(manifest, target, ensure_ascii=False, allow_nan=False)
            target.flush()
            import os
            os.fsync(target.fileno())
        (staging / 'ready.sha256').write_text(file_digest(staging / 'stage.json', cancel))
        check_cancel(cancel)
        staging.replace(destination)
        return dict(path=destination, key=key, result=result, reused=False,
                    seconds=time.monotonic() - started)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
