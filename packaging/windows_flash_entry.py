"""Separate executable and window title, sharing the existing single-instance data lock."""
if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    import sys
    if '--flash-build-check' in sys.argv:
        from majimeeting.flash_build import verify_native_flash
        verify_native_flash()
        raise SystemExit(0)
    from majimeeting import __main__ as application

    BaseWindow = application.MainWindow

    class FlashWindow(BaseWindow):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.setWindowTitle('MAJIMeeting — Flash expérimental (RTX 3080)')

    application.MainWindow = FlashWindow
    raise SystemExit(application.main())
