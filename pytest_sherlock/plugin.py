import pytest
from _pytest.runner import runtestprotocol


def pytest_addoption(parser):
    group = parser.getgroup(
        "sherlock",
        "Try to find coupled tests")
    group.addoption(
        "--flaky-test",
        action="store",
        dest="flaky_test",
        help="Set the flaky tests which probably have dependent tests",
    )


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


def refresh(item):
    _remove_cached_results_from_failed_fixtures(item)
    _remove_failed_setup_state_from_session(item)


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
                item.parent.nodeid
            ),
            reverse=True,
        )
        return tests


class Node(object):
    def __init__(self, items):
        self.value = items
        self.mid = len(self.value) // 2
        self._left = None
        self._right = None

    def _node_or_none(self, next_value):
        return Node(next_value) if next_value and len(next_value) != len(self.value) else None

    def depth(self):
        q = [{'node': self, 'depth': 0}]
        while len(q) > 0:
            item = q.pop()
            node = item['node']
            depth = item['depth']
            if node.left is None and node.right is None:
                return depth

            if node.left is not None:
                q.append({'node': node.left, 'depth': depth + 1})

            if node.right is not None:
                q.append({'node': node.right, 'depth': depth + 1})

    @property
    def left(self):
        if self._left is None:
            self._left = self._node_or_none(self.value[:self.mid])
        return self._left

    @property
    def right(self):
        if self._right is None:
            self._right = self._node_or_none(self.value[self.mid:])
        return self._right

    def __len__(self):
        return len(self.value) if self.value else 0

    def __str__(self):
        s = "<Node length={}".format(len(self.value))
        if self.left:
            s += " left={}".format(len(self.left))
        if self.right:
            s += " right={}".format(len(self.right))
        return s + ">"

    def __repr__(self):
        return self.__str__()


@pytest.hookimpl(hookwrapper=True)
def pytest_collection_modifyitems(session, config, items):
    """
    called after collection has been performed, may filter or re-order
    the items in-place.

    :param _pytest.config.Config config: pytest config object
    :param List[_pytest.nodes.Item] items: list of item objects
    """
    if config.getoption("--flaky-test"):
        # TODO move to custom hooks
        test_collection = TestCollection(items)
        tests_binary_tree = Node(test_collection.needed_tests(config.option.flaky_test))
        session.tests_binary_tree = tests_binary_tree
        items[:] = [test_collection.test_func]
    # outcome = yield
    yield


def pytest_runtest_protocol(item, nextitem):
    tbt = item.session.tests_binary_tree
    tw = item.config.get_terminal_writer()
    tw.line()
    steps = 1
    while tbt is not None and len(tbt.value) >= 1:
        tw.write("Step #{}:".format(steps))
        current_tests = tbt.left.value if tbt.left is not None else tbt.value
        for next_idx, test_func in enumerate(current_tests, 1):
            # refresh(test_func)
            item.ihook.pytest_runtest_logstart(nodeid=test_func.nodeid, location=test_func.location)
            reports = runtestprotocol(
                item=test_func,
                nextitem=current_tests[next_idx] if next_idx < len(current_tests) else item,
                log=False,
            )
            for report in reports:  # 3 reports: setup, call, teardown
                if report.failed is True:
                    report.outcome = 'flaky'
                item.ihook.pytest_runtest_logreport(report=report)
            item.ihook.pytest_runtest_logfinish(
                nodeid=test_func.nodeid,
                location=test_func.location
            )

        item.ihook.pytest_runtest_logstart(nodeid=item.nodeid, location=item.location)
        reports = runtestprotocol(item, log=False)
        for report in reports:  # 3 reports: setup, call, teardown
            if report.failed is True:
                report.outcome = 'coupled'
                item.ihook.pytest_runtest_logreport(report=report)
                # TODO need optimize and refactoring
                tbt = tbt.left
                if len(current_tests) == 1:
                    tbt = None
                refresh(item)
                break
            item.ihook.pytest_runtest_logreport(report=report)
        else:
            tbt = tbt.right
        item.ihook.pytest_runtest_logfinish(nodeid=item.nodeid, location=item.location)
        steps += 1
    return True


@pytest.hookimpl(trylast=True)
def pytest_report_collectionfinish(config, startdir, items):
    return "Try to find coupled tests"


def pytest_report_teststatus(report):
    if report.outcome == 'coupled':
        return 'failed', 'C', ('COUPLED', {'red': True})
    elif report.outcome == 'flaky':
        return 'flaky', 'F', ('FLAKY', {'yellow': True})
