

def test_delete_random_param(config):
    del config["c"]
    assert config.get("c") is None
