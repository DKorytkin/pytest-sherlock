

def test_read_params(config, param):
    assert config.get(param) == 2
