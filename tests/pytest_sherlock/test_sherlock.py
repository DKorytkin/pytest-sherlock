import mock
import pytest
from _pytest.nodes import Item

from pytest_sherlock.sherlock import TestCollection


class TestTestCollection(object):

    @pytest.fixture(scope="class")
    def items(self):
        fixture_names = ["my_fixture", "fixture_do_something", "other_fixture"]
        pytest_items = []
        for item in ["one", "two", "tree", "four", "five", "six"]:
            pytest_func = mock.MagicMock(spec=Item)
            pytest_func.name = "test_{}".format(item)
            node = mock.MagicMock(spec=Item)
            node.nodeid = "tests/test_{}.py".format(item)
            pytest_func.parent = node
            pytest_func.nodeid = "{}::{}".format(pytest_func.parent.nodeid, pytest_func.name)
            pytest_func.fixturenames = []
            pytest_items.append(pytest_func)

        # ['other_fixture'] for test_one
        pytest_items[0].fixturenames[:] = fixture_names[2:]
        # ['fixture_do_something', 'other_fixture'] for test_tree
        pytest_items[2].fixturenames[:] = fixture_names[1:]
        # ['my_fixture', 'fixture_do_something', 'other_fixture'] for test_five
        pytest_items[4].fixturenames[:] = fixture_names  # should target_test
        # ['my_fixture', 'fixture_do_something', 'other_fixture'] for test_six
        pytest_items[-1].fixturenames[:] = fixture_names
        return pytest_items

    @pytest.fixture()
    def collection(self, items):
        return TestCollection(items)

    def test_create_instance(self, items):
        tc = TestCollection(items)
        assert tc.items == items
        assert tc.test_func is None

    def test_find_needed_tests_by_name(self, collection):
        """
        Method needed_tests must return list of tests which was ran before target test (flaky)
        and have use the same fixtures

        'tests/test_tree.py::test_tree'
        'tests/test_one.py::test_one'
        'tests/test_two.py::test_two'
        'tests/test_four.py::test_four

        >> 'tests/test_five.py::test_five
        """
        target_test_func_name = "test_five"
        sorted_items = collection.needed_tests(target_test_func_name)
        assert len(sorted_items) == 4  # the rest must cut
