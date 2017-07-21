from asyncio import (CancelledError, Event, Task, ensure_future,
                     get_event_loop, sleep)
from contextlib import contextmanager
import sys
from unittest.mock import MagicMock, patch, ANY

import pytest

from sig2srv.asynchelper import (WithEventLoop, PeriodicCaller, periodic_calls,
                                 signal_handled)


class TestWithEventLoop:
    def test_init_uses_default_loop_if_not_given(self, event_loop):
        sut = WithEventLoop()
        assert sut.loop is get_event_loop()

    def test_init_takes_and_avails_event_loop(self, event_loop):
        assert event_loop is not get_event_loop()
        sut = WithEventLoop(loop=event_loop)
        assert sut.loop is event_loop

    def test_init_raises_assertion_error_for_bad_loop(self):
        with pytest.raises(AssertionError):
            WithEventLoop(loop=1)


class TimeMachine:
    """A helper to advance an event loop's time.

    :param `AbstractEventLoop` event_loop: the event loop to monkey-patch.
    """

    def __init__(self, *poargs, event_loop, **kwargs):
        super().__init__(*poargs, **kwargs)
        self.__original_time = event_loop.time
        self.__delta = 0
        event_loop.time = self.__time

    def __time(self):
        return self.__original_time() + self.__delta

    def advance_by(self, amount):
        """Advance the time reference by the given amount.

        :param `float` amount: number of seconds to advance.
        :raise `ValueError`: if *amount* is negative.
        """
        if amount < 0:
            raise ValueError("cannot retreat time reference: amount {} < 0"
                             .format(amount))
        self.__delta += amount

    def advance_to(self, timestamp):
        """Advance the time reference so that now is the given timestamp.

        :param `float` timestamp: the new current timestamp.
        :raise `ValueError`: if *timestamp* is in the past.
        """
        now = self.__original_time()
        if timestamp < now:
            raise ValueError("cannot retreat time reference: "
                             "target {} < now {}"
                             .format(timestamp, now))
        self.__delta = timestamp - now


