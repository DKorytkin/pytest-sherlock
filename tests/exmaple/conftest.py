import json
import os

import pytest

pytest_plugins = "pytest_sherlock.plugin"
EXAMPLE_ROOT = os.path.dirname(os.path.abspath(__file__))


@pytest.fixture(scope="session")
def config():
    """
    Very "huge" function
    :return: config file
    """
    file_path = os.path.join(EXAMPLE_ROOT, "data/data.json")
    with open(file_path, "r") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def param():
    return "b"
