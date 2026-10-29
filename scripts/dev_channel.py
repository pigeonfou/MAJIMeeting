"""Verified source-channel manager. Bootstrap uses only Python's standard library."""
import argparse
import contextlib
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import urllib.request
import uuid
import zipfile
from pathlib import Path

REPOSITORY = 'pigeonfou/MAJIMeeting'
SHA = re.compile(r'^[0-9a-f]{40}$')
PIN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]*==[A-Za-z0-9][A-Za-z0-9.+!_-]*$')
MAX_ARCHIVE = 32 * 1024**2
MAX_CONTENT = 64 * 1024**2


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2), encoding='utf-8')
    os.replace(temporary, path)


def read_state(root):
    path = root / 'state.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


@contextlib.contextmanager
def guard(root):
    root.mkdir(parents=True, exist_ok=True)
    with (root / 'manager.guard').open('a+b') as handle:
        try:
            # Windows forbids reads inside a region held by another lock.
            # Metadata can be inspected without touching the locked byte.
            if os.fstat(handle.fileno()).st_size == 0:
                handle.write(b'0')
                handle.flush()
            handle.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError('MAJIMeeting DEV ou sa mise à jour est déjà ouvert. Fermez-le avant de continuer.') from exc
        try:
            yield
        finally:
            if os.name == 'nt':
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


@contextlib.contextmanager
def closed_catalogue(path):
    from PySide6.QtCore import QLockFile
    path.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(path / 'application.lock'))
    if not lock.tryLock(0):
        raise RuntimeError(f'Fermez l’application qui utilise ce catalogue : {path}')
    try:
        yield
    finally:
        lock.unlock()


