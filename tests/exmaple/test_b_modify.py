

def test_modify_random_param(config, param):
    new_value = 13
    config[param] = new_value
    assert config.get(param) == new_value
