"""Stable, standard-library trampoline; shortcuts always follow the active version."""
import json
import os
import subprocess
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent
    state = json.loads((root / 'state.json').read_text(encoding='utf-8'))
    current = state['current']
    source = root / 'versions' / current['commit']
    name = 'pythonw.exe' if sys.argv[1:] == ['run'] else 'python.exe'
    python = root / 'runtimes' / current['runtime'] / ('Scripts/' + name)
    if not python.is_file():
        python = python.with_name('python.exe')
    env = os.environ.copy()
    env.pop('PYTHONHOME', None)
    env.pop('PYTHONPATH', None)
    return subprocess.call([str(python), '-I', '-X', 'utf8', str(source / 'scripts/dev_channel.py'),
                            '--root', str(root), *sys.argv[1:]], env=env)


if __name__ == '__main__':
    raise SystemExit(main())
