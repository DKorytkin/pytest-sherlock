def test_deleted_passed():
    assert True


def test_delete_random_param(config):
    del config["c"]
    assert config.get("c") is None


def test_do_not_delete():
    pass
