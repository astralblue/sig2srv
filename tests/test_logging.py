from logging import getLogger, DEBUG, INFO, WARNING, ERROR, CRITICAL
from unittest.mock import MagicMock, patch

import pytest

from sig2srv.logging import WithLog, logger as module_logger, BraceMessage


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


class TestWithLog:

    def test_init_takes_logger_kwarg(self):
        class Super:
            def __init__(self, *poargs, **kwargs):
                self.poargs = poargs
                self.kwargs = kwargs
        class Sub(WithLog, Super):
            pass
        sut = Sub(1, 2, 3, a=4, b=5, logger=None, c=6)
        assert sut.poargs == (1, 2, 3)
        assert sut.kwargs == dict(a=4, b=5, c=6)

    def test_avails_logger(self):
        logger = getLogger(__name__)
        sut = WithLog(logger=logger)
        assert sut.logger is logger

    def test_logger_is_readonly(self):
        logger = getLogger(__name__)
        sut = WithLog()
        with pytest.raises(AttributeError):
            sut.logger = logger

    def test_no_logger_uses_module_logger(self):
        global module_logger
        sut = WithLog()
        assert sut.logger is module_logger

    @pytest.fixture
    def mock_logger(self):
        return MagicMock(spec=module_logger)

    def test_log(self, mock_logger):
        class Caller(WithLog):
            def __repr__(self):
                return "Caller(x={})"

            def test(self, fmt, *poargs, **kwargs):
                self._log(fmt, *poargs, **kwargs)

        with patch('sig2srv.logging.BraceMessage') as BraceMessageMock:
            caller = Caller(logger=mock_logger)
            caller.test(INFO, "abc=%d", 3)
            BraceMessageMock.assert_called_once_with(
                    "Caller(x={{}}).test(): abc=%d", 3,
            )
            bm = BraceMessageMock.return_value
            assert bm is not None
            assert len(mock_logger.log.call_args_list) == 1
            poargs, kwargs = mock_logger.log.call_args_list[0]
            assert len(poargs) == 2
            assert len(kwargs) == 0
            assert poargs[0] == INFO
            assert poargs[1] is bm

    @pytest.fixture
    def with_log(self, mock_logger):
        return WithLog(logger=mock_logger)

    @pytest.mark.parametrize('name,level', [
        ('_debug', DEBUG),
        ('_info', INFO),
        ('_warning', WARNING),
        ('_error', ERROR),
        ('_critical', CRITICAL),
    ])
    def test_shorthands(self, with_log, name, level):
        with patch.object(with_log, '_log') as log:
            getattr(with_log, name)("OMG", 1, 2, 3, a=4, b=5, c=6)
            log.assert_called_once_with(level, "OMG", 1, 2, 3, a=4, b=5, c=6,
                                        log_depth=1)
