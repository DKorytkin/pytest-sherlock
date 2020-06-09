import mock
import pytest
from _pytest.config import Config
from _pytest.nodes import Item

from pytest_sherlock.sherlock import Collection, Sherlock


FAKE_FIXTURE_NAMES = ["my_fixture", "fixture_do_something", "other_fixture"]


def make_fake_test_item(name, *fixtures):
    pytest_func = mock.MagicMock(spec=Item)
    pytest_func.name = "test_{}".format(name)
    node = mock.MagicMock(spec=Item)
    node.nodeid = "tests/test_{}.py".format(name)
    pytest_func.parent = node
    pytest_func.nodeid = "{}::{}".format(pytest_func.parent.nodeid, pytest_func.name)
    pytest_func.fixturenames = [f for f in fixtures]
    ihook = mock.MagicMock()
    ihook.pytest_runtest_logreport.return_value = True
    ihook.pytest_runtest_logstart.return_value = True
    ihook.pytest_runtest_logfinish.return_value = True
    pytest_func.ihook = ihook
    return pytest_func


@pytest.fixture(scope="function")
def target_item():
    return make_fake_test_item("five")


@pytest.fixture(scope="function")
def items(target_item):
    pytest_items = [make_fake_test_item(item) for item in ["one", "two", "tree", "four", "six"]]
    pytest_items.insert(4, target_item)  # between four and six

    # ['other_fixture'] for test_one
    pytest_items[0].fixturenames[:] = FAKE_FIXTURE_NAMES[2:]
    # ['fixture_do_something', 'other_fixture'] for test_tree
    pytest_items[2].fixturenames[:] = FAKE_FIXTURE_NAMES[1:]
    # ['my_fixture', 'fixture_do_something', 'other_fixture'] for test_five
    pytest_items[4].fixturenames[:] = FAKE_FIXTURE_NAMES[:]  # should target_test
    # ['my_fixture', 'fixture_do_something', 'other_fixture'] for test_six
    pytest_items[-1].fixturenames[:] = FAKE_FIXTURE_NAMES[:]
    return pytest_items


@pytest.fixture(scope="function")
def collection(items):
    return Collection(items)


@pytest.fixture(scope="function")
def sherlock_with_prepared_collection(sherlock, collection, target_item):
    sherlock.collection = collection
    sherlock.collection.prepare(target_item.nodeid)
    return sherlock


class TestCollection(object):

    def test_create_instance(self, items):
        tc = Collection(items)
        assert tc.items == items
        assert tc.test_func is None

    @pytest.mark.parametrize(
        "by",
        ("test_five", "tests/test_five.py::test_five"),
        ids=["name", "node_id"]
    )
    def test_find_needed_tests(self, collection, by):
        """
        Method needed_tests must return list of tests which was ran before target test (flaky)
        and have use the same fixtures

        'tests/test_tree.py::test_tree'
        'tests/test_one.py::test_one'
        'tests/test_two.py::test_two'
        'tests/test_four.py::test_four'

        >> 'tests/test_five.py::test_five'
        """
        exp_tests = [
            "tests/test_tree.py::test_tree",
            "tests/test_one.py::test_one",
            "tests/test_two.py::test_two",
            "tests/test_four.py::test_four",
        ]
        sorted_items = collection._needed_tests(by)
        assert len(sorted_items) == 4  # the rest must cut
        assert [item.nodeid for item in sorted_items] == exp_tests
        assert collection.test_func is not None
        assert collection.test_func.name == "test_five"
        assert collection.test_func.nodeid == "tests/test_five.py::test_five"

    def test_not_found_needed_tests(self, collection):
        with pytest.raises(RuntimeError):
            collection._needed_tests("tests/which/not_exist.py::test_fake")


