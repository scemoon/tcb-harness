"""pytest-bdd configuration for ai-dlc."""
import pytest
from pathlib import Path


def pytest_bdd_get_features_paths():
    """Return all paths containing BDD feature files."""
    return [
        Path("pybdd"),
        Path("aidlc"),
    ]


@pytest.fixture
def pybdd_root():
    """Return the root directory for BDD features."""
    return Path(__file__).parent.parent
