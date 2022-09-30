from __future__ import absolute_import

import contextlib

import pytest
import six
from _pytest.junitxml import _NodeReporter

from pytest_sherlock.binary_tree_search import length, make_tee


class SherlockError(Exception):
    pass


class NotFoundError(SherlockError):
    @classmethod
    def make_from(cls, test_name, items):
        msg = (
            "Test not found: {}. "
            "Please validate your test name (ex: 'tests/unit/test_one.py::test_first')"
        ).format(test_name)

        if ".py::" in test_name:
            target_test_name = test_name.split("::")[-1]
        else:
            target_test_name = test_name.split("[")[0]
        target_test_names = [i.nodeid for i in items if target_test_name in i.name]
        if target_test_names:
            msg += "\nFound similar test names: {}".format(target_test_names)
        return cls(msg)


def _remove_cached_results_from_failed_fixtures(item):
    """
    Note: remove all cached_result attribute from every fixture
    """
    try:
        info = item._fixtureinfo
    except AttributeError:
        # doctests items have no _fixtureinfo attribute
        return
    if not info.name2fixturedefs:
        # this test item does not use any fixtures
        return

    for _, fixture_defs in sorted(info.name2fixturedefs.items()):
        if not fixture_defs:
            continue
        for fixture_def in fixture_defs:
            if hasattr(fixture_def, "cached_result"):
                del fixture_def.cached_result
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
    setup_state.stack = []
    return True


def refresh_state(item):
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


@contextlib.contextmanager
def log(item):
    item.ihook.pytest_runtest_logstart(nodeid=item.nodeid, location=item.location)
    yield item.ihook.pytest_runtest_logreport
    item.ihook.pytest_runtest_logfinish(nodeid=item.nodeid, location=item.location)


class Cache(object):
    def __init__(self, config):
        """
        Parameters
        ----------
        config: _pytest.config.Config
        """
        self.config = config
        self._data = []

    def get(self):
        """
        Returns
        -------
        list[list[str]]
        """
        return self.config.cache.get(self.KEY, [])

    def add(self, items):
        """
        Parameters
        ----------
        items: list[_pytest.python.Function]

        Returns
        -------
        bool
        """
        self._data.append([item.nodeid for item in items])
        return True

    def store(self):

        return True


class Sherlock(object):
    KEY = "PytestSherlock/steps"

    def __init__(self, config):
        self.config = config
        self._steps = []
        self.start_from_step = self.config.option.step
        self.verbose = self.config.getvalue("verbose") >= 2
        # initialize via pytest_sessionstart
        self.reporter = None
        self.session = None
        # initialize via pytest_collection_modifyitems
        self.collection = None
        self.target_test_method = None
        self._min_iterations = 0
        self._max_iterations = 0
        # initialize via pytest_runtest_makereport
        self.failed_report = None
        # initialize via pytest_runtestloop
        self.last_failed = None

    def add_step(self, items):
        self._steps.append([item.nodeid for item in items])
        return True

    def setup_from_step(self, items):
        """
        Uses cache to get data about previous execution for filtering out tests only for this step.
        Could be useful in case when global state was modified and
        reduce step to reproduce an issue.

        Parameters
        ----------
        items: list[_pytest.python.Function]

        Returns
        -------
        list[_pytest.python.Function]
        """
        if self.start_from_step:
            target_step = self.start_from_step - 1
            if self._steps and len(self._steps) > target_step:
                tests_from_step = self._steps[target_step]
                items[:] = [item for item in items if item.nodeid in tests_from_step]
            else:
                # not found any steps in cache from previous execution
                self.start_from_step = None
        return items

    def write_step(self, step, maximum):
        """
        Write summary of steps
        For Example:
        _______________________________ Step [1 of 4]: _______________________________
        ...

        :param str|int step:
        :param str|int maximum:
        """
        message = "Step [{} of {}]:".format(step, maximum)
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

        :param list[_pytest.python.Function] items: bucket of tests
        """
        self.failed_report = None
        setattr(self.reporter, "_progress_nodeids_reported", set())
        setattr(self.session, "testscollected", len(items))

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

    @pytest.hookimpl(hookwrapper=True, trylast=True)
    def pytest_sessionstart(self, session):
        self.session = session
        self._steps = self.config.cache.get(self.KEY, [])
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

        :param _pytest.main.Session session:
        :param _pytest.config.Config config: pytest config object
        :param List[_pytest.python.Function] items: list of item objects
        """
        if config.getoption("--flaky-test"):
            idx, target_test_method = find_target_test(
                items, config.option.flaky_test.strip()
            )
            target_items = sorted(
                self.setup_from_step(items[:idx]),
                key=lambda item: (
                    len(set(item.fixturenames) & set(target_test_method.fixturenames)),
                    item.parent.nodeid,  # TODO can we do AST or Name or Content analysis?
                ),
                reverse=True,
            )
            items[:] = [target_test_method]
            self.target_test_method = target_test_method
            binary_tree = make_tee((0, len(target_items)))
            self._min_iterations = length(binary_tree, min)
            self._max_iterations = length(binary_tree, max)
            self.collection = make_collection(target_items, binary_tree=binary_tree)
        yield

    @pytest.hookimpl(trylast=True)
    def pytest_report_collectionfinish(self, config, startdir, items):
        """
        Write summary which minimum steps need to find guilty tests
        :param _pytest.config.Config config: pytest config object
        :param py._path.local.LocalPath startdir:
        :param List[_pytest.python.Function] items: contain just target test
        """
        msg = "Try to find coupled tests in [{}-{}] steps".format(
            self._min_iterations, self._max_iterations
        )
        if self.start_from_step:
            msg = "{} (reproduce from {} step)".format(msg, self.start_from_step)
        return msg

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

        step = 1
        items = next(self.collection)
        while items:
            items.append(self.target_test_method)
            self.write_step(step, self._max_iterations)
            self.reset_progress(items)
            self.add_step(items)

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
            except StopIteration:
                if len(items) != 2:  # the last iteration must contain two tests
                    raise SherlockError("Something is going wrong")
                if self.failed_report:
                    self.patch_report(self.failed_report, coupled=items)
                    self.last_failed = items
                break

            step += 1
            refresh_state(item=self.target_test_method)
        return True

    @pytest.hookimpl(hookwrapper=True, trylast=True)
    def pytest_runtest_makereport(self, item, call):
        report = yield
        test_report = report.get_result()
        if (
            test_report.nodeid == self.target_test_method.nodeid
            and test_report.outcome != "passed"
        ):
            self.failed_report = test_report
        elif test_report.outcome != "passed":
            test_report.outcome = "flaky"
            if self.verbose:
                test_report.longrepr.toterminal(self.reporter._tw)

    @pytest.hookimpl(hookwrapper=True, trylast=True)
    def pytest_sessionfinish(self, session):
        yield
        self.config.cache.set(self.KEY, self._steps)
        if self.last_failed:
            self.config.cache.set(
                "cache/lastfailed", {i.nodeid: True for i in self.last_failed}
            )
