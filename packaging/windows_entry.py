if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    from majimeeting.__main__ import main
    raise SystemExit(main())
