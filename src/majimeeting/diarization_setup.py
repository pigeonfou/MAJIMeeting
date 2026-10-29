"""User-triggered dependency installation and model download, independent of inference."""
import os
import queue
import signal
import subprocess
import sys
import threading
from collections import deque
from pathlib import Path

from majimeeting.model_download import _cancel, download_model


def default_runtime():
    root = Path(os.environ.get('LOCALAPPDATA', str(Path.home())))
    return root / ('MAJIMeeting-DEV/diarization-runtime'
                   if os.environ.get('MAJIMEETING_CHANNEL') == 'dev' else 'MAJIMeeting/runtime')


def setup_script():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent / 'setup-diarization.ps1'
    return Path(__file__).resolve().parents[2] / 'scripts/setup-diarization.ps1'


def stop_process(process):
    """Stop the installer and its pip children before reporting cancellation."""
    if process.poll() is not None:
        return
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                       capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
                       timeout=15, check=False)
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def stream_process(command, cancel=None, progress=lambda message, percent=None: None):
    _cancel(cancel)
    env = os.environ.copy()
    for key in ('PYTHONHOME', 'PYTHONPATH', 'HF_HUB_OFFLINE'):
        env.pop(key, None)
    env['PYTHONIOENCODING'] = 'utf-8'
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               stdin=subprocess.DEVNULL, text=True, encoding='utf-8',
                               errors='replace', env=env, bufsize=1,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                               start_new_session=os.name != 'nt')
    messages = queue.Queue(maxsize=200)
    tail = deque(maxlen=30)

    def read():
        for line in process.stdout:
            try:
                messages.put_nowait(line.rstrip())
            except queue.Full:
                pass

    reader = threading.Thread(target=read, daemon=True, name='majimeeting-runtime-output')
    reader.start()
    try:
        while process.poll() is None or reader.is_alive() or not messages.empty():
            _cancel(cancel)
            try:
                line = messages.get(timeout=.1)
            except queue.Empty:
                continue
            tail.append(line)
            progress(line, None)
        if process.returncode:
            raise RuntimeError('Installation des dépendances échouée. Python 3.11 x64 avec '
                               'le lanceur py est requis.\n' + '\n'.join(tail)[-3000:])
    finally:
        if process.poll() is None:
            stop_process(process)
        reader.join(timeout=2)
        process.stdout.close()


def install_dependencies(device='cuda', cancel=None, progress=lambda message, percent=None: None,
                         runtime_root=None):
    if device not in {'cuda', 'cpu'}:
        raise ValueError('Appareil de calcul invalide.')
    script = setup_script()
    if not script.is_file():
        raise RuntimeError('Script d’installation absent. Réinstallez MAJIMeeting.')
    root = Path(runtime_root) if runtime_root is not None else default_runtime()
    progress('Installation des dépendances ; plusieurs Go peuvent être téléchargés…', None)
    stream_process(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                    '-File', str(script), '-Device', device, '-RuntimeRoot', str(root), '-SkipModel'],
                   cancel, progress)
    python = root / 'Scripts/python.exe'
    if not python.is_file():
        raise RuntimeError('L’installation n’a pas créé le runtime attendu.')
    _cancel(cancel)
    progress('Dépendances installées et imports vérifiés.', 100)
    return str(python)


def download_community(destination, token, cancel=None, progress=lambda message, percent=None: None):
    if not token.strip():
        raise ValueError('Un jeton Hugging Face de lecture autorisé est nécessaire.')
    # Token stays in this call's memory; never passed in argv, files or settings.
    return download_model(destination, cancel, progress, model_name='community-1', token=token)
