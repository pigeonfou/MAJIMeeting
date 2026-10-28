import json
import sys
from types import SimpleNamespace

import pytest

from majimeeting.flash_build import verify_native_flash


@pytest.mark.parametrize('native_flag', [0, 1])
def test_native_probe_overrules_python_marker(tmp_path, monkeypatch, native_flag):
    import majimeeting.flash_build as check
    marker = {'source_commit': '5de572ef60b67a0276c5989ee73d0072808ff4c3',
              'flash_attention_compiled': True}
    (tmp_path / 'majimeeting_flash_build.json').write_text(json.dumps(marker))
    monkeypatch.setitem(sys.modules, 'ctranslate2',
                        SimpleNamespace(__file__=str(tmp_path / '__init__.py')))

    class Probe:
        def __call__(self):
            return native_flag

    monkeypatch.setattr(check.ctypes, 'CDLL', lambda _: SimpleNamespace(
        majimeeting_flash_compiled=Probe()))
    if native_flag:
        result = verify_native_flash()
        assert result['native_flash_compiled'] is True
        assert result['gpu_inference_verified'] is False
    else:
        with pytest.raises(RuntimeError, match='does not report'):
            verify_native_flash()
