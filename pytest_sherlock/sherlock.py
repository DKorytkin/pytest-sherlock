import contextlib
import time

import pytest
from _pytest.main import (
    EXIT_OK,
    EXIT_TESTSFAILED,
    EXIT_INTERRUPTED,
    EXIT_USAGEERROR,
    EXIT_NOTESTSCOLLECTED,
)
from _pytest.runner import runtestprotocol

from pytest_sherlock.binary_tree_search import Root as BTSRoot


PYTEST_EXIT_CODES = (
    EXIT_OK,
    EXIT_TESTSFAILED,
    EXIT_INTERRUPTED,
    EXIT_USAGEERROR,
    EXIT_NOTESTSCOLLECTED,
)


def build_summary_stats_line(stats):
    keys = [
        "failed", "passed", "skipped", "deselected", "xfailed", "xpassed", "warnings", "error",
        "coupled", "flaky",
    ]

    unknown_key_seen = False
    for key in stats.keys():
        if key not in keys:
            if key:  # setup/teardown reports have an empty key, ignore them
                keys.append(key)
                unknown_key_seen = True
    parts = []
    for key in keys:
        val = stats.get(key, None)
        if val:
            parts.append("%d %s" % (len(val), key))

    if parts:
        line = "found coupled"
    else:
        line = "no tests ran"

    if "coupled" in keys or "failed" in stats or "error" in stats:
        color = 'red'
    elif ("warnings" in stats or "flaky" in keys) or unknown_key_seen:
        color = "yellow"
    elif "passed" in stats:
        color = "green"
    else:
        color = "yellow"

    return line, color


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


class Collection(object):

    def __init__(self, items):
        self.items = items
        self.test_func = None
        self._bts = BTSRoot()
        self.__current_root = None

    def needed_tests(self, test_name):
        tests = []
        for test_func in self.items:
            if test_func.name == test_name or test_func.nodeid == test_name:
                self.test_func = test_func
                break
            tests.append(test_func)

        if self.test_func is None:
            # TODO make own error
            raise RuntimeError("Validate your test name (ex: 'tests/unit/test_one.py::test_first')")

        tests[:] = sorted(
            tests,
            key=lambda item: (
                len(set(item.fixturenames) & set(self.test_func.fixturenames)),
                item.parent.nodeid  # TODO add AST analise
            ),
            reverse=True,
        )
        return tests

    def make(self, test_name):
        items = self.needed_tests(test_name)
        self._bts.insert(items)
        self.__current_root = self._bts.root

    def set_current_status(self, status):
        if status is True:
            self.__current_root = self.__current_root.right
        else:
            self.__current_root = self.__current_root.left

    def get_current_tests(self):
        if self.__current_root is None:
            return
        if self.__current_root.left is not None:
            return self.__current_root.left.items
        return self.__current_root.items


