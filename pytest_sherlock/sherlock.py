from __future__ import absolute_import

import contextlib

import pytest
import six
from _pytest.junitxml import _NodeReporter
from _pytest.runner import TestReport, runtestprotocol

from pytest_sherlock.binary_tree_search import length, make_tee


class SherlockError(Exception):
    pass


class NotFoundError(SherlockError):
    @classmethod
    def make(cls, test_name, target_tests=None):
        msg = (
            "Test not found: {}. "
            "Please validate your test name (ex: 'tests/unit/test_one.py::test_first')"
        ).format(test_name)
        if target_tests:
            msg += "\nFound similar test names: {}".format(target_tests)
        return cls(msg)


def _remove_cached_results_from_failed_fixtures(item):
    """
    Note: remove all cached_result attribute from every fixture
    """
    cached_result = "cached_result"
    fixture_info = getattr(item, "_fixtureinfo", None)
    for fixture_def_str in getattr(fixture_info, "name2fixturedefs", {}):
        fixture_defs = fixture_info.name2fixturedefs[fixture_def_str]
        for fixture_def in fixture_defs:
            setattr(fixture_def, cached_result, None)  # cleanup cached fixtures
    return True


def _remove_failed_setup_state_from_session(item):
    """
    Note: remove all _prepare_exc attribute from every col in stack of _setupstate and
    cleaning the stack itself
    """
    prepare_exc = "_prepare_exc"
    setup_state = getattr(item.session, "_setupstate")
    for col in setup_state.stack:
        if hasattr(col, prepare_exc):
            delattr(col, prepare_exc)
    setup_state.stack = list()
    return True


def refresh_state(item):
    # TODO need investigate
    _remove_cached_results_from_failed_fixtures(item)
    _remove_failed_setup_state_from_session(item)
    return True


def write_coupled_report(coupled_tests):
    """
    :param list[_pytest.python.Function] coupled_tests: list of coupled tests
    """
    # TODO can I get info about modified common fixtures?
    coupled_test_names = [t.nodeid.replace("::()::", "::") for t in coupled_tests]
    common_fixtures = set.intersection(*[set(t.fixturenames) for t in coupled_tests])
    msg = "Found coupled tests:\n{}\n\n".format("\n".join(coupled_test_names))
    if common_fixtures:
        msg += "Common fixtures:\n{}\n\n".format("\n".join(common_fixtures))
    msg += "How to reproduce:\npytest -l -vv {}\n".format(" ".join(coupled_test_names))
    return msg


class Bucket(object):

    report_valid_types = (TestReport, type(None))

    def __init__(self, items):
        self.items = items
        self._failed_report = None
        self.__current = 0

    def __len__(self):
        return len(self.items)

    def __iter__(self):
        return self

    def __getitem__(self, item):
        return self.items[item]

    def __repr__(self):
        return str(self.items)

    def __str__(self):
        return "<Bucket items={}>".format(len(self.items))

    def __next__(self):
        if self.__current < len(self.items):
            item = self.items[self.__current]
            self.__current += 1
            return item

        self.__current = 0
        raise StopIteration

    next = __next__

    @property
    def failed_report(self):
        return self._failed_report

    @failed_report.setter
    def failed_report(self, value):
        if not isinstance(value, self.report_valid_types):
            raise SherlockError(
                "Not valid type of report {}, should be one of {}".format(
                    type(value), self.report_valid_types
                )
            )
        self._failed_report = value


