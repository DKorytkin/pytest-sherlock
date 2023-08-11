from __future__ import absolute_import

import contextlib
from typing import List, Optional

import pytest
import six
from _pytest.config import Config
from _pytest.junitxml import _NodeReporter
from _pytest.main import Session
from _pytest.python import Function
from _pytest.terminal import TerminalReporter

from pytest_sherlock.binary_tree_search import draw_tree, length, make_tee


class SherlockError(Exception):
    pass


class NotFoundError(SherlockError):
    @classmethod
    def make_from(cls, test_name, items):
        msg = (
            f"Test not found: {test_name}. "
            f"Please validate your test name (ex: 'tests/unit/test_one.py::test_first')"
        )

        if ".py::" in test_name:
            target_test_name = test_name.split("::")[-1]
        else:
            target_test_name = test_name.split("[")[0]
        target_test_names = [i.nodeid for i in items if target_test_name in i.name]
        if target_test_names:
            msg += f"\nFound similar test names: {test_name}"
        return cls(msg)


def _remove_cached_results_from_failed_fixtures(item):
    """
    This function force to remove all cached_result attribute from every fixture

    Parameters
    ----------
    item: Function
    """
    try:
        info = getattr(item, "_fixtureinfo")
    except AttributeError:
        # doctests items have no _fixtureinfo attribute
        return False
    if not info.name2fixturedefs:
        # this test item does not use any fixtures
        return False

    for _, fixture_defs in sorted(info.name2fixturedefs.items()):
        if not fixture_defs:
            continue
        for fixture_def in fixture_defs:
            if hasattr(fixture_def, "cached_result"):
                fixture_def.cached_result = None
    return True


def _remove_failed_setup_state_from_session(item):
    """
    Force to call teardown for item.

    Parameters
    ----------
    item: Function
    """
    setup_state = getattr(item.session, "_setupstate")
    if hasattr(setup_state, "teardown_all"):
        setup_state.teardown_all()  # until pytest 6.2.5
    else:
        setup_state.teardown_exact(None)  # from pytest 7.0.0
    return True


def refresh_state(item):
    """
    Parameters
    ----------
    item: Function
    """
    _remove_cached_results_from_failed_fixtures(item)
    _remove_failed_setup_state_from_session(item)
    return True


def write_coupled_report(coupled_tests):
    """
    Parameters
    ----------
    coupled_tests: List[_pytest.python.Function]
        list of coupled tests

    Returns
    -------
    str
    """
    # Can I get info about modified common fixtures?
    coupled_test_names = [t.nodeid.replace("::()::", "::") for t in coupled_tests]
    common_fixtures = set.intersection(*[set(t.fixturenames) for t in coupled_tests])
    coupled_tests = "\n".join(coupled_test_names)
    msg = f"Found coupled tests:\n{coupled_tests}\n\n"
    if common_fixtures:
        common_fixtures = "\n".join(common_fixtures)
        msg += f"Common fixtures:\n{common_fixtures}\n\n"
    coupled_test_names = " ".join(coupled_test_names)
    msg += f"How to reproduce:\npytest -l -vv {coupled_test_names}\n"
    return msg


def find_target_test(items, test_name):
    for idx, test_func in enumerate(items):
        if test_name in (test_func.name, test_func.nodeid):
            return idx, test_func

    raise NotFoundError.make_from(test_name, items)


def make_collection(items, binary_tree=None):
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


class Collection:
    def __init__(self, collection, binary_tree, target_test_method):
        self.collection = collection
        self.binary_tree = binary_tree
        self.target_test_method = target_test_method
        self.min = length(self.binary_tree, min)
        self.max = length(self.binary_tree, max)

    @classmethod
    def make(cls, items, target_test_method):
        binary_tree = make_tee((0, len(items)))
        collection = make_collection(items, binary_tree=binary_tree)
        return cls(
            collection=collection,
            binary_tree=binary_tree,
            target_test_method=target_test_method,
        )

    def send(self, is_fail: bool):
        items = self.collection.send(is_fail)
        if items:
            items.append(self.target_test_method)
            refresh_state(item=self.target_test_method)
        return items

    def __next__(self):
        items = next(self.collection)
        if items:
            items.append(self.target_test_method)
        return items

    def __str__(self):
        return draw_tree(self.binary_tree)