class Sherlock(object):
    def __init__(self, config):
        self.config = config
        self.collection = None
        self.bts_root = BTSRoot()
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

    def write_step(self, step):
        self.reporter.ensure_newline()
        # self.terminal.sep(sep, title, **markup)
        # TODO need add process like: Step: [1 of 12]
        self.terminal.write("Step #{}:".format(step), yellow=True, bold=True)

    @contextlib.contextmanager
    def log(self, item):
        self.reporter.pytest_runtest_logstart(nodeid=item.nodeid, location=item.location)
        yield self.reporter.pytest_runtest_logreport
        self.reporter.pytest_runtest_logfinish(nodeid=item.nodeid)

    @staticmethod
    def refresh_state(item):
        # TODO need investigate
        _remove_cached_results_from_failed_fixtures(item)
        _remove_failed_setup_state_from_session(item)
        return True

    def reset_progress(self, collection):
        self.reporter._progress_nodeids_reported = set()
        self.reporter._session.testscollected = len(collection) + 1  # current item

    def summary_coupled(self):
        # TODO port class TerminalReporter and modify
        if self.config.option.tbstyle != "no":
            reports = self.reporter.getreports("coupled")
            if not reports:
                return
            last_report = reports[-1]
            if self._coupled:
                # TODO can I get info about modified common fixtures?
                coupled_test_names = [t.nodeid for t in self._coupled]
                common_fixtures = set.intersection(*[set(t.fixturenames) for t in self._coupled])
                msg = (
                    "found coupled tests:\n"
                    "{coupled}\n\n"
                    "Common fixtures:\n"
                    "{common_fixtures}\n\n"
                    "How to reproduce:\npytest -l -vv {tests}\n"
                ).format(
                    coupled="\n".join(coupled_test_names),
                    tests=" ".join(coupled_test_names),
                    common_fixtures="\n".join(common_fixtures) if common_fixtures else ""
                )
                self.reporter.write(msg, red=True)

            msg = self.reporter._getfailureheadline(last_report)
            self.reporter.write_sep("_", msg, red=True, bold=True)
            self.reporter._outrep_summary(last_report)

    def summary_stats(self):
        session_duration = time.time() - self.reporter._sessionstarttime
        line, color = build_summary_stats_line(self.reporter.stats)
        msg = "%s in %.2f seconds" % (line, session_duration)
        markup = {color: True, 'bold': True}

        if self.reporter.verbosity >= 0:
            self.reporter.write_sep("=", msg, **markup)
        if self.reporter.verbosity == -1:
            self.reporter.write_line(msg, **markup)

    @pytest.hookimpl(hookwrapper=True)
    def pytest_collection_modifyitems(self, session, config, items):
        """
        called after collection has been performed, may filter or re-order
        the items in-place.

        :param _pytest.config.Config config: pytest config object
        :param List[_pytest.nodes.Item] items: list of item objects
        """
        if config.getoption("--flaky-test"):
            self.collection = Collection(items)
            self.collection.make(config.option.flaky_test)
            items[:] = [self.collection.test_func]
        yield

    @pytest.hookimpl(trylast=True)
    def pytest_report_collectionfinish(self, config, startdir, items):
        # TODO add bts length, from 12 to 13 steps
        return "Try to find coupled tests"

    @pytest.hookimpl(hookwrapper=True)
    def pytest_terminal_summary(self, terminalreporter):
        if self._coupled:
            self.summary_stats()
            self.summary_coupled()
        yield
        terminalreporter.summary_failures()
        terminalreporter.summary_errors()
        terminalreporter.summary_warnings()
        terminalreporter.summary_passes()

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_protocol(self, item, nextitem):
        steps = 1
        is_target_test_success = True
        current_tests = self.collection.get_current_tests()
        while current_tests:
            self.write_step(steps)
            self.reset_progress(current_tests)
            self.call_items(target_item=item, items=current_tests)
            is_target_test_success = self.call_target(target_item=item)
            if len(current_tests) == 1 and not is_target_test_success:
                self._coupled = [current_tests[0], item]
                break
            steps += 1
            self.collection.set_current_status(is_target_test_success)
            current_tests = self.collection.get_current_tests()
        return is_target_test_success

    def pytest_runtestloop(self, session):
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
        for next_idx, test_func in enumerate(items, 1):
            with self.log(test_func) as logger:
                next_item = items[next_idx] if next_idx < len(items) else target_item
                reports = runtestprotocol(item=test_func, nextitem=next_item, log=False)
                for report in reports:  # 3 reports: setup, call, teardown
                    if report.failed is True:
                        report.outcome = 'flaky'
                    logger(report=report)

    def call_target(self, target_item):
        success = []
        with self.log(target_item) as logger:
            reports = runtestprotocol(target_item, log=False)
            for report in reports:  # 3 reports: setup, call, teardown
                if report.failed is True:
                    report.outcome = 'coupled'
                    self.refresh_state(item=target_item)
                    logger(report=report)
                    success.append(False)
                    continue
                logger(report=report)
                success.append(True)
        return all(success)  # setup, call, teardown must success