class Collection(object):
    def __init__(self, items, test_func=None):
        self.items = items
        self.test_func = test_func
        self.last = None
        self.bts = make_tee((0, len(items)))
        self.current_root = self.bts

    def __len__(self):
        return length(self.bts)

    def __iter__(self):
        return self

    def __next__(self):
        if self.last is not None:
            has_report = bool(self.last.failed_report)
            self.update_root_by_status(status=has_report)

        self.last = self._get_current_tests()
        if self.last is not None:
            return self.last

        self.refresh_state()
        raise StopIteration

    next = __next__

    @staticmethod
    def find_target_test(items, test_name):

        for idx, test_func in enumerate(items):
            if test_name in (test_func.name, test_func.nodeid):
                return idx, test_func

        if ".py::" in test_name:
            target_test_name = test_name.split("::")[-1]
        else:
            target_test_name = test_name.split("[")[0]
        target_test_names = [i.nodeid for i in items if target_test_name in i.name]
        raise NotFoundError.make(test_name, target_tests=target_test_names)

    @classmethod
    def make(cls, items, test_name):
        idx, target_test_method = cls.find_target_test(items, test_name)
        target_items = sorted(
            items[:idx],
            key=lambda item: (
                len(set(item.fixturenames) & set(target_test_method.fixturenames)),
                item.parent.nodeid,  # TODO can we do AST or Name or Content analysis?
            ),
            reverse=True,
        )
        collection = cls(items=target_items, test_func=target_test_method)
        return collection

    def update_root_by_status(self, status):
        if status is False:
            self.current_root = self.current_root.right
            return

        if self.last and len(self.last) == 1:
            # The last bucked has just one test and target tests failed after it
            # Found coupled tests
            self.current_root = None
            return

        self.current_root = self.current_root.left

    def _get_current_tests(self):
        if self.current_root is None:
            return None

        if self.current_root.left is not None:
            return self.make_bucket(self.current_root.left)
        if self.current_root.right is not None:
            return self.make_bucket(self.current_root.right)

        # the last tests (should be just one test) which should be checked
        return self.make_bucket(self.current_root)

    def make_bucket(self, node):
        start, end = node.items
        items = self.items[start:end]
        return Bucket(items)

    def refresh_state(self):
        self.current_root = self.bts
        self.last = None


@contextlib.contextmanager
def log(item):
    item.ihook.pytest_runtest_logstart(nodeid=item.nodeid, location=item.location)
    yield item.ihook.pytest_runtest_logreport
    item.ihook.pytest_runtest_logfinish(nodeid=item.nodeid, location=item.location)


