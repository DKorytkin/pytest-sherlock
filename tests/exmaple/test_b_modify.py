import random


def test_modified_passed():
    assert True


def test_modify_random_param(config):
    config["b"] = 13
    assert config.get("b") == 13


def test_do_not_modified():
    pass


def test_flaky():
    assert random.choice([True, False])
