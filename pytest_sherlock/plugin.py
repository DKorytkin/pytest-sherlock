from __future__ import absolute_import

from pytest_sherlock.sherlock import Sherlock


def pytest_addoption(parser):
    group = parser.getgroup("sherlock", "Try to find coupled tests")
    group.addoption(
        "--flaky-test",
        action="store",
        dest="flaky_test",
        help="Set the flaky tests which probably have dependent tests",
    )
    group.addoption(
        "--step",
        action="store",
        dest="step",
        type=int,
        help="Reproduce from exists steps `Step [1 of ...]`",
    )


def pytest_configure(config):
    """Find and load configuration file onto the session."""
    if not config.getoption("--flaky-test"):
        return

    config.sherlock = Sherlock(config)
    config.pluginmanager.register(config.sherlock)


def pytest_report_teststatus(report):
    if report.outcome == "flaky":
        return "flaky", "F", ("FLAKY", {"yellow": True})
