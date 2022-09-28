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


def make_collection(*items, binary_tree=None):
    root = binary_tree or make_tee((0, len(items)))
    current_node = root
    while current_node is not None:
        if current_node.left is not None:
            range_of_tests = slice(*current_node.left.items)
        elif current_node.right is not None:
            range_of_tests = slice(*current_node.right.items)
        else:
            range_of_tests = slice(*current_node.items)

        bucket = items[range_of_tests]
        has_report = yield bucket

        if has_report and len(bucket) == 1:  # found coupled tests
            return

        if has_report:
            current_node = current_node.left  # dive dipper if report was made
        else:
            current_node = current_node.right


@contextlib.contextmanager
def log(item):
    item.ihook.pytest_runtest_logstart(nodeid=item.nodeid, location=item.location)
    yield item.ihook.pytest_runtest_logreport
    item.ihook.pytest_runtest_logfinish(nodeid=item.nodeid, location=item.location)


class Sherlock(object):
    def __init__(self, config):
        self.config = config
        # initialize via pytest_sessionstart
        self._session = None
        self._tw = None
        self._reporter = None
        self._coupled = None
        # initialize via pytest_collection_modifyitems
        self.collection = None
        self.target_test_method = None
        self._bts = None
        self._min_iterations = 0
        self._max_iterations = 0

    @pytest.hookimpl(hookwrapper=True, trylast=True)
    def pytest_sessionstart(self, session):
        self._session = session
        if self._reporter is None:
            self._reporter = self.config.pluginmanager.get_plugin("terminalreporter")
        yield

    @property
    def reporter(self):
        return self._reporter

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
        self.reporter.writer.sep("_", message, yellow=True, bold=True)

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
        setattr(self._session, "testscollected", len(collection) + 1)  # current item

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
            idx, target_test_method = find_target_test(
                items, config.option.flaky_test.strip()
            )
            target_items = sorted(
                items[:idx],
                key=lambda item: (
                    len(set(item.fixturenames) & set(target_test_method.fixturenames)),
                    item.parent.nodeid,  # TODO can we do AST or Name or Content analysis?
                ),
                reverse=True,
            )
            items[:] = [target_test_method]
            self.target_test_method = target_test_method
            self._bts = make_tee((0, len(target_items)))
            self._min_iterations = length(self._bts, min)
            self._max_iterations = length(self._bts, max)
            self.collection = make_collection(*target_items, binary_tree=self._bts)
        yield

    @pytest.hookimpl(trylast=True)
    def pytest_report_collectionfinish(self, config, startdir, items):
        """
        Write summary which minimum steps need to find guilty tests
        :param _pytest.config.Config config: pytest config object
        :param py._path.local.LocalPath startdir:
        :param List[_pytest.python.Function] items: contain just target test
        """
        max_steps = self._max_iterations
        min_steps = self._min_iterations
        return "Try to find coupled tests in [{}-{}] steps".format(min_steps, max_steps)

    def patch_report(self, failed_report, coupled):
        """
        Patch reports console output and Junit result xml
        to avoid multi errors in report
        :param _pytest.runner.TestReport failed_report:
        :param list[_pytest.python.Function] coupled: list of coupled tests, last should be target
        """
        target_item = coupled[-1]
        # TODO join failed_reports
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
        step = 1
        items = next(self.collection)
        while items:
            self.write_step(step, self._max_iterations)
            self.reset_progress(items)

            # call tests before our "--flaky-test" to make sure they are not coupled
            for next_idx, test_func in enumerate(items, 1):
                with log(test_func) as logger:
                    next_item = items[next_idx] if next_idx < len(items) else item
                    reports = runtestprotocol(
                        item=test_func, nextitem=next_item, log=False
                    )
                    for report in reports:  # 3 reports: setup, call, teardown
                        if report.failed is True:
                            report.outcome = "flaky"
                        logger(report=report)

            # call to target test for checking is it still green
            with log(item) as logger:
                reports = runtestprotocol(item, log=False)
                failed_reports = []
                for report in reports:  # 3 reports: setup, call, teardown
                    if report.failed is True:
                        refresh_state(item=item)
                        logger(report=report)
                        failed_reports.append(report)
                        continue
                    logger(report=report)

            if len(items) == 1 and failed_reports:
                # self.patch_report(failed_reports, coupled=[items[0], item])
                break

            try:
                items = self.collection.send(bool(failed_reports))
            except StopIteration:
                if len(items) != 1:
                    raise  # something going wrong
                break  # didn't find any coupled tests

            step += 1

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
            # TODO move logic here
            is_success = self.pytest_runtest_protocol(item=item, nextitem=nextitem)
            if not is_success:
                raise session.Failed("Found coupled tests")
            if session.shouldstop:
                raise session.Interrupted(session.shouldstop)
        return True
