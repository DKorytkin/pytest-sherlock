import argparse

import mock
import pytest
from _pytest.config import Config, PytestPluginManager
from _pytest.junitxml import _NodeReporter
from _pytest.python import Function
from _pytest.runner import TestReport as PytestReport
from _pytest.terminal import TerminalReporter

from pytest_sherlock.sherlock import Sherlock, log, refresh_state, write_coupled_report

FAKE_FIXTURE_NAMES = ["my_fixture", "fixture_do_something", "other_fixture"]


def make_fake_test_item(name, *fixtures):
    pytest_func = mock.MagicMock(spec=Function)
    pytest_func.name = "test_{}".format(name)
    node = mock.MagicMock(spec=Function)
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
    pytest_items = [
        make_fake_test_item(item) for item in ["one", "two", "tree", "four", "six"]
    ]
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


@pytest.fixture
def session():
    return mock.MagicMock()


@pytest.fixture
def reporter():
    return mock.MagicMock(spec=TerminalReporter, stats={})


@pytest.fixture
def step():
    return None


@pytest.fixture
def cache():
    m = mock.MagicMock()
    m.get.return_value = None
    return m


@pytest.fixture
def config(target_item, reporter, step, cache):
    plugin_manager = mock.MagicMock(spec=PytestPluginManager)
    plugin_manager.get_plugin.return_value = reporter
    option_namespace = argparse.Namespace(flaky_test=target_item.nodeid, step=step)
    c = mock.MagicMock(
        spec=Config, pluginmanager=plugin_manager, option=option_namespace
    )
    c.cache = cache
    c.getvalue.return_value = 2
    return c


@pytest.fixture
def sherlock(config):
    return Sherlock(config=config)


@pytest.fixture
def sherlock_with_prepared_collection(sherlock, config, session, items, target_item):
    """
    Target tests:
        0, 'tests/test_tree.py::test_tree'
        1, 'tests/test_one.py::test_one'
        2, 'tests/test_two.py::test_two'
        3, 'tests/test_four.py::test_four'

    Example of tree:
              ________(0, 4)_________
             /                       \
        __(0, 2)___             __(2, 4)___
       /           \           /           \
    (0, 1)      (1, 2)      (2, 3)      (3, 4)
    """
    sherlock.config.getoption.return_value = True
    next(sherlock.pytest_sessionstart(session))
    next(sherlock.pytest_collection_modifyitems(session, config, items))
    return sherlock


class TestCleanupItem(object):
    @pytest.fixture
    def fixtures(self):
        mock_fixtures = (
            mock.MagicMock(cached_result="1", argname="fixture1"),
            mock.MagicMock(cached_result=2, argname="fixture2"),
        )
        return {f.argname: (f,) for f in mock_fixtures}

    @pytest.fixture
    def stack(self):
        return [mock.MagicMock(_prepare_exc=1)]

    @pytest.fixture
    def called_item(self, target_item, fixtures, stack):
        # added cached results of fixtures
        target_item._fixtureinfo = mock.MagicMock(name2fixturedefs=fixtures)
        # added cache to session
        target_item.session = mock.MagicMock(_setupstate=mock.MagicMock(stack=stack))
        return target_item

    @staticmethod
    def check_cleanup_fixtures(fixtures):
        assert fixtures
        for funcs in fixtures.values():
            for func in funcs:
                assert not hasattr(
                    func, "cached_result"
                ), "cached_result wasn't cleanup"

    @staticmethod
    def check_cleanup_stack(stack):
        assert stack
        for cal in stack:
            assert not hasattr(cal, "_prepare_exc"), "_prepare_exc wasn't delete"

    def test_refresh_state(self, called_item, fixtures, stack):
        assert refresh_state(called_item)
        self.check_cleanup_fixtures(fixtures)
        self.check_cleanup_stack(stack)

    def test_write_coupled_report_without_fixtures(self, called_item):
        coupled_tests = [
            make_fake_test_item("test1"),
            make_fake_test_item("test2"),
        ]
        exp_message = (
            "Found coupled tests:\n"
            "tests/test_test1.py::test_test1\n"
            "tests/test_test2.py::test_test2\n\n"
            "How to reproduce:\n"
            "pytest -l -vv tests/test_test1.py::test_test1 tests/test_test2.py::test_test2\n"
        )
        assert write_coupled_report(coupled_tests) == exp_message

    def test_write_coupled_report_with_common_fixtures(self, called_item):
        coupled_tests = [
            make_fake_test_item("test1", "fixture1", "fixture2"),
            make_fake_test_item("test2", "fixture2"),
        ]
        exp_message = (
            "Found coupled tests:\n"
            "tests/test_test1.py::test_test1\n"
            "tests/test_test2.py::test_test2\n\n"
            "Common fixtures:\n"
            "fixture2\n\n"
            "How to reproduce:\n"
            "pytest -l -vv tests/test_test1.py::test_test1 tests/test_test2.py::test_test2\n"
        )
        assert write_coupled_report(coupled_tests) == exp_message

    def test_write_coupled_report_without_common_fixtures(self, called_item):
        coupled_tests = [
            make_fake_test_item("test1", "fixture1", "fixture2"),
            make_fake_test_item("test2", "fixture3"),
        ]
        exp_message = (
            "Found coupled tests:\n"
            "tests/test_test1.py::test_test1\n"
            "tests/test_test2.py::test_test2\n\n"
            "How to reproduce:\n"
            "pytest -l -vv tests/test_test1.py::test_test1 tests/test_test2.py::test_test2\n"
        )
        assert write_coupled_report(coupled_tests) == exp_message