class TestSherlock(object):

    @pytest.fixture()
    def config(self):
        plugin_manager = mock.MagicMock()
        return mock.MagicMock(spec=Config, pluginmanager=plugin_manager)

    @pytest.fixture()
    def sherlock(self, config):
        return Sherlock(config=config)

    def test_create_instance(self):
        config = mock.MagicMock(spec=Config)  # pytest config
        sherlock = Sherlock(config)
        assert sherlock.config == config
        assert sherlock._tw is None
        assert sherlock._reporter is None
        assert sherlock._coupled is None

    def test_first_call_terminal(self, sherlock):
        assert sherlock._tw is None
        assert callable(sherlock.terminal)
        assert sherlock._tw is sherlock.terminal

    def test_call_exist_terminal(self, sherlock):
        sherlock.tw = mock.MagicMock()
        assert sherlock.terminal is not None  # from cache
        sherlock.terminal.write("some line # 1")
        sherlock.terminal.write("some line # 2")
        sherlock.config.get_terminal_writer.assert_not_called()

    @pytest.mark.parametrize("line", ("123", 12), ids=["string", "integer"])
    def test_write_step_to_terminal(self, sherlock, line):
        """
        test expected message like:
        ________ Step [123 of 666] ________
        """
        sherlock._tw = mock.MagicMock()  # just for mock terminal
        sherlock.write_step(line, 666)
        sherlock.reporter.ensure_newline.assert_called_once()
        exp_msg = "Step [{} of 666]:".format(line)
        sherlock.terminal.sep.assert_called_once_with("_", exp_msg, yellow=True, bold=True)

    def test_log(self, sherlock, target_item):
        with mock.patch(
                "pytest_sherlock.sherlock.Sherlock.reporter",
                new_callable=mock.PropertyMock,
        ) as m:
            m.return_value = mock.MagicMock(**{"pytest_runtest_logreport.return_value": True})
            with sherlock.log(target_item) as logger:
                sherlock.reporter.pytest_runtest_logstart.assert_called_once_with(
                    nodeid=target_item.nodeid, location=target_item.location
                )
                assert logger() is True
            sherlock.reporter.pytest_runtest_logreport.assert_called_once()
            sherlock.reporter.pytest_runtest_logfinish.assert_called_once_with(
                nodeid=target_item.nodeid
            )

    @pytest.mark.parametrize("by", ("name", "nodeid"))
    def test_pytest_collection_modifyitems_with_option(self, sherlock, items, target_item, by):
        config = mock.MagicMock()
        config.getoption.return_value = True
        config.option.flaky_test = getattr(target_item, by)
        next(
            sherlock.pytest_collection_modifyitems(
                session=mock.MagicMock(), config=config, items=items
            )
        )
        assert items == [target_item]
        config.getoption.assert_called_once()

    @pytest.mark.parametrize("by", ("name", "nodeid"))
    def test_pytest_collection_modifyitems_without_option(self, sherlock, items, target_item, by):
        config = mock.MagicMock()
        config.getoption.return_value = False
        config.option.flaky_test = getattr(target_item, by)
        next(
            sherlock.pytest_collection_modifyitems(
                session=mock.MagicMock(), config=config, items=items
            )
        )
        assert items == items
        config.getoption.assert_called_once()

    def test_pytest_report_collectionfinish(self, sherlock_with_prepared_collection):
        """
        Collection:
        [
            'tests/test_one.py::test_one',
            'tests/test_two.py::test_two',
            'tests/test_tree.py::test_tree',
            'tests/test_four.py::test_four',
            'tests/test_five.py::test_five',
            'tests/test_six.py::test_six',
        ]
        Target item: 'tests/test_five.py::test_five'
        Prepared collection (filtered by target item):
        ____________________________________________
        || index | test                           ||
        --------------------------------------------
        | 0      | 'tests/test_one.py::test_one'   |
        | 1      | 'tests/test_two.py::test_two'   |
        | 2      | 'tests/test_tree.py::test_tree' |
        | 3      | 'tests/test_four.py::test_four' |
        --------------------------------------------

        Binary tree search:
                        First step
                        /        \
                    [0, 1]       [2, 3]
             Second step            Second step
            /           \          /          \
         [0]            [1]     [2]           [3]
        """
        report = sherlock_with_prepared_collection.pytest_report_collectionfinish(
            config=mock.MagicMock(), startdir=mock.MagicMock(), items=items
        )
        assert report == "Try to find coupled tests in [2-3] steps"
