import mock
import pytest
from _pytest.config import Config
from _pytest.junitxml import _NodeReporter
from _pytest.python import Function
from _pytest.runner import TestReport as PytestReport

from pytest_sherlock.binary_tree_search import Root
from pytest_sherlock.sherlock import (
    Bucket,
    Collection,
    Sherlock,
    SherlockError,
    SherlockNotFoundError,
    _remove_cached_results_from_failed_fixtures,
    _remove_failed_setup_state_from_session,
    refresh_state,
    write_coupled_report,
)

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


@pytest.fixture(scope="function")
def collection(items):
    return Collection(items)


@pytest.fixture(scope="function")
def prepared_collection(items, target_item):
    c = Collection(items)
    c.prepare(target_item.nodeid)
    return c


@pytest.fixture(scope="function")
def sherlock_with_prepared_collection(sherlock, prepared_collection):
    sherlock.collection = prepared_collection
    return sherlock


class TestCleanupItem(object):
    @pytest.fixture()
    def fixtures(self):
        mock_fixtures = (
            mock.MagicMock(cached_result="1", argname="fixture1"),
            mock.MagicMock(cached_result=2, argname="fixture2"),
        )
        return {f.argname: (f,) for f in mock_fixtures}

    @pytest.fixture()
    def stack(self):
        return [mock.MagicMock(_prepare_exc=1)]

    @pytest.fixture()
    def called_item(self, target_item, fixtures, stack):
        # added cached results of fixtures
        target_item._fixtureinfo = mock.MagicMock(name2fixturedefs=fixtures)
        # added cache to session
        target_item.session = mock.MagicMock(_setupstate=mock.MagicMock(stack=stack))
        return target_item

    @staticmethod
    def check_cleanup_fixtures(fixtures):
        assert fixtures
        for fixture_name, funcs in fixtures.items():
            for func in funcs:
                assert func.cached_result is None, "cached_result wasn't cleanup"

    @staticmethod
    def check_cleanup_stack(stack):
        assert stack
        for s in stack:
            assert not hasattr(s, "_prepare_exc"), "_prepare_exc wasn't delete"

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

    def test_remove_cached_results_from_failed_fixtures(self, called_item, fixtures):
        assert _remove_cached_results_from_failed_fixtures(called_item)
        self.check_cleanup_fixtures(fixtures)

    def test_remove_failed_setup_state_from_session(self, called_item, stack):
        assert _remove_failed_setup_state_from_session(called_item)
        self.check_cleanup_stack(stack)


class TestBucket(object):
    @pytest.fixture()
    def bucket(self, items):
        return Bucket(items)

    def test_crete_instance(self, bucket, items):
        assert bucket.items == items
        assert bucket.failed_report is None
        assert bucket._failed_report is None

    def test_valid_failed_report_types(self, bucket):
        assert bucket.report_valid_types == (PytestReport, type(None))

    def test_as_string(self, bucket):
        assert str(bucket) == "<Bucket items=6>"

    def test_representation(self, bucket):
        assert repr(bucket) == str(bucket.items)

    def test_length(self, bucket):
        assert len(bucket) == 6

    def test_getitem_by_index(self, bucket):
        assert bucket[4].nodeid == "tests/test_five.py::test_five"

    def test_iteration(self, bucket, items):
        for idx, item in enumerate(bucket):
            assert item == items[idx]

    @pytest.mark.parametrize("report", (None, mock.MagicMock(spec=PytestReport)))
    def test_set_failed_report(self, bucket, report):
        bucket.failed_report = report
        assert bucket.failed_report == report
        assert bucket._failed_report == report

    def test_set_not_valid_failed_report(self, bucket):
        with pytest.raises(SherlockError, match="Not valid type of report"):
            bucket.failed_report = mock.MagicMock()


