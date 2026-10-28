"""Separate experimental executable with persistent startup diagnostics."""
import os
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


def run():
    if '--flash-build-check' in sys.argv:
        from majimeeting.flash_build import verify_native_flash
        print(verify_native_flash())
        return 0
    from majimeeting import __main__ as application

    BaseWindow = application.MainWindow

    class FlashWindow(BaseWindow):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.setWindowTitle('MAJIMeeting — Flash expérimental (RTX 3080)')

    application.MainWindow = FlashWindow
    return application.main()


def main():
    # Windowed PyInstaller displays an error dialog for uncaught exceptions. In CI
    # that dialog looks like a hang; retain the traceback and return a failure.
    default = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'MAJIMeeting'
    log = Path(os.environ.get('MAJIMEETING_DIAGNOSTIC_LOG', default / 'flash-startup.log'))
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('a', encoding='utf-8', buffering=1) as output:
        with redirect_stdout(output), redirect_stderr(output):
            print('Starting Flash executable:', sys.argv, flush=True)
            try:
                result = run()
            except Exception:
                traceback.print_exc()
                return 1
            print('Exit:', result, flush=True)
            return result


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    raise SystemExit(main())
