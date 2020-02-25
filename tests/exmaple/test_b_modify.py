

def test_modified_passed():
    assert True


def test_modify_random_param(config, param):
    new_value = 13
    config[param] = new_value
    assert config.get(param) == new_value


def test_do_not_modified():
    pass


def test_flaky():
    import random
    assert random.choice([True, False])

