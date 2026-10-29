"""Entry point for an extracted, verified source version (no editable install)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from majimeeting.__main__ import main  # noqa: E402

if __name__ == '__main__':
    raise SystemExit(main())