class TestPeriodicCaller:
    def test_init_requires_cb_as_poarg_1(self):
        with pytest.raises(TypeError):
            PeriodicCaller()

    def test_init_requires_period_as_poarg_2(self):
        with pytest.raises(TypeError):
            PeriodicCaller(lambda: None)

    def test_init_accepts_period_as_kwarg(self):
        PeriodicCaller(lambda: None, period=10)

    def test_init_accepts_cb_as_kwarg(self):
        PeriodicCaller(cb=lambda: None, period=10)

    def test_init_accepts_bg_as_kwarg(self):
        PeriodicCaller(lambda: None, 10, bg=True)

    def test_init_accepts_on_ret_as_kwarg(self):
        PeriodicCaller(lambda: None, 10, on_ret=lambda ret: None)

    def test_init_accepts_on_exc_as_kwarg(self):
        PeriodicCaller(lambda: None, 10, on_exc=lambda exc: None)

    def test_init_passes_other_args_to_super(self):
        class Super:
            def __init__(self, *poargs, **kwargs):
                self.poargs = poargs
                self.kwargs = kwargs

        class Sub(PeriodicCaller, Super):
            pass

        sub = Sub(lambda: None, 10, 'foo', 'bar', omg='wtf', bbq='cakes')
        assert sub.poargs == ('foo', 'bar')
        assert sub.kwargs == {'omg': 'wtf', 'bbq': 'cakes'}

    def test_init_asserts_cb_is_callable(self):
        with pytest.raises(AssertionError):
            PeriodicCaller(None, 10)

    def test_init_accepts_none_as_on_ret(self):
        PeriodicCaller(lambda: None, 10, on_ret=None)

    def test_init_asserts_on_ret_is_callable(self):
        with pytest.raises(AssertionError):
            PeriodicCaller(lambda: None, 10, on_ret=0)

    def test_init_accepts_none_as_on_exc(self):
        PeriodicCaller(lambda: None, 10, on_exc=None)

    def test_init_asserts_on_exc_is_callable(self):
        with pytest.raises(AssertionError):
            PeriodicCaller(lambda: None, 10, on_exc=0)

    def test_init_accepts_event_loop(self, event_loop):
        PeriodicCaller(lambda: None, 10, loop=event_loop)

    def test_init_does_not_automatically_schedule_tasks(self, event_loop):
        event_loop = MagicMock(spec=event_loop, wraps=event_loop)
        PeriodicCaller(lambda: None, 10, loop=event_loop)
        event_loop.call_at.assert_not_called()

    def test_start_starts_one_task(self, event_loop):
        event_loop = MagicMock(spec=event_loop, wraps=event_loop)
        pc = PeriodicCaller(lambda: None, 10, loop=event_loop)
        pc.start()
        event_loop.call_at.assert_called_once_with(ANY, ANY)

    def test_start_accepts_at_as_poarg_1(self, event_loop):
        event_loop = MagicMock(spec=event_loop, wraps=event_loop)
        pc = PeriodicCaller(lambda: None, 10, loop=event_loop)
        pc.start(12345)
        event_loop.call_at.assert_called_once_with(12345, ANY)

    def test_start_accepts_at_as_kwarg(self, event_loop):
        event_loop = MagicMock(spec=event_loop, wraps=event_loop)
        pc = PeriodicCaller(lambda: None, 10, loop=event_loop)
        pc.start(at=12345)
        event_loop.call_at.assert_called_once_with(12345, ANY)

    def test_start_at_defaults_to_now_plus_period(self, event_loop):
        event_loop = MagicMock(spec=event_loop, wraps=event_loop)
        event_loop.time.return_value = 12345
        pc = PeriodicCaller(lambda: None, 65432, loop=event_loop)
        pc.start()
        event_loop.call_at.assert_called_once_with(77777, ANY)

    def test_start_does_nothing_if_already_started(self, event_loop):
        event_loop = MagicMock(spec=event_loop, wraps=event_loop)
        pc = PeriodicCaller(lambda: None, 10, loop=event_loop)
        pc.start()
        event_loop.call_at.reset_mock()
        pc.start()
        event_loop.call_at.assert_not_called()

    def test_stop_stops_current_task(self, event_loop):
        event_loop = MagicMock(spec=event_loop, wraps=event_loop)
        handle = MagicMock()
        event_loop.call_at.return_value = handle
        pc = PeriodicCaller(lambda: None, 10, loop=event_loop)
        pc.start()
        handle.cancel.assert_not_called()
        pc.stop()
        handle.cancel.assert_called_once_with()

    def test_stop_is_idempotent(self, event_loop):
        event_loop = MagicMock(spec=event_loop, wraps=event_loop)
        handle = MagicMock()
        event_loop.call_at.return_value = handle
        pc = PeriodicCaller(lambda: None, 10, loop=event_loop)
        pc.stop()
        handle.cancel.assert_not_called()
        pc.start()
        pc.stop()
        handle.cancel.assert_called_once_with()
        handle.cancel.reset_mock()
        pc.stop()
        handle.cancel.assert_not_called()

    def __cb_timestamp_test(self, event_loop, scheduled, start_at):
        tm = TimeMachine(event_loop=event_loop)
        sentinel = ensure_future(sleep(scheduled[-1] - event_loop.time() + 1),
                                 loop=event_loop)
        remaining = scheduled.copy()
        called = []
        def cb(ts):
            remaining.pop(0)
            called.append(ts)
            if remaining:
                tm.advance_to(remaining[0])
            else:
                sentinel.cancel()
        pc = PeriodicCaller(cb, 1, loop=event_loop)
        pc.start(at=start_at)
        tm.advance_to(scheduled[0])
        with pytest.raises(CancelledError):
            event_loop.run_until_complete(sentinel)
        assert not remaining
        return called

    def test_cb_called_with_scheduled_time(self, event_loop):
        now = event_loop.time()
        scheduled = [now + i for i in range(1, 5)]
        called = self.__cb_timestamp_test(event_loop, scheduled, None)
        assert called == pytest.approx(scheduled)

    def test_start_at_passes_exact_scheduled_time(self, event_loop):
        start_at = event_loop.time() + 1
        scheduled = [start_at + i for i in range(5)]
        called = self.__cb_timestamp_test(event_loop, scheduled, start_at)
        assert scheduled == called

    def test_on_ret_called_with_sync_retval(self, event_loop):
        tm = TimeMachine(event_loop=event_loop)
        sentinel = ensure_future(sleep(2), loop=event_loop)
        def cb(ts):
            sentinel.cancel()
            return 123
        captured = []
        def on_ret(ret):
            captured.append(ret)
        pc = PeriodicCaller(cb, 1, loop=event_loop, on_ret=on_ret)
        pc.start()
        tm.advance_by(1)
        with pytest.raises(CancelledError):
            event_loop.run_until_complete(sentinel)
        assert captured == [123]

    def test_on_exc_called_with_sync_exception(self, event_loop):
        tm = TimeMachine(event_loop=event_loop)
        sentinel = ensure_future(sleep(2), loop=event_loop)
        raised = []
        def cb(ts):
            sentinel.cancel()
            try:
                raise RuntimeError("omg")
            except Exception as e:
                raised.append(e)
                raise
        caught = []
        def on_exc(exc):
            caught.append(exc)
        pc = PeriodicCaller(cb, 1, loop=event_loop, on_exc=on_exc)
        pc.start()
        tm.advance_by(1)
        with pytest.raises(CancelledError):
            event_loop.run_until_complete(sentinel)
        assert raised == caught
        assert raised
        assert caught

    def test_on_ret_called_with_async_fg_retval(self, event_loop):
        tm = TimeMachine(event_loop=event_loop)
        sentinel = ensure_future(sleep(2), loop=event_loop)
        async def cb(ts):
            sentinel.cancel()
            return 123
        captured = []
        def on_ret(ret):
            captured.append(ret)
        pc = PeriodicCaller(cb, 1, loop=event_loop, bg=False, on_ret=on_ret)
        pc.start()
        tm.advance_by(1)
        with pytest.raises(CancelledError):
            event_loop.run_until_complete(sentinel)
        assert captured == [123]

    def test_on_exc_called_with_async_fg_exception(self, event_loop):
        tm = TimeMachine(event_loop=event_loop)
        sentinel = ensure_future(sleep(2), loop=event_loop)
        raised = []
        async def cb(ts):
            sentinel.cancel()
            try:
                raise RuntimeError("omg")
            except Exception as e:
                raised.append(e)
                raise
        caught = []
        def on_exc(exc):
            caught.append(exc)
        pc = PeriodicCaller(cb, 1, loop=event_loop, bg=False, on_exc=on_exc)
        pc.start()
        tm.advance_by(1)
        with pytest.raises(CancelledError):
            event_loop.run_until_complete(sentinel)
        assert raised == caught
        assert raised
        assert caught

    @patch('sig2srv.asynchelper.PeriodicCaller', autospec=True)
    def test_periodic_calls(self, cls):
        obj = MagicMock()
        cls.return_value = obj
        obj.start = MagicMock()
        obj.stop = MagicMock()
        with periodic_calls(1, 2, 3, omg=4, at=5, wtf=6) as caller:
            cls.assert_called_once_with(1, 2, 3, omg=4, wtf=6)
            assert caller is obj
            obj.start.assert_called_once_with(at=5)
            obj.stop.assert_not_called()
        obj.stop.assert_called_once_with()


class TestSignalHandled:
    def test_main_behavior(self):
        loop = MagicMock(spec=['add_signal_handler', 'remove_signal_handler'])
        loop.add_signal_handler = MagicMock()
        loop.remove_signal_handler = MagicMock()
        manager = signal_handled('SIG', 'HANDLER', loop=loop)
        loop.add_signal_handler.assert_not_called()
        loop.remove_signal_handler.assert_not_called()
        with manager:
            loop.add_signal_handler.assert_called_once_with('SIG', 'HANDLER')
            loop.remove_signal_handler.assert_not_called()
        loop.add_signal_handler.assert_called_once_with('SIG', 'HANDLER')
        loop.remove_signal_handler.assert_called_once_with('SIG')
