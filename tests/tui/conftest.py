import httpx
import pytest

from kp9.tui.app import Kp9App

KEYS = {" ": "space", ":": "colon", "/": "slash", "-": "minus", ".": "full_stop", "_": "underscore"}


@pytest.fixture
def make_app(sample_ws, recorder):
    def factory(root=None, handler=None):
        transport = httpx.MockTransport(handler or recorder)
        client = httpx.AsyncClient(transport=transport)
        return Kp9App(root or sample_ws, client=client, environ={}, watch=False)

    return factory


@pytest.fixture
def type_keys():
    async def _type(pilot, text):
        for ch in text:
            await pilot.press(KEYS.get(ch, ch))
        await pilot.pause()

    return _type
