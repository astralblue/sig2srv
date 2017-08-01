from asyncio import (CancelledError, Event, Task, coroutine,
                     async as ensure_future, get_event_loop, sleep)
from contextlib import contextmanager
import sys
from unittest.mock import MagicMock, patch, ANY

from asynciotimemachine import TimeMachine
import pytest

from sig2srv.asynchelper import (WithEventLoop, PeriodicCaller, periodic_calls,
                                 signal_handled)
from tests.eventloopfixture import event_loop


class TestWithEventLoop:
    def test_init_uses_default_loop_if_not_given(self):
        sut = WithEventLoop()
        assert sut.loop is get_event_loop()

    def test_init_takes_and_avails_event_loop(self, event_loop):
        assert event_loop is not get_event_loop()
        sut = WithEventLoop(loop=event_loop)
        assert sut.loop is event_loop

    def test_init_raises_assertion_error_for_bad_loop(self):
        with pytest.raises(AssertionError):
            WithEventLoop(loop=1)


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
        assert not event_loop.call_at.call_args_list

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
        assert not event_loop.call_at.call_args_list

    def test_stop_stops_current_task(self, event_loop):
        event_loop = MagicMock(spec=event_loop, wraps=event_loop)
        handle = MagicMock()
        event_loop.call_at.return_value = handle
        pc = PeriodicCaller(lambda: None, 10, loop=event_loop)
        pc.start()
        assert not handle.cancel.call_args_list
        pc.stop()
        handle.cancel.assert_called_once_with()

    def test_stop_is_idempotent(self, event_loop):
        event_loop = MagicMock(spec=event_loop, wraps=event_loop)
        handle = MagicMock()
        event_loop.call_at.return_value = handle
        pc = PeriodicCaller(lambda: None, 10, loop=event_loop)
        pc.stop()
        assert not handle.cancel.call_args_list
        pc.start()
        pc.stop()
        handle.cancel.assert_called_once_with()
        handle.cancel.reset_mock()
        pc.stop()
        assert not handle.cancel.call_args_list

    def __cb_timestamp_test(self, event_loop, scheduled, start_at):
        tm = TimeMachine(event_loop=event_loop)
        sentinel = ensure_future(sleep(scheduled[-1] - event_loop.time() + 1,
                                       loop=event_loop),
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

    def test_stop_can_be_called_from_within(self, event_loop):
        tm = TimeMachine(event_loop=event_loop)
        call_count = 0
        def cb(ts):
            nonlocal call_count
            call_count += 1
            tm.advance_by(60)
            pc.stop()
        pc = PeriodicCaller(cb, 10, loop=event_loop)
        pc.start()
        tm.advance_by(10)
        event_loop.run_until_complete(sleep(60, loop=event_loop))
        assert call_count == 1

    def test_on_ret_called_with_sync_retval(self, event_loop):
        tm = TimeMachine(event_loop=event_loop)
        sentinel = ensure_future(sleep(2, loop=event_loop), loop=event_loop)
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
        sentinel = ensure_future(sleep(2, loop=event_loop), loop=event_loop)
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
        sentinel = ensure_future(sleep(2, loop=event_loop), loop=event_loop)
        @coroutine
        def cb(ts):
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
        sentinel = ensure_future(sleep(2, loop=event_loop), loop=event_loop)
        raised = []
        @coroutine
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
        pc = PeriodicCaller(cb, 1, loop=event_loop, bg=False, on_exc=on_exc)
        pc.start()
        tm.advance_by(1)
        with pytest.raises(CancelledError):
            event_loop.run_until_complete(sentinel)
        assert raised == caught
        assert raised
        assert caught

    @pytest.mark.timeout(5)
    def test_async_bg(self, event_loop):
        cur = 0
        wm = 0
        tm = TimeMachine(event_loop=event_loop)
        dec_start = event_loop.time() + 31
        @coroutine
        def cb(ts):
            nonlocal cur, wm
            cur += 1
            wm = max(cur, wm)
            if cur == 10:
                pc.stop()
                tm.advance_to(dec_start)
            else:
                tm.advance_by(1)
            sleep_duration = ts + 30 - event_loop.time()
            assert sleep_duration > 0
            yield from sleep(sleep_duration, loop=event_loop)
            cur -= 1
            if cur == 0:
                event_loop.stop()
            else:
                tm.advance_by(1)
        pc = PeriodicCaller(cb, 1, loop=event_loop, bg=True)
        pc.start()
        tm.advance_by(1)
        event_loop.run_forever()
        assert cur == 0
        assert wm == 10

    def test_async_bg_callable(self, event_loop):
        tm = TimeMachine(event_loop=event_loop)
        handles = []
        remaining = 10
        @coroutine
        def cb(ts):
            nonlocal remaining
            tm.advance_by(1)
            ret = remaining
            if remaining == 0:
                pc.stop()
            else:
                remaining -= 1
            return ret
        def bg_callable(handle):
            handles.append(handle)
        pc = PeriodicCaller(cb, 1, loop=event_loop, bg=bg_callable)
        pc.start()
        tm.advance_by(1)
        event_loop.run_until_complete(sleep(remaining, loop=event_loop))
        assert remaining == 0
        assert ([handle.result() for handle in handles] ==
                list(reversed(range(11))))

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
            assert not obj.stop.call_args_list
        obj.stop.assert_called_once_with()

    @patch('sig2srv.asynchelper.PeriodicCaller', autospec=True)
    def test_periodic_calls_run_stop_on_exc(self, cls):
        obj = MagicMock()
        cls.return_value = obj
        obj.stop = MagicMock()
        with pytest.raises(RuntimeError):
            with periodic_calls(lambda ts: None, 10):
                raise RuntimeError("OMG")
        obj.stop.assert_called_once_with()


class TestSignalHandled:
    @pytest.fixture
    def loop(self):
        """Mock loop with add_signal_handler() and remove_signal_handler()."""
        loop = MagicMock(spec=['add_signal_handler', 'remove_signal_handler'])
        loop.add_signal_handler = MagicMock()
        loop.remove_signal_handler = MagicMock()
        return loop

    def test_main_behavior(self, loop):
        manager = signal_handled('SIG', 'HANDLER', loop=loop)
        assert not loop.add_signal_handler.call_args_list
        assert not loop.remove_signal_handler.call_args_list
        with manager:
            loop.add_signal_handler.assert_called_once_with('SIG', 'HANDLER')
            assert not loop.remove_signal_handler.call_args_list
        loop.add_signal_handler.assert_called_once_with('SIG', 'HANDLER')
        loop.remove_signal_handler.assert_called_once_with('SIG')

    @patch('sig2srv.asynchelper.get_event_loop', autospec=True)
    def test_with_default_loop(self, get_event_loop, loop):
        get_event_loop.return_value = loop
        manager = signal_handled('SIG', 'HANDLER')
        assert not loop.add_signal_handler.call_args_list
        assert not loop.remove_signal_handler.call_args_list
        with manager:
            loop.add_signal_handler.assert_called_once_with('SIG', 'HANDLER')
            assert not loop.remove_signal_handler.call_args_list
        loop.add_signal_handler.assert_called_once_with('SIG', 'HANDLER')
        loop.remove_signal_handler.assert_called_once_with('SIG')

    def test_handler_is_removed_on_exc(self, loop):
        with pytest.raises(RuntimeError):
            with signal_handled('SIG', 'HANDLER', loop=loop):
                raise RuntimeError("OMG")
        loop.remove_signal_handler.assert_called_once_with('SIG')

    def test_loop_is_keyword_only(self):
        with pytest.raises(TypeError):
            signal_handled('SIG', 'HANDLER', 'LOOP')
