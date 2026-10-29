"""Entry point for verified sources, with dependency checks before opening the GUI."""
import importlib.metadata
import sys
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet

ROOT = Path(__file__).resolve().parents[1]


def check_runtime():
    project = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']
    version = '.'.join(map(str, sys.version_info[:3]))
    if version not in SpecifierSet(project['requires-python']):
        raise RuntimeError('Version de Python incompatible avec cette version source.')
    for specification in project['dependencies']:
        requirement = Requirement(specification)
        if requirement.marker and not requirement.marker.evaluate():
            continue
        try:
            installed = importlib.metadata.version(requirement.name)
        except importlib.metadata.PackageNotFoundError as exc:
            raise RuntimeError('Dépendance manquante : ' + requirement.name +
                               '. Relancez la mise à jour DEV.') from exc
        if installed not in requirement.specifier:
            raise RuntimeError('Dépendance incompatible : ' + requirement.name)


if __name__ == '__main__':
    check_runtime()
    sys.path.insert(0, str(ROOT / 'src'))
    from majimeeting.__main__ import main
    raise SystemExit(main())
