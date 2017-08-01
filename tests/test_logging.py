import pytest

from sig2srv.logging import BraceMessage


class TestBraceMessage:

    @pytest.fixture
    def fmt(self):
        return "abc={} def={} ghi={ghi}"

    @pytest.fixture
    def brace_message(self, fmt):
        return BraceMessage(fmt, 3, 'DEF', ghi='GHI')

    def test_init_captures_all_args(self, fmt):
        class Super:
            def __init__(self, *poargs, **kwargs):
                self.super_poargs = poargs
                self.super_kwargs = kwargs
        class Sub(BraceMessage, Super):
            pass
        brace_message = Sub(fmt, 3, 'DEF', ghi='GHI')
        assert brace_message.fmt == fmt
        assert brace_message.poargs == (3, 'DEF')
        assert brace_message.kwargs == dict(ghi='GHI')
        assert not brace_message.super_poargs
        assert not brace_message.super_kwargs

    def test_str_formats(self, brace_message):
        assert str(brace_message) == 'abc=3 def=DEF ghi=GHI'
