from asyncio import new_event_loop

import pytest


@pytest.fixture
def event_loop():
    loop = new_event_loop()
    loop.debug = True
    try:
        yield loop
    finally:
        loop.close()
