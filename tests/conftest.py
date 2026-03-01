import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run integration tests that call external APIs.",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-integration"):
        return

    skip_integration = pytest.mark.skip(
        reason="Integration tests are skipped by default. Use --run-integration."
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)
