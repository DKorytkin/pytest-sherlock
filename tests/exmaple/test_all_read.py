def test_passed():
    assert True


def test_read_params(config, param):
    assert config.get(param) == 2


def test_do_nothing():
    pass
