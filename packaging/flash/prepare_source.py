"""Add a native capability probe; do not modify attention kernels or model mathematics."""
import json
import subprocess
import sys
from pathlib import Path

PIN = '5de572ef60b67a0276c5989ee73d0072808ff4c3'


def prepare(source):
    source = Path(source)
    actual = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'],
                                     text=True).strip()
    if actual != PIN:
        raise ValueError('Unexpected upstream source commit')
    cmake = source / 'CMakeLists.txt'
    text = cmake.read_text(encoding='utf-8')
    needle = 'set(SOURCES\n'
    if text.count(needle) != 1:
        raise ValueError('Unexpected source list')
    cmake.write_text(text.replace(needle, needle + '  src/majimeeting_flash_probe.cc\n'),
                     encoding='utf-8')
    (source / 'src/majimeeting_flash_probe.cc').write_text('''extern "C" __declspec(dllexport)
int majimeeting_flash_compiled() {
#ifdef CT2_WITH_FLASH_ATTN
  return 1;
#else
  return 0;
#endif
}
''', encoding='utf-8')
    package = source / 'python/ctranslate2'
    metadata = {'source_commit': PIN, 'flash_attention_compiled': True,
                'cuda_arch': '8.6', 'cuda_toolkit': '12.8.1', 'cpu_backend': 'RUY',
                'experimental': True, 'gpu_inference_verified': False}
    (package / 'majimeeting_flash_build.json').write_text(json.dumps(metadata, indent=2),
                                                        encoding='utf-8')
    notices = ['CTranslate2 source: ' + PIN,
               Path(__file__).with_name('FLASH_ATTENTION_LICENSE.txt').read_text(encoding='utf-8')]
    for legal in sorted(source.rglob('*')):
        if legal.is_file() and '.git' not in legal.parts and legal.name.upper().startswith(
                ('LICENSE', 'COPYING', 'NOTICE')):
            notices.append('\n--- ' + str(legal.relative_to(source)) + ' ---\n' +
                           legal.read_text(encoding='utf-8', errors='replace'))
    (package / 'majimeeting_flash_licenses.txt').write_text('\n'.join(notices), encoding='utf-8')
    setup = source / 'python/setup.py'
    setup_text = setup.read_text(encoding='utf-8')
    original = 'package_data["ctranslate2"] = ["*.dll"]'
    if original not in setup_text:
        raise ValueError('Unexpected wheel metadata')
    setup.write_text(setup_text.replace(original,
                     'package_data["ctranslate2"] = ["*.dll", "majimeeting_flash_build.json", "majimeeting_flash_licenses.txt"]'),
                     encoding='utf-8')


if __name__ == '__main__':
    prepare(sys.argv[1])
