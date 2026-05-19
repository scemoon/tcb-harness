import pytest
import pytest_asyncio


@pytest.fixture
def pilot_factory():
    from textual.pilot import Pilot
    return Pilot


@pytest_asyncio.fixture
async def pilot(app, event_loop):
    """Provide a pilot fixture for TUI tests."""
    async with app.run_test(size=(120, 40), handle_crash=True) as p:
        yield p