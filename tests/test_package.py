from majimeeting import __version__


def test_version_is_defined():
    assert __version__.startswith("0.2.")

