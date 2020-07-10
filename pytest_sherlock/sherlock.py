import contextlib

import pytest
import six
from _pytest.runner import runtestprotocol
from _pytest.junitxml import _NodeReporter

from pytest_sherlock.binary_tree_search import Root as BTSRoot


class SherlockNotFoundError(Exception):
    def __init__(self, test_name):
        self.test_name = test_name
        super(SherlockNotFoundError, self).__init__()

    def message(self):
        return (
            "Test not found: {}. "
            "Please validate your test name (ex: 'tests/unit/test_one.py::test_first')"
        ).format(self.test_name)

    def __str__(self):
        return self.message()


def _remove_cached_results_from_failed_fixtures(item):
    """
    Note: remove all cached_result attribute from every fixture
    """
    cached_result = 'cached_result'
    fixture_info = getattr(item, '_fixtureinfo', None)
    for fixture_def_str in getattr(fixture_info, 'name2fixturedefs', ()):
        fixture_defs = fixture_info.name2fixturedefs[fixture_def_str]
        for fixture_def in fixture_defs:
            setattr(fixture_def, cached_result, None)  # cleanup cache
    return True


def _remove_failed_setup_state_from_session(item):
    """
    Note: remove all _prepare_exc attribute from every col in stack of _setupstate and
    cleaning the stack itself
    """
    prepare_exc = "_prepare_exc"
    setup_state = getattr(item.session, '_setupstate')
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
    def __init__(self, items):
        self.items = items
        self.__current = 0
        self.failed_report = None

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


class Collection(object):

    def __init__(self, items):
        self.items = items
        self.test_func = None
        self._bts = BTSRoot()
        self.__current_root = None
        self.__last = None

    def _needed_tests(self, test_name):
        tests = []
        for test_func in self.items:
            if test_func.name == test_name or test_func.nodeid == test_name:
                self.test_func = test_func
                break
            tests.append(test_func)

        if self.test_func is None:
            raise SherlockNotFoundError(test_name)

        tests[:] = sorted(
            tests,
            key=lambda item: (
                len(set(item.fixturenames) & set(self.test_func.fixturenames)),
                item.parent.nodeid  # TODO add AST analise
            ),
            reverse=True,
        )
        return tests

    def __len__(self):
        return len(self._bts)

    def __iter__(self):
        return self

    def __next__(self):
        if self.__last is not None:
            self._set_current_status(not bool(self.__last.failed_report))
            self.__last = self._get_current_tests()
        else:
            self.__last = self._get_current_tests()

        if self.__last is None:
            self.refresh_state()
            raise StopIteration
        return self.__last

    next = __next__

    def prepare(self, test_name):
        items = self._needed_tests(test_name)
        self._bts.insert(items)
        self.refresh_state()

    def _set_current_status(self, status):
        if status is True:
            self.__current_root = self.__current_root.right
        else:
            self.__current_root = self.__current_root.left

    def _get_current_tests(self):
        if self.__current_root is None:
            return
        if self.__current_root.left is not None:
            return Bucket(self.__current_root.left.items)
        return Bucket(self.__current_root.items)

    def refresh_state(self):
        self.__current_root = self._bts.root
        self.__last = None


class Sherlock(object):
    def __init__(self, config):
        self.config = config
        # TODO add tests
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
        self.terminal.sep('_', message, yellow=True, bold=True)

    @contextlib.contextmanager
    def log(self, item):
        item.ihook.pytest_runtest_logstart(nodeid=item.nodeid, location=item.location)
        yield item.ihook.pytest_runtest_logreport
        item.ihook.pytest_runtest_logfinish(nodeid=item.nodeid, location=item.location)

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
        self.reporter._progress_nodeids_reported = set()
        self.reporter._session.testscollected = len(collection) + 1  # current item

    @pytest.hookimpl(hookwrapper=True)
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
            self.collection = Collection(items)
            self.collection.prepare(config.option.flaky_test)
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
        length = len(self.collection)
        return "Try to find coupled tests in [{}-{}] steps".format(length, length + 1)

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
        failed_report.longrepr = "\n{}\n\n{}".format(write_coupled_report(coupled), message)
        self.reporter.stats["failed"] = [failed_report]
        xml = getattr(self.config, "_xml", None)
        if xml:
            node_reporter = _NodeReporter(target_item.nodeid, xml)
            node_reporter.append_failure(failed_report)
            node_reporter.finalize()
            xml.node_reporters_ordered[:] = [node_reporter]
            xml.stats["failure"] = 1

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_protocol(self, item, nextitem=None):
        """
        Method will run just once,
        because session.items have just a single target test and nextitem always should be None
        :param _pytest.python.Function item: target test
        :param _pytest.python.Function | None nextitem: by default None
        """
        max_length = len(self.collection) + 1  # target test
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
        if session.testsfailed and not session.config.option.continue_on_collection_errors:
            raise session.Interrupted("%d errors during collection" % session.testsfailed)

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
            with self.log(test_func) as logger:
                next_item = items[next_idx] if next_idx < len(items) else target_item
                reports = runtestprotocol(item=test_func, nextitem=next_item, log=False)
                for report in reports:  # 3 reports: setup, call, teardown
                    if report.failed is True:
                        report.outcome = 'flaky'
                    logger(report=report)

    def call_target(self, target_item):
        """
        Call target test after some tests which were run before
        and if one of result (setup, call, teardown) failed mark as coupled
        :param _pytest.python.Function target_item: current flaky test
        """
        failed_report = None
        with self.log(target_item) as logger:
            reports = runtestprotocol(target_item, log=False)
            for report in reports:  # 3 reports: setup, call, teardown
                if report.failed is True:
                    refresh_state(item=target_item)
                    logger(report=report)
                    failed_report = report
                    continue
                logger(report=report)
        return failed_report  # setup, call, teardown must success

    def call(self, target_item, items):
        """
        Call all tests (which probably guilty in failure) before target test
        :param _pytest.python.Function target_item: current flaky test
        :param Bucket[_pytest.python.Function] items: bucket of tests
        """
        self.reset_progress(items)
        self.call_items(target_item=target_item, items=items)
        items.failed_report = self.call_target(target_item=target_item)