def fetch(url, limit=MAX_ARCHIVE):
    if not url.startswith(('https://api.github.com/repos/' + REPOSITORY + '/',
                           'https://github.com/' + REPOSITORY + '/releases/download/')):
        raise ValueError('URL de mise à jour étrangère au dépôt.')
    request = urllib.request.Request(url, headers={'User-Agent': 'MAJIMeeting-DEV',
                                                  'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        content = response.read(limit + 1)
    if len(content) > limit:
        raise ValueError('Téléchargement trop volumineux.')
    return content


def latest_bundle():
    print('Recherche de la dernière version DEV validée…', flush=True)
    releases = json.loads(fetch(f'https://api.github.com/repos/{REPOSITORY}/releases?per_page=100', 4 * 1024**2))
    for release in releases:
        commit = release['tag_name'].removeprefix('dev-')
        if not release['tag_name'].startswith('dev-') or not SHA.fullmatch(commit) or release['draft']:
            continue
        assets = {a['name']: a for a in release['assets']}
        if 'dev-manifest.json' not in assets or 'MAJIMeeting-DEV.zip' not in assets:
            continue
        manifest_bytes = fetch(assets['dev-manifest.json']['browser_download_url'], 4 * 1024**2)
        manifest = json.loads(manifest_bytes)
        if manifest['commit'] != commit:
            raise ValueError('Le manifeste ne correspond pas à la release.')
        print('Téléchargement du code validé : ' + commit[:12], flush=True)
        archive = fetch(assets['MAJIMeeting-DEV.zip']['browser_download_url'])
        return manifest, archive
    raise RuntimeError('Aucune version DEV validée publiée pour le moment.')


def validate_manifest(manifest):
    if manifest.get('format') != 1 or manifest.get('repository') != REPOSITORY:
        raise ValueError('Format ou dépôt du manifeste invalide.')
    if not SHA.fullmatch(manifest.get('commit', '')) or manifest.get('data_schema') != 1:
        raise ValueError('Commit ou format des données non pris en charge.')
    if manifest.get('python') != '3.11' or manifest.get('platform') != 'win_amd64':
        raise ValueError('Ce canal requiert Python3.11 Windows x64.')
    pins = manifest.get('requirements', [])
    if not pins or any(not PIN.fullmatch(pin) for pin in pins):
        raise ValueError('Dépendances non figées ou invalides.')
    if digest(('\n'.join(pins) + '\n').encode()) != manifest.get('runtime'):
        raise ValueError('Empreinte des dépendances invalide.')
    files = manifest.get('files', {})
    if not files or len(files) > 5000 or sum(f['size'] for f in files.values()) > MAX_CONTENT:
        raise ValueError('Liste de fichiers invalide ou trop volumineuse.')
    for name, info in files.items():
        path = Path(name)
        if (path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name or
                not name or name.startswith('.') or info['size'] < 0):
            raise ValueError('Chemin de fichier invalide.')
    for required in ['scripts/dev_channel.py', 'scripts/dev_launch.py', 'scripts/run_source.py',
                     'requirements-dev-runtime.txt', 'src/majimeeting/__main__.py']:
        if required not in files:
            raise ValueError('Version source incomplète.')


def extract_verified(manifest, archive, destination):
    validate_manifest(manifest)
    if len(archive) > MAX_ARCHIVE or digest(archive) != manifest.get('archive_sha256'):
        raise ValueError('Archive endommagée ou empreinte différente.')
    import io
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        members = bundle.infolist()
        if len(members) != len(manifest['files']) or {i.filename for i in members} != set(manifest['files']):
            raise ValueError('Fichiers manquants, supplémentaires ou dupliqués.')
        for member in members:
            expected = manifest['files'][member.filename]
            if stat.S_ISLNK(member.external_attr >> 16) or member.file_size != expected['size']:
                raise ValueError('Type ou taille de fichier invalide.')
            data = bundle.read(member)
            if digest(data) != expected['sha256']:
                raise ValueError('Intégrité du fichier invalide : ' + member.filename)
            target = destination / member.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    pins = [line.strip() for line in (destination / 'requirements-dev-runtime.txt').read_text().splitlines()
            if line.strip() and not line.startswith('#')]
    if pins != manifest['requirements']:
        raise ValueError('Dépendances du code différentes du manifeste.')
    atomic_json(destination / 'dev-manifest.json', manifest)


def verify_source(source, manifest):
    validate_manifest(manifest)
    for name, expected in manifest['files'].items():
        path = source / name
        if not path.is_file() or path.is_symlink() or digest(path.read_bytes()) != expected['sha256']:
            raise ValueError('Version locale modifiée ou incomplète : ' + name)


def runtime_python(root, runtime):
    return root / 'runtimes' / runtime / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def child_environment(root, state, commit):
    env = os.environ.copy()
    for key in ('PYTHONHOME', 'PYTHONPATH'):
        env.pop(key, None)
    env.update(MAJIMEETING_CHANNEL='dev', MAJIMEETING_SOURCE_COMMIT=commit,
               MAJIMEETING_DATA_ROOT=str(state.get('data', root / 'data')))
    return env


def prepare_runtime(root, manifest, source):
    runtime = manifest['runtime']
    python = runtime_python(root, runtime)
    ready = python.parent.parent / 'runtime-ready.json'
    if ready.exists() and json.loads(ready.read_text()) == {'runtime': runtime}:
        return
    print('Préparation initiale des dépendances (réutilisées aux mises à jour suivantes)…', flush=True)
    env = os.environ.copy()
    env.pop('PYTHONHOME', None)
    env.pop('PYTHONPATH', None)
    if not python.is_file():
        subprocess.run([sys.executable, '-I', '-m', 'venv', str(python.parent.parent)], check=True, env=env)
    pins = python.parent.parent / 'requirements.txt'
    pins.write_text('\n'.join(manifest['requirements']) + '\n', encoding='utf-8')
    subprocess.run([str(python), '-I', '-m', 'pip', 'install', '--disable-pip-version-check',
                    '-r', str(pins)], check=True, env=env)
    subprocess.run([str(python), '-I', '-m', 'pip', 'check'], check=True, env=env)
    atomic_json(ready, {'runtime': runtime})


def smoke(root, manifest, source):
    print('Vérification du démarrage de la nouvelle version…', flush=True)
    with tempfile.TemporaryDirectory(prefix='smoke-', dir=root) as temporary:
        env = child_environment(root, {'data': temporary}, manifest['commit'])
        env['QT_QPA_PLATFORM'] = 'offscreen'
        subprocess.run([str(runtime_python(root, manifest['runtime'])), '-I', '-X', 'utf8',
                        str(source / 'scripts/run_source.py'), '--smoke-test'],
                       check=True, timeout=60, env=env)


def activate(root, manifest, archive, prepare=prepare_runtime, check=smoke):
    validate_manifest(manifest)
    commit = manifest['commit']
    source = root / 'versions' / commit
    (root / 'versions').mkdir(parents=True, exist_ok=True)
    state = read_state(root)
    with tempfile.TemporaryDirectory(prefix='staging-', dir=root) as temporary:
        staged = Path(temporary) / 'source'
        extract_verified(manifest, archive, staged)
        if source.exists():
            verify_source(source, manifest)
        else:
            os.replace(staged, source)
    prepare(root, manifest, source)
    check(root, manifest, source)
    current = dict(commit=commit, runtime=manifest['runtime'], data_schema=manifest['data_schema'])
    if state.get('current') != current:
        previous = state.get('current')
        state.update(current=current, previous=previous)
    state.setdefault('data', str(root / 'data'))
    # Atomic pointer changes only after download, integrity, environment and smoke pass.
    launcher = root / 'launcher.tmp'
    shutil.copyfile(source / 'scripts/dev_launch.py', launcher)
    os.replace(launcher, root / 'launcher.py')
    atomic_json(root / 'state.json', state)
    return state


def rollback(root):
    state = read_state(root)
    previous = state.get('previous')
    if not previous or previous['data_schema'] != state['current']['data_schema']:
        raise RuntimeError('Aucune version précédente compatible disponible.')
    source = root / 'versions' / previous['commit']
    manifest = json.loads((source / 'dev-manifest.json').read_text())
    verify_source(source, manifest)
    smoke(root, manifest, source)
    state['current'], state['previous'] = previous, state['current']
    atomic_json(root / 'state.json', state)


def copy_catalogue(root, source):
    state = read_state(root)
    if not (source / 'meetings.sqlite3').is_file():
        raise RuntimeError('Aucun catalogue habituel trouvé : ' + str(source))
    target = root / 'datasets' / ('copie-' + uuid.uuid4().hex)
    target.parent.mkdir(parents=True, exist_ok=True)
    def copying(first, second):
        if Path(first).is_symlink():
            raise ValueError('Lien symbolique refusé dans le catalogue.')
        return shutil.copy2(first, second)
    print('Copie des réunions et audios vers ' + str(target) + ' (les originaux restent inchangés)…', flush=True)
    try:
        shutil.copytree(source, target, copy_function=copying, ignore=shutil.ignore_patterns(
            'application.lock', 'meetings.sqlite3', 'meetings.sqlite3-wal', 'meetings.sqlite3-shm'))
        with sqlite3.connect(source / 'meetings.sqlite3') as original, sqlite3.connect(target / 'meetings.sqlite3') as clone:
            original.backup(clone)
        state['data'] = str(target)
        atomic_json(root / 'state.json', state)
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise
    return target


def run(root, state, extra=()):
    current = state['current']
    source = root / 'versions' / current['commit']
    verify_source(source, json.loads((source / 'dev-manifest.json').read_text()))
    # manager.guard stays held throughout the application's lifetime.
    with closed_catalogue(Path(state['data'])):
        pass
    log = root / 'logs'
    log.mkdir(exist_ok=True)
    with (log / ('application-' + current['commit'][:12] + '.log')).open('a', encoding='utf-8') as output:
        subprocess.run([str(runtime_python(root, current['runtime'])), '-I', '-X', 'utf8',
                        str(source / 'scripts/run_source.py'), *extra],
                       check=True, env=child_environment(root, state, current['commit']),
                       stdout=output, stderr=output,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def notify(message, error=False):
    print(message, flush=True)
    if os.name == 'nt' and not os.environ.get('MAJIMEETING_DEV_TEST'):
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, 'MAJIMeeting DEV', 0x10 if error else 0x40)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('action', choices=['bootstrap', 'run', 'update', 'rollback', 'copy-data'])
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--smoke', action='store_true')
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        with guard(root):
            state = read_state(root)
            if args.action == 'run':
                run(root, state, ['--smoke-test'] if args.smoke else [])
                return 0
            if args.action == 'bootstrap':
                if sys.version_info[:2] != (3, 11) or sys.platform != 'win32' or sys.maxsize <= 2**32:
                    raise RuntimeError('Installez Python3.11 x64 avec le lanceur py, puis relancez.')
                if state:
                    source = root / 'versions' / state['current']['commit']
                    verify_source(source, json.loads((source / 'dev-manifest.json').read_text()))
                    temporary = root / 'launcher.tmp'
                    shutil.copyfile(source / 'scripts/dev_launch.py', temporary)
                    os.replace(temporary, root / 'launcher.py')
                    notify('DEV est déjà installé. Les raccourcis vont être réparés ; utilisez ensuite Mettre à jour.')
                    return 0
            @contextlib.contextmanager
            def available():
                if state:
                    with closed_catalogue(Path(state['data'])):
                        yield
                else:
                    yield
            with available():
                if args.action in {'update', 'bootstrap'}:
                    if bool(args.manifest) != bool(args.bundle):
                        raise ValueError('Le manifeste et l’archive doivent être fournis ensemble.')
                    manifest, archive = ((json.loads(args.manifest.read_text()), args.bundle.read_bytes())
                                          if args.manifest else latest_bundle())
                    activate(root, manifest, archive)
                    message = ('Version DEV prête : ' + manifest['commit'][:12] +
                               '. Modèles et réunions habituelles conservés.')
                    if args.action == 'bootstrap':
                        notify(message)
                    else:
                        print(message, flush=True)
                elif args.action == 'rollback':
                    rollback(root)
                    notify('Version précédente réactivée. Les données DEV sont conservées.')
                elif args.action == 'copy-data':
                    ordinary = Path(os.environ['LOCALAPPDATA']) / 'MAJIMeeting/data'
                    with closed_catalogue(ordinary):
                        target = copy_catalogue(root, ordinary)
                    notify('Copie prête : ' + str(target) + '. Lancez MAJIMeeting DEV.')
        if args.action == 'update':
            state = read_state(root)
            python = runtime_python(root, state['current']['runtime'])
            if os.name == 'nt':
                python = python.with_name('pythonw.exe')
            subprocess.Popen([str(python), '-I', '-X', 'utf8', str(root / 'launcher.py'), 'run'],
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return 0
    except Exception as exc:
        root.mkdir(parents=True, exist_ok=True)
        with (root / 'dev-errors.log').open('a', encoding='utf-8') as log:
            import traceback
            traceback.print_exc(file=log)
        notify(str(exc) + '\nJournal : ' + str(root / 'dev-errors.log'), error=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
