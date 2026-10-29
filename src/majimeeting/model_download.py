"""Bounded, cancellable HTTPS downloads without loading the inference runtime."""
import hashlib
import json
import os
import re
import shutil
from concurrent.futures import CancelledError
from datetime import UTC, datetime
from pathlib import Path

import requests

TIMEOUT = (10, 15)  # connect / idle read, seconds; no unbounded retry loop
FILES = {'model.bin', 'config.json', 'tokenizer.json', 'preprocessor_config.json',
         'vocabulary.json', 'vocabulary.txt'}
REQUIRED = {'model.bin', 'config.json', 'tokenizer.json'}


def _cancel(event):
    if event is not None and event.is_set():
        raise CancelledError('Téléchargement annulé ; les fichiers partiels sont conservés.')


def _digest(path, algorithm, cancel, progress):
    size = path.stat().st_size
    result = hashlib.new(algorithm)
    if algorithm == 'sha1':
        result.update(f'blob {size}\0'.encode())  # Git blob id for non-LFS files
    with path.open('rb') as handle:
        while block := handle.read(4 * 1024 * 1024):
            _cancel(cancel)
            result.update(block)
    return result.hexdigest()


def download_model(destination, cancel=None, progress=lambda message, percent=None: None,
                   model_name='large-v3', session_factory=requests.Session, token=''):
    """Download an allowed model at a fixed revision; verify every promoted file."""
    if model_name not in {'large-v3', 'tiny', 'community-1'}:
        raise ValueError('Modèle de téléchargement non pris en charge.')
    _cancel(cancel)
    destination = Path(destination).expanduser()
    destination.mkdir(parents=True, exist_ok=True)
    log_path = destination / 'download.log'

    def log(message):
        with log_path.open('a', encoding='utf-8') as handle:
            handle.write(f'{datetime.now(UTC).isoformat()} {message}\n')

    def report(message, percent=None):
        progress(message, percent)

    community = model_name == 'community-1'
    repo = ('pyannote/speaker-diarization-community-1' if community else
            f'Systran/faster-whisper-{model_name}')
    required = ({'config.yaml', 'embedding/pytorch_model.bin',
                 'segmentation/pytorch_model.bin', 'plda/plda.npz',
                 'plda/xvec_transform.npz'} if community else REQUIRED)
    allowed_files = required if community else FILES
    try:
        log(f'Start {repo}')
        report('Connexion au serveur de modèles… (connexion 10 s, lecture 15 s maximum sans réponse)')
        with session_factory() as session:
            session.headers.update({'User-Agent': 'MAJIMeeting-model-downloader/0.2.1',
                                    'Accept-Encoding': 'identity'})
            if community and token:
                session.headers['Authorization'] = 'Bearer ' + token.strip()
            with session.get(f'https://huggingface.co/api/models/{repo}/revision/main',
                             params={'blobs': 'true'}, timeout=TIMEOUT) as response:
                response.raise_for_status()
                metadata = response.json()
            _cancel(cancel)
            revision = metadata.get('sha', '')
            if not re.fullmatch('[0-9a-f]{40}', revision):
                raise ValueError('Révision du modèle invalide.')
            files = []
            for entry in metadata.get('siblings', []):
                name = entry.get('rfilename')
                if name not in allowed_files:
                    continue
                size = entry.get('size')
                lfs = entry.get('lfs') or {}
                checksum = lfs.get('sha256') or entry.get('blobId', '')
                algorithm = 'sha256' if lfs else 'sha1'
                length = 64 if algorithm == 'sha256' else 40
                if (not isinstance(size, int) or size <= 0 or
                        not re.fullmatch(f'[0-9a-f]{{{length}}}', checksum)):
                    raise ValueError(f'Métadonnées incomplètes pour {name}.')
                files.append((name, size, algorithm, checksum))
            if not required.issubset({f[0] for f in files}):
                raise ValueError('La liste du modèle ne contient pas les fichiers indispensables.')
            # Small configuration first; model.bin last. Never delete an existing complete model.
            files.sort(key=lambda f: (f[0] == 'model.bin', f[0]))
            total = sum(f[1] for f in files)
            done = 0
            log(f'Revision {revision}; total bytes {total}')
            for name, size, algorithm, checksum in files:
                _cancel(cancel)
                target = destination / name
                target.parent.mkdir(parents=True, exist_ok=True)
                part = destination / (name + '.part')
                state = destination / (name + '.part.json')
                identity = {'size': size, 'algorithm': algorithm, 'checksum': checksum}
                report(f'Vérification de {name}…', round(done * 100 / total))
                if target.is_file() and target.stat().st_size == size:
                    if _digest(target, algorithm, cancel, progress) == checksum:
                        done += size
                        report(f'{name} déjà présent et vérifié', round(done * 100 / total))
                        continue
                try:
                    reusable = json.loads(state.read_text(encoding='utf-8')) == identity
                except (OSError, ValueError):
                    reusable = False
                offset = part.stat().st_size if reusable and part.is_file() else 0
                if offset > size:
                    offset = 0
                if not offset:
                    # Only our incomplete file is reset; completed files are untouched.
                    part.write_bytes(b'')
                state.write_text(json.dumps(identity), encoding='utf-8')
                if shutil.disk_usage(destination).free < size - offset:
                    raise OSError(f'Espace disque insuffisant pour {name}.')
                if offset < size:
                    headers = {'Range': f'bytes={offset}-'} if offset else {}
                    log(f'Transfer {name} from {offset}/{size}')
                    report(f'{name} : connexion / reprise à {offset / 1048576:.1f} Mo…',
                           round((done + offset) * 100 / total))
                    url = f'https://huggingface.co/{repo}/resolve/{revision}/{name}'
                    with session.get(url, headers=headers, stream=True, timeout=TIMEOUT) as response:
                        response.raise_for_status()
                        if response.status_code == 206:
                            if not response.headers.get('Content-Range', '').startswith(f'bytes {offset}-'):
                                raise ValueError(f'Reprise HTTP incohérente pour {name}.')
                        elif response.status_code == 200:
                            offset = 0  # Server ignored Range; restart rather than concatenate.
                        else:
                            raise ValueError(f'Réponse HTTP inattendue : {response.status_code}.')
                        with part.open('ab' if offset else 'wb') as output:
                            for block in response.iter_content(chunk_size=1024 * 1024):
                                _cancel(cancel)
                                if not block:
                                    continue
                                if offset + len(block) > size:
                                    raise ValueError(f'Taille reçue excessive pour {name}.')
                                output.write(block)
                                offset += len(block)
                                report(f'{name} : {offset / 1048576:.1f} / {size / 1048576:.1f} Mo',
                                       round((done + offset) * 100 / total))
                            output.flush()
                            os.fsync(output.fileno())
                _cancel(cancel)
                if part.stat().st_size != size:
                    raise ValueError(f'Téléchargement incomplet pour {name}. Cliquez sur Télécharger pour reprendre.')
                report(f'Contrôle d’intégrité de {name}…', round((done + size) * 100 / total))
                if _digest(part, algorithm, cancel, progress) != checksum:
                    state.unlink(missing_ok=True)  # Next attempt restarts this corrupted partial file.
                    raise ValueError(f'Contrôle d’intégrité échoué pour {name}. Relancez le téléchargement.')
                part.replace(target)
                state.unlink(missing_ok=True)
                done += size
                log(f'Verified {name}')
            manifest = {'repository': repo, 'revision': revision, 'files': [f[0] for f in files]}
            (destination / 'download-manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        report('Modèle téléchargé et vérifié. Prêt pour l’utilisation hors ligne.', 100)
        log('Completed')
        return str(destination)
    except CancelledError:
        log('Cancelled; partial files retained')
        raise
    except requests.Timeout as exc:
        message = 'Le serveur de modèles ne répond pas dans le délai prévu. Relancez pour reprendre.'
        log(f'Timeout: {type(exc).__name__}')
        raise RuntimeError(f'{message} Journal : {log_path}') from exc
    except requests.RequestException as exc:
        status = getattr(getattr(exc, 'response', None), 'status_code', None)
        detail = f'HTTP {status}' if status else type(exc).__name__
        log(f'Network error: {detail}')
        if community and status in {401, 403}:
            raise RuntimeError('Accès Community-1 refusé. Acceptez les conditions sur Hugging Face '
                               'et utilisez un jeton de lecture autorisé. Aucun jeton n’est enregistré.') from None
        raise RuntimeError(f'Échec de connexion au serveur de modèles ({detail}). '
                           f'Vérifiez la connexion et le proxy. Journal : {log_path}') from exc
    except Exception as exc:
        log(f'Failed: {type(exc).__name__}: {exc}')
        raise