class Sherlock(object):
    def __init__(self, config):
        self.config = config
        self.collection = None
        self._tw = None
        self._reporter = None
        self._coupled = None

    @property
    def reporter(self):
        if self._reporter is None:
            self._reporter = self.config.pluginmanager.get_plugin("terminalreporter")
        return self._reporter

    @property
    def terminal(self):
        if self._tw is None:
            self._tw = self.reporter.writer
        return self._tw

    def write_step(self, step, maximum):
        """
        Write summary of steps
        For Example:
        _______________________________ Step [1 of 4]: _______________________________
        ...

        :param str|int step:
        :param str|int maximum:
        """
        self.reporter.ensure_newline()
        message = "Step [{} of {}]:".format(step, maximum)
        self.terminal.sep("_", message, yellow=True, bold=True)

    def reset_progress(self, collection):
        """
        Patch progress for each step
        100% should be all tests from collection + target test
        For example:
        _______________________________ Step [1 of 4]: _______________________________
        tests/exmaple/test_c_delete.py::test_delete_random_param PASSED         [ 20%]
        tests/exmaple/test_b_modify.py::test_modify_random_param PASSED         [ 40%]
        tests/exmaple/test_c_delete.py::test_deleted_passed PASSED              [ 60%]
        tests/exmaple/test_c_delete.py::test_do_not_delete PASSED               [ 80%]
        tests/exmaple/test_all_read.py::test_read_params FAILED                 [100%]
        _______________________________ Step [2 of 4]: _______________________________
        tests/exmaple/test_c_delete.py::test_delete_random_param PASSED         [ 33%]
        tests/exmaple/test_b_modify.py::test_modify_random_param PASSED         [ 66%]
        tests/exmaple/test_all_read.py::test_read_params FAILED                 [100%]
        ...

        :param Bucket[_pytest.python.Function] collection: bucket of tests
        """
        setattr(self.reporter, "_progress_nodeids_reported", set())
        setattr(
            self.reporter._session, "testscollected", len(collection) + 1
        )  # current item

    @pytest.hookimpl(hookwrapper=True, trylast=True)
    def pytest_collection_modifyitems(self, session, config, items):
        r"""
        called after collection has been performed, may filter or re-order
        the items in-place.

        Items:
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
        # First step
                            root
                           /    \
                     [0, 1]      [2, 3]
        # Second step
                    /   \        /    \
                 [0]    [1]    [2]    [3]

        :param _pytest.main.Session session:
        :param _pytest.config.Config config: pytest config object
        :param List[_pytest.python.Function] items: list of item objects
        """
        if config.getoption("--flaky-test"):
            self.collection = Collection.make(items, config.option.flaky_test.strip())
            items[:] = [self.collection.test_func]
        yield

    @pytest.hookimpl(trylast=True)
    def pytest_report_collectionfinish(self, config, startdir, items):
        """
        Write summary which minimum steps need to find guilty tests
        :param _pytest.config.Config config: pytest config object
        :param py._path.local.LocalPath startdir:
        :param List[_pytest.python.Function] items: contain just target test
        """
        max_steps = length(self.collection.bts, max)
        min_steps = length(self.collection.bts, min)
        return "Try to find coupled tests in [{}-{}] steps".format(min_steps, max_steps)

    def patch_report(self, failed_report, coupled):
        """
        Patch reports console output and Junit result xml
        to avoid multi errors in report
        :param _pytest.runner.TestReport failed_report:
        :param list[_pytest.python.Function] coupled: list of coupled tests, last should be target
        """
        target_item = coupled[-1]
        if hasattr(failed_report.longrepr, "reprcrash"):
            message = failed_report.longrepr.reprcrash.message
        elif isinstance(failed_report.longrepr, six.string_types):
            message = failed_report.longrepr
        else:
            message = str(failed_report.longrepr)
        failed_report.longrepr = "\n{}\n\n{}".format(
            write_coupled_report(coupled), message
        )
        self.reporter.stats["failed"] = [failed_report]
        xml = getattr(self.config, "_xml", None)
        if xml:
            node_reporter = _NodeReporter(target_item.nodeid, xml)
            node_reporter.append_failure(failed_report)
            node_reporter.finalize()
            xml.node_reporters_ordered[:] = [node_reporter]
            xml.stats["failure"] = 1
        return True

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_protocol(self, item, nextitem=None):
        """
        Method will run just once,
        because session.items have just a single target test and nextitem always should be None
        :param _pytest.python.Function item: target test
        :param _pytest.python.Function | None nextitem: by default None
        """
        max_length = len(self.collection)
        for step, bucket in enumerate(self.collection, start=1):
            self.write_step(step, max_length)
            self.call(target_item=item, items=bucket)
            if len(bucket) == 1 and bucket.failed_report:
                self.patch_report(bucket.failed_report, coupled=[bucket[0], item])
                break

    def pytest_runtestloop(self, session):
        """
        Just fork origin pytest method and reuse own `pytest_runtest_protocol` inside
        session.items always a list with the single target test
        :param _pytest.main.Session session:
        """
        if (
            session.testsfailed
            and not session.config.option.continue_on_collection_errors
        ):
            raise session.Interrupted(
                "%d errors during collection" % session.testsfailed
            )

        if session.config.option.collectonly:
            return True

        for i, item in enumerate(session.items):
            nextitem = session.items[i + 1] if i + 1 < len(session.items) else None
            is_success = self.pytest_runtest_protocol(item=item, nextitem=nextitem)
            if not is_success:
                raise session.Failed("Found coupled tests")
            if session.shouldstop:
                raise session.Interrupted(session.shouldstop)
        return True

    def call_items(self, target_item, items):
        """
        Call all items before target test
        and if one of result (setup, call, teardown) failed mark as flaky
        :param _pytest.python.Function target_item: test which should fail
        :param Bucket[_pytest.python.Function] items: bucket of tests
        """
        for next_idx, test_func in enumerate(items, 1):
            with log(test_func) as logger:
                next_item = items[next_idx] if next_idx < len(items) else target_item
                reports = runtestprotocol(item=test_func, nextitem=next_item, log=False)
                for report in reports:  # 3 reports: setup, call, teardown
                    if report.failed is True:
                        report.outcome = "flaky"
                    logger(report=report)

    def call_target(self, target_item):
        """
        Call target test after some tests which were run before
        and if one of result (setup, call, teardown) failed mark as coupled
        :param _pytest.python.Function target_item: current flaky test
        """
        failed_report = None
        with log(target_item) as logger:
            reports = runtestprotocol(target_item, log=False)
            for report in reports:  # 3 reports: setup, call, teardown
                if report.failed is True:
                    refresh_state(item=target_item)
                    logger(report=report)
                    failed_report = report
                    continue
                logger(report=report)
        return failed_report  # setup, call, teardown must be succeeded

    def call(self, target_item, items):
        """
        Call all tests (which probably guilty in failure) before target test
        :param _pytest.python.Function target_item: current flaky test
        :param Bucket[_pytest.python.Function] items: bucket of tests
        """
        self.reset_progress(items)
        self.call_items(target_item=target_item, items=items)
        items.failed_report = self.call_target(target_item=target_item)