class TestCollection(object):
    def test_create_instance(self, collection, items):
        assert collection.items == items
        assert collection.test_func is None
        assert isinstance(collection.bts, Root)
        assert collection.bts.root is None
        assert collection.current_root is None
        assert collection.last is None

    def test_prepare_collection(self, prepared_collection):
        assert prepared_collection.last is None
        assert prepared_collection.bts.root is not None
        assert prepared_collection.current_root == prepared_collection.bts.root
        # TODO check insert method

    def test_raw_collection_length(self, collection):
        assert len(collection) == 0

    def test_prepared_collection_length(self, prepared_collection):
        assert len(prepared_collection) == 2

    @pytest.mark.parametrize(
        "report, exp_buckets",
        (
            (
                None,
                [
                    [
                        "tests/test_tree.py::test_tree",
                        "tests/test_one.py::test_one",
                    ],  # Step [1 of 3]
                    ["tests/test_two.py::test_two"],  # Step [2 of 3]
                    [
                        "tests/test_four.py::test_four"
                    ],  # Step [3 of 3], not found any coupled
                ],
            ),
            (
                mock.MagicMock(spec=PytestReport),
                [
                    [
                        "tests/test_tree.py::test_tree",
                        "tests/test_one.py::test_one",
                    ],  # Step [1 of 3]
                    [
                        "tests/test_tree.py::test_tree"
                    ],  # Step [2 of 3], the last because found coupled
                ],
            ),
        ),
    )
    def test_iteration_by_collection(self, prepared_collection, exp_buckets, report):
        for idx, bucket in enumerate(prepared_collection):
            assert isinstance(bucket, Bucket)
            test_ids = [i.nodeid for i in bucket.items]
            assert test_ids == exp_buckets[idx]
            assert prepared_collection.last == bucket
            bucket.failed_report = report  # should be None or TestReport

        # after completed, refresh state
        assert prepared_collection.last is None
        assert prepared_collection.current_root == prepared_collection.bts.root

    @pytest.mark.parametrize(
        "by", ("test_five", "tests/test_five.py::test_five"), ids=["name", "node_id"]
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
        fake_test_name = "tests/which/not_exist.py::test_fake"
        with pytest.raises(SherlockNotFoundError, match=fake_test_name):
            collection._needed_tests(fake_test_name)

    @pytest.mark.parametrize("status, direction", ((True, "left"), (False, "right")))
    def test_update_root_by_status(self, prepared_collection, status, direction):
        origin_root = prepared_collection.current_root
        prepared_collection.update_root_by_status(status)
        assert prepared_collection.current_root != origin_root
        assert prepared_collection.current_root == getattr(origin_root, direction)

    def test_get_current_tests_by_left_direction(self, prepared_collection):
        bucket = prepared_collection._get_current_tests()
        assert isinstance(bucket, Bucket)
        assert bucket.items == prepared_collection.current_root.left.items

    def test_get_current_tests_by_right_direction(self, prepared_collection):
        prepared_collection.current_root.left = None
        bucket = prepared_collection._get_current_tests()
        assert isinstance(bucket, Bucket)
        assert bucket.items == prepared_collection.current_root.right.items

    def test_get_last_current_tests(self, prepared_collection):
        prepared_collection.current_root.left = None
        prepared_collection.current_root.right = None
        bucket = prepared_collection._get_current_tests()
        assert bucket.items == prepared_collection.current_root.items

    def test_not_found_current_tests(self, prepared_collection):
        prepared_collection.current_root = None
        assert prepared_collection._get_current_tests() is None

    def test_refresh_state(self, prepared_collection):
        first_bucket = next(prepared_collection)
        assert prepared_collection.last == first_bucket
        assert prepared_collection.current_root == prepared_collection.bts.root
        second_bucket = next(prepared_collection)
        assert prepared_collection.last == second_bucket
        assert prepared_collection.current_root != prepared_collection.bts.root
        prepared_collection.refresh_state()
        assert prepared_collection.last is None
        assert prepared_collection.current_root == prepared_collection.bts.root


class TestSherlock(object):
    @pytest.fixture()
    def config(self):
        plugin_manager = mock.MagicMock()
        return mock.MagicMock(spec=Config, pluginmanager=plugin_manager)

    @pytest.fixture()
    def sherlock(self, config):
        return Sherlock(config=config)

    @pytest.fixture()
    def sherlock_with_failures(self, sherlock):
        sherlock._reporter = mock.MagicMock(stats={"failed": [1, 2, 3, 4]})
        return sherlock

    @pytest.fixture()
    def mock_coupled(self):
        mock_coupled = [
            make_fake_test_item("test1"),
            make_fake_test_item("test2"),
        ]
        return mock_coupled

    @pytest.fixture()
    def mock_report_str(self):
        return mock.MagicMock(spec=PytestReport, longrepr="AssertError: 1 != 2")

    @pytest.fixture()
    def mock_report_class(self):
        class LongReprStub(object):
            def __init__(self, msg):
                self.msg = msg

            def __str__(self):
                return self.msg

        return mock.MagicMock(
            spec=PytestReport, longrepr=LongReprStub("AssertError: 1 != 2")
        )

    @pytest.fixture()
    def mock_report_crash(self):
        longrepr = mock.MagicMock(
            reprcrash=mock.MagicMock(message="AssertError: 1 != 2")
        )
        return mock.MagicMock(spec=PytestReport, longrepr=longrepr)

    def test_create_instance(self):
        config = mock.MagicMock(spec=Config)  # pytest config
        sherlock = Sherlock(config)
        assert sherlock.config == config
        assert sherlock.collection is None
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
        sherlock.terminal.sep.assert_called_once_with(
            "_", exp_msg, yellow=True, bold=True
        )

    def test_terminal_reset_progress(self, sherlock, prepared_collection):
        mock_session = mock.MagicMock(testscollected=6)
        sherlock._reporter = mock.MagicMock(
            _progress_nodeids_reported={1, 2}, _session=mock_session
        )
        sherlock.reset_progress(prepared_collection)
        assert sherlock.reporter._session.testscollected == len(prepared_collection) + 1
        assert sherlock.reporter._progress_nodeids_reported == set()

    def test_log(self, sherlock, target_item):
        with sherlock.log(target_item) as logger:
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
        assert isinstance(sherlock.collection, Collection)
        assert sherlock.collection.items == [target_item]
        config.getoption.assert_called_once()

    @pytest.mark.parametrize("by", ("name", "nodeid"))
    def test_pytest_collection_modifyitems_without_option(
        self, sherlock, items, target_item, by
    ):
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