class TestSherlock(object):
    @pytest.fixture
    def sherlock_with_failures(self, sherlock_with_prepared_collection):
        sherlock_with_prepared_collection.reporter.stats["failed"] = [1, 2, 3, 4]
        return sherlock_with_prepared_collection

    @pytest.fixture
    def mock_coupled(self):
        mock_coupled = [
            make_fake_test_item("test1"),
            make_fake_test_item("test2"),
        ]
        return mock_coupled

    @pytest.fixture
    def mock_report_str(self):
        return mock.MagicMock(spec=PytestReport, longrepr="AssertError: 1 != 2")

    @pytest.fixture
    def mock_report_class(self):
        class LongReprStub(object):
            def __init__(self, msg):
                self.msg = msg

            def __str__(self):
                return self.msg

        return mock.MagicMock(
            spec=PytestReport, longrepr=LongReprStub("AssertError: 1 != 2")
        )

    @pytest.fixture
    def mock_report_crash(self):
        longrepr = mock.MagicMock(
            reprcrash=mock.MagicMock(message="AssertError: 1 != 2")
        )
        return mock.MagicMock(spec=PytestReport, longrepr=longrepr)

    def test_create_instance(self, cache):
        config = mock.MagicMock(spec=Config)  # pytest config
        config.getvalue.return_value = 2
        config.option = mock.MagicMock(step=None)
        config.cache = cache

        sherlock = Sherlock(config)
        assert sherlock.config == config
        assert sherlock.verbose is True
        assert sherlock.collection is None
        assert sherlock.session is None
        assert sherlock.reporter is None
        assert sherlock.target_test_method is None
        assert sherlock.failed_report is None

    def test_instance_after_pytest_sessionstart(self, config, session, reporter):
        sherlock = Sherlock(config)
        next(sherlock.pytest_sessionstart(session))

        assert sherlock.config == config
        assert sherlock.verbose is True
        assert sherlock.collection is None
        assert sherlock.session == session
        assert sherlock.reporter == reporter
        assert sherlock.target_test_method is None
        assert sherlock.failed_report is None

    @pytest.mark.parametrize("line", ("123", 12), ids=["string", "integer"])
    def test_write_step_to_terminal(self, sherlock_with_prepared_collection, line):
        """
        test expected message like:
        ________ Step [123 of 666] ________
        """
        exp_msg = "Step [{} of 666]:".format(line)
        sherlock_with_prepared_collection.write_step(line, 666)
        sherlock_with_prepared_collection.reporter.write_sep.assert_called_once_with(
            "_", exp_msg, yellow=True, bold=True
        )

    def test_terminal_reset_progress(self, sherlock_with_prepared_collection):
        items = list(range(5))
        sherlock_with_prepared_collection.session.testscollected = 999
        setattr(
            sherlock_with_prepared_collection.reporter,
            "_progress_nodeids_reported",
            {1, 2},
        )

        sherlock_with_prepared_collection.reset_progress(items)
        assert sherlock_with_prepared_collection.session.testscollected == len(items)
        assert (
            sherlock_with_prepared_collection.reporter._progress_nodeids_reported
            == set()
        )

    def test_log(self, target_item):
        with log(target_item) as logger:
            target_item.ihook.pytest_runtest_logstart.assert_called_once_with(
                nodeid=target_item.nodeid, location=target_item.location
            )
            assert logger()
        target_item.ihook.pytest_runtest_logreport.assert_called_once()
        target_item.ihook.pytest_runtest_logfinish.assert_called_once_with(
            nodeid=target_item.nodeid, location=target_item.location
        )

    @pytest.mark.parametrize("by", ("name", "nodeid"))
    def test_pytest_collection_modifyitems_with_option(
        self, sherlock, items, target_item, by
    ):
        config = mock.MagicMock()
        config.getoption.return_value = True
        config.option.flaky_test = getattr(target_item, by)
        assert sherlock.collection is None
        next(
            sherlock.pytest_collection_modifyitems(
                session=mock.MagicMock(), config=config, items=items
            )
        )
        assert items == [target_item]
        assert sherlock.collection is not None
        config.getoption.assert_called_once()

    @pytest.mark.parametrize("by", ("name", "nodeid"))
    def test_pytest_collection_modifyitems_without_option(
        self, sherlock, items, target_item, by
    ):
        config = mock.MagicMock()
        config.getoption.return_value = False
        config.option.flaky_test = getattr(target_item, by)
        will_be_modified = list(items)
        assert sherlock.collection is None
        next(
            sherlock.pytest_collection_modifyitems(
                session=mock.MagicMock(), config=config, items=will_be_modified
            )
        )
        assert will_be_modified == items
        assert sherlock.collection is None
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

    @pytest.mark.parametrize(
        "report_type", ("mock_report_str", "mock_report_class", "mock_report_crash")
    )
    def test_patch_report_with_different_longrepr_type(
        self, request, sherlock_with_failures, mock_coupled, report_type
    ):
        report = request.getfixturevalue(report_type)
        assert sherlock_with_failures.patch_report(
            failed_report=report, coupled=mock_coupled
        )
        exp_report_message = (
            "\n"
            "Found coupled tests:\n"
            "tests/test_test1.py::test_test1\n"
            "tests/test_test2.py::test_test2\n"
            "\n"
            "How to reproduce:\n"
            "pytest -l -vv tests/test_test1.py::test_test1 tests/test_test2.py::test_test2\n"
            "\n"
            "\n"
            "AssertError: 1 != 2"
        )
        assert report.longrepr == exp_report_message, "Report message wasn't changed"
        assert sherlock_with_failures.reporter.stats["failed"] == [report]

    def test_patch_report_with_xml(
        self, sherlock_with_failures, mock_coupled, mock_report_str
    ):
        node_reporters = [
            mock.MagicMock(spec=_NodeReporter),
            mock.MagicMock(spec=_NodeReporter),
            mock.MagicMock(spec=_NodeReporter),
        ]
        mock_xml = mock.MagicMock(
            node_reporters_ordered=node_reporters, stats={"failure": 4}
        )
        sherlock_with_failures.config._xml = mock_xml
        assert sherlock_with_failures.patch_report(
            failed_report=mock_report_str, coupled=mock_coupled
        )
        exp_report_message = (
            "\n"
            "Found coupled tests:\n"
            "tests/test_test1.py::test_test1\n"
            "tests/test_test2.py::test_test2\n"
            "\n"
            "How to reproduce:\n"
            "pytest -l -vv tests/test_test1.py::test_test1 tests/test_test2.py::test_test2\n"
            "\n"
            "\n"
            "AssertError: 1 != 2"
        )
        assert mock_report_str.longrepr == exp_report_message
        assert sherlock_with_failures.reporter.stats["failed"] == [mock_report_str]
        assert len(mock_xml.node_reporters_ordered) == 1
        assert mock_xml.stats["failure"] == 1
