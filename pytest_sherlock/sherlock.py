import contextlib

import pytest
from _pytest.runner import runtestprotocol

from pytest_sherlock.binary_tree_search import Root as BTSRoot


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


def refresh(item):
    _remove_cached_results_from_failed_fixtures(item)
    _remove_failed_setup_state_from_session(item)
    return True


class TestCollection(object):

    def __init__(self, items):
        self.items = items
        self.test_func = None

    def needed_tests(self, test_name):
        tests = []
        for test_func in self.items:
            if test_func.name == test_name or test_func.nodeid == test_name:
                self.test_func = test_func
                break
            tests.append(test_func)

        if self.test_func is None:
            raise RuntimeError("Validate your test name (ex: 'tests/unit/test_one.py::test_first')")

        tests[:] = sorted(
            tests,
            key=lambda item: (
                len(set(item.fixturenames) & set(self.test_func.fixturenames)),
                item.parent.nodeid  # TODO add ast analise
            ),
            reverse=True,
        )
        return tests


class Sherlock(object):
    def __init__(self, config):
        self.config = config
        self.bts_root = BTSRoot()
        self.tw = None

    @property
    def terminal(self):
        if self.tw is None:
            self.tw = self.config.get_terminal_writer()
        return self.tw

    def write_step(self, step):
        self.terminal.line()
        self.terminal.write("Step #{}:".format(step))

    @contextlib.contextmanager
    def log(self, item):
        item.ihook.pytest_runtest_logstart(nodeid=item.nodeid, location=item.location)
        yield item.ihook.pytest_runtest_logreport
        item.ihook.pytest_runtest_logfinish(nodeid=item.nodeid, location=item.location)

    @staticmethod
    def refresh_state(item):
        return refresh(item)

    @pytest.hookimpl(hookwrapper=True)
    def pytest_collection_modifyitems(self, session, config, items):
        """
        called after collection has been performed, may filter or re-order
        the items in-place.

        :param _pytest.config.Config config: pytest config object
        :param List[_pytest.nodes.Item] items: list of item objects
        """
        if config.getoption("--flaky-test"):
            test_collection = TestCollection(items)
            self.bts_root.insert(test_collection.needed_tests(config.option.flaky_test))
            items[:] = [test_collection.test_func]
        # outcome = yield
        yield

    @pytest.hookimpl(trylast=True)
    def pytest_report_collectionfinish(self, config, startdir, items):
        # TODO add bts length
        return "Try to find coupled tests"

    def pytest_runtest_protocol(self, item, nextitem):
        steps = 1
        root = self.bts_root.root
        while root is not None:
            self.write_step(steps)
            current_tests = root.left.value if root.left is not None else root.value
            self.call_items(target_item=item, items=current_tests)
            is_target_test_success = self.call_target(target_item=item)
            if is_target_test_success:
                root = root.right
            else:
                if len(current_tests) == 1:
                    break
                root = root.left
            steps += 1
        return True

    def call_items(self, target_item, items):
        for next_idx, test_func in enumerate(items, 1):
            # refresh(test_func)  # TODO maybe need to refresh state for all previous tests
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