class Steps:
    STEPS_KEY = "PytestSherlock/steps"
    LAST_FAILED_KEY = "cache/lastfailed"

    def __init__(self, config: Config):
        self.config = config
        self.steps = []
        self.start_from_step = self.config.option.step

    def add(self, items):
        self.steps.append([item.nodeid for item in items])
        return True

    def setup_from_step(self, items):
        """
        Uses cache to get data about previous execution for filtering out tests only for this step.
        Could be useful in case when global state was modified and
        reduce step to reproduce an issue.

        Parameters
        ----------
        items: List[_pytest.python.Function]

        Returns
        -------
        List[_pytest.python.Function]
        """
        if self.start_from_step:
            target_step = self.start_from_step - 1
            if self.steps and len(self.steps) > target_step:
                tests_from_step = self.steps[target_step]
                items[:] = [item for item in items if item.nodeid in tests_from_step]
            else:
                # not found any steps in cache from previous execution
                self.start_from_step = None
        return items

    def read(self):
        pass

    def store(self, last_failed_items: Optional[List[Function]] = None):
        self.config.cache.set(self.STEPS_KEY, self.steps)
        if last_failed_items:
            self.config.cache.set(
                self.LAST_FAILED_KEY, {i.nodeid: True for i in last_failed_items}
            )


@contextlib.contextmanager
def log(item):
    item.ihook.pytest_runtest_logstart(nodeid=item.nodeid, location=item.location)
    yield item.ihook.pytest_runtest_logreport
    item.ihook.pytest_runtest_logfinish(nodeid=item.nodeid, location=item.location)


