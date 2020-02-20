import itertools

import pytest
from _pytest.runner import runtestprotocol


def pytest_addoption(parser):
    group = parser.getgroup(
        "sherlock",
        "find coupled tests")
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
            if hasattr(fixture_def, cached_result):
                result, cache_key, err = getattr(fixture_def, cached_result)
                if err:  # Deleting cached results for only failed fixtures
                    delattr(fixture_def, cached_result)


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

    def needed_tests(self, test_name):
        tests = []
        current_test_func = None
        for test_func in self.items:

            if test_func.name == test_name or test_func.nodeid == test_name:
                current_test_func = test_func
                break
            tests.append(test_func)

        if current_test_func is None:
            raise RuntimeError("Validate your test name (ex: 'tests/unit/test_one.py::test_first')")

        tests[:] = sorted(
            tests,
            key=lambda item: len(set(item.fixturenames) & set(current_test_func.fixturenames)),
            reverse=True
        )
        return itertools.product(tests, [current_test_func])

    def chain_for(self, test_name):
        return itertools.chain.from_iterable(self.needed_tests(test_name))


@pytest.hookimpl(hookwrapper=True)
def pytest_collection_modifyitems(session, config, items):
    """
    called after collection has been performed, may filter or re-order
    the items in-place.

    :param _pytest.config.Config config: pytest config object
    :param List[_pytest.nodes.Item] items: list of item objects
    """
    if config.getoption("--flaky-test"):
        test_collection = TestCollection(items)
        items[:] = test_collection.chain_for(config.option.flaky_test)
    # outcome = yield
    yield


def pytest_runtest_protocol(item, nextitem):
    current_test = item.session.config.option.flaky_test
    item.ihook.pytest_runtest_logstart(nodeid=item.nodeid, location=item.location)
    reports = runtestprotocol(item, nextitem=nextitem)
    for report in reports:  # 3 reports: setup, call, teardown
        if report.when == 'call' and report.outcome == 'failed':
            if item.name != current_test or item.nodeid != current_test:
                report.outcome = 'coupled'
                # TODO add firstfailed param -x
            else:
                report.outcome = 'flaky'
            refresh(item)
    item.ihook.pytest_runtest_logfinish(nodeid=item.nodeid, location=item.location)
    return True


@pytest.hookimpl(trylast=True)
def pytest_report_collectionfinish(config, startdir, items):
    return "Try to find coupled tests:"


def pytest_report_teststatus(report):
    if report.outcome == 'coupled':
        return 'coupled', 'C', ('COUPLED', {'yellow': True})
    elif report.outcome == 'flaky':
        return 'flaky', 'F', ('FLAKY', {'yellow': True})