class Sherlock(object):
    KEY = "PytestSherlock/steps"

    def __init__(self, config):
        self.config: Config = config
        self._steps: Steps = Steps(self.config)
        # initialize via pytest_sessionstart
        self.reporter: Optional[TerminalReporter] = None
        self.session: Optional[Session] = None
        # initialize via pytest_collection_modifyitems
        self.collection: Optional[Collection] = None
        # initialize via pytest_runtest_makereport
        self.failed_report = None
        # initialize via pytest_runtestloop
        self.last_failed = None

    def write_step(self, step, maximum):
        """
        Write summary of steps
        For Example:
        _______________________________ Step [1 of 4]: _______________________________
        ...

        :param str|int step:
        :param str|int maximum:
        """
        message = f"Step [{step} of {maximum}]:"
        self.reporter.write_sep("_", message, yellow=True, bold=True)

    def reset_progress(self, items):
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

        Parameters
        ----------
        items: List[_pytest.python.Function]
            bucket of tests
        """
        self.failed_report = None
        setattr(self.reporter, "_progress_nodeids_reported", set())
        setattr(self.session, "testscollected", len(items))

    def patch_report(self, failed_report, coupled):
        """
        Patch reports console output and Junit result xml
        to avoid multi errors in report

        Parameters
        ----------
        failed_report: _pytest.runner.TestReport
        coupled: List[_pytest.python.Function]
            list of coupled tests, last should be a target
        """
        target_item = coupled[-1]
        if hasattr(failed_report.longrepr, "reprcrash"):
            message = failed_report.longrepr.reprcrash.message
        elif isinstance(failed_report.longrepr, six.string_types):
            message = failed_report.longrepr
        else:
            message = str(failed_report.longrepr)
        failed_report.longrepr = f"\n{write_coupled_report(coupled)}\n\n{message}"
        self.reporter.stats["failed"] = [failed_report]
        xml = getattr(self.config, "_xml", None)
        if xml:
            node_reporter = _NodeReporter(target_item.nodeid, xml)
            node_reporter.append_failure(failed_report)
            node_reporter.finalize()
            xml.node_reporters_ordered[:] = [node_reporter]
            xml.stats["failure"] = 1
        return True

    @pytest.hookimpl(hookwrapper=True, trylast=True)
    def pytest_sessionstart(self, session):
        self.session = session
        self._steps.read()
        if self.reporter is None:
            self.reporter = self.config.pluginmanager.get_plugin("terminalreporter")
        yield

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

        Parameters
        ----------
        session: _pytest.main.Session
        config: _pytest.config.Config
            pytest config object
        items: List[_pytest.python.Function]
            list of item objects
        """
        _ = session  # to make pylint happy
        if config.getoption("--flaky-test"):
            idx, target_test_method = find_target_test(
                items, config.option.flaky_test.strip()
            )
            target_items = sorted(
                self._steps.setup_from_step(items[:idx]),
                key=lambda item: (
                    len(set(item.fixturenames) & set(target_test_method.fixturenames)),
                    item.parent.nodeid,  # Can we do AST or Name or Content analysis?
                ),
                reverse=True,
            )
            items[:] = [target_test_method]
            self.collection = Collection.make(
                target_items, target_test_method=target_test_method
            )
        yield

    @pytest.hookimpl(trylast=True)
    def pytest_report_collectionfinish(self, config, startdir, items):
        """
        Write summary which minimum steps need to find guilty tests
        Parameters
        ----------
        config: _pytest.config.Config
            pytest config object
        startdir: py._path.local.LocalPath
        items: List[_pytest.python.Function]
            contain just target test
        """
        _ = config, startdir, items  # to make pylint happy
        msg = f"Try to find coupled tests in [{self.collection.min}-{self.collection.max}] steps"
        if self._steps.start_from_step:
            msg = f"{msg} (reproduce from {self._steps.start_from_step} step)"
        return msg

    def pytest_runtestloop(self, session):
        """
        Just fork origin pytest method and reuse own `pytest_runtest_protocol` inside
        session.items always a list with the single target test
        Parameters
        ----------
        session: _pytest.main.Session
        """
        if (
            session.testsfailed
            and not session.config.option.continue_on_collection_errors
        ):
            raise session.Interrupted(f"{session.testsfailed} errors during collection")

        if session.config.option.collectonly:
            return True

        step = 1
        items = next(self.collection)
        while items:
            self.write_step(step, self.collection.max)
            self.reset_progress(items)
            self._steps.add(items)

            for next_idx, item in enumerate(items, 1):
                next_item = items[next_idx] if next_idx < len(items) else None
                self.config.hook.pytest_runtest_protocol(item=item, nextitem=next_item)
                if session.shouldfail:
                    raise session.Failed(session.shouldfail)
                if session.shouldstop:
                    raise session.Interrupted(session.shouldstop)

            try:
                # shift left if a report is red or shifts right if green
                items = self.collection.send(bool(self.failed_report))
            except StopIteration as err:
                if len(items) != 2:  # the last iteration must contain two tests
                    raise SherlockError("Something is going wrong") from err
                if self.failed_report:
                    self.patch_report(self.failed_report, coupled=items)
                    self.last_failed = items
                break

            step += 1

        return True

    @pytest.hookimpl(hookwrapper=True, trylast=True)
    def pytest_runtest_makereport(self, item, call):
        _ = item, call  # to make pylint happy
        report = yield
        test_report = report.get_result()
        if (
            test_report.nodeid == self.collection.target_test_method.nodeid
            and test_report.outcome != "passed"
        ):
            self.failed_report = test_report
        elif test_report.outcome != "passed":
            test_report.outcome = "flaky"
            if self.config.getvalue("verbose") >= 2:
                if hasattr(test_report.longrepr, "toterminal"):
                    test_report.longrepr.toterminal(self.config.get_terminal_writer())
                else:
                    self.reporter.line(str(test_report.longrepr))

    @pytest.hookimpl(hookwrapper=True, trylast=True)
    def pytest_sessionfinish(self, session):
        _ = session  # to make pylint happy
        yield
        self._steps.store(self.last_failed)
