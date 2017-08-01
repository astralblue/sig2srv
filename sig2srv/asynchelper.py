"""`asyncio` utilities."""

from asyncio import AbstractEventLoop, coroutine, get_event_loop, iscoroutine
from contextlib import contextmanager

from ctorrepr import CtorRepr

from .logging import WithLog, logger


class WithEventLoop(WithLog, CtorRepr):
    """A simple mixin that takes an optional event loop."""

    __slots__ = ('__loop',)

    def __init__(self, *poargs, loop=None, **kwargs):
        """Initialize this instance.

        :param `AbstractEventLoop` loop: optional event loop.  Avail this loop
            as the `~WithEventLoop.loop` property.
        :raise `AssertionError`: if the given `loop` is not an event loop.
        """
        if loop is None:
            loop = get_event_loop()
        assert isinstance(loop, AbstractEventLoop)
        super().__init__(*poargs, **kwargs)
        self.__loop = loop

    def _collect_repr_args(self, poargs, kwargs):
        super()._collect_repr_args(poargs, kwargs)
        kwargs.update(loop=self.__loop)

    @property
    def loop(self):
        """Event loop given at the creation time, or `None` if not given."""
        return self.__loop


class PeriodicCaller(WithEventLoop, WithLog, CtorRepr):
    """A facility to run a callback periodically.

    :param `~collections.abc.Callable` cb: what to call periodically.
    :param `float` period: how often `cb` should be called, in seconds.
    :param `bool` bg: whether to call `cb` in background if it is a
        coroutine function (see class description).
    :param `~collections.abc.Callable` on_ret: an optional callable to call
        with the return value from the callback (see class description).
    :param `~collections.abc.Callable` on_exc: an optional callable to call
        with any exception raised by the callback (see class description).
    :param `AbstractEventLoop` loop: optional event loop in which to
        schedule periodic timers and calls.

    With a period *P* and start time *S* schedule each call at *S*, *S* + *P*,
    *S* + 2 * *P*, *S* + 3 * *P* and so on.  (The start time *S* is given as
    the *at* argument to the `start()` method.)

    Schedule calls even if their start time is in the past.  Typical event
    loops will schedule such calls for immediate execution.

    Call the callback with the scheduled start timestamp for the call.

    If the callback returns a coroutine object (such as when the callback is an
    ``async def``-ined coroutine function), it can be run in foreground or in
    background.  If foreground, schedule the next call after first awaiting the
    returned coroutine object (and use the return values and/or exceptions from
    it for return value/exception processing as noted below).  If background,
    schedule the next call immediately after creating a task for the returned
    coroutine object instead of awaiting.

    Call a coroutine function in foreground – that is, wait for its return
    value and/or exception, except if *bg* `bool`-converts to `True`, call it
    in background.  If *bg* is also a callable, call it with each background
    task created, e.g. so as to reap the return value and/or exception from the
    task.

    Ignore return values and exceptions, except if the callback is not a
    background coroutine and *on_ret* and/or *on_exc* callbacks are given, call
    them with the return value and/or the exception caught respectively.  A
    common trick is a closure that stops the periodic call loop on exception::

        pc = PeriodicCaller(callback, 60, on_exc=lambda e: pc.stop())

    Ignore *on_ret* and *on_exc* for background callbacks.  Return values and
    exceptions from background callbacks can be collected by a callable *bg* as
    noted above.

    Ignore exceptions raised by the *on_ret*, *on_exc*, and *bg* callbacks
    themselves.
    """

    def __init__(self, cb, period, *poargs,
                 bg=False, on_ret=None, on_exc=None, **kwargs):
        """Initialize this instance."""
        assert callable(cb)
        assert on_ret is None or callable(on_ret)
        assert on_exc is None or callable(on_exc)
        super().__init__(*poargs, **kwargs)
        self.__cb = cb
        self.__period = float(period)
        self.__bg = bg if callable(bg) else bool(bg)
        self.__on_ret = on_ret
        self.__on_exc = on_exc
        self.__next = None
        self.__pending = None

    def _collect_repr_args(self, poargs, kwargs):
        super()._collect_repr_args(poargs, kwargs)
        poargs[:0] = self.__cb, self.__period
        kwargs.update(bg=self.__bg, on_ret=self.__on_ret, on_exc=self.__on_exc)

    def start(self, at=None):
        """Start periodic calls.

        Do nothing if periodic calls have already been started.

        :param `float` at: timestamp at which to start the first call, using
            the same time reference as `AbstractEventLoop.time()`.  If not
            given or `None`, start the first call after a full period from now.
        """
        if self.__next is not None:
            self._debug("already started")
            return
        if at is None:
            self.__next = self.loop.time() + self.__period
        else:
            self.__next = at
        self._debug("next call at {!r}", self.__next)
        self.__pending = self.loop.call_at(self.__next, self.__handle_expire)

    def stop(self):
        """Stop the ongoing periodic calls.

        Do nothing if periodic calls have not been started.
        """
        if self.__next is None:
            self._debug("already stopped")
            return
        self.__pending.cancel()
        self.__pending = None
        self.__next = None
        self._debug("stopped")

    def __handle_expire(self):
        # Do not use asyncio.iscoroutinefunction() to test self.__cb itself,
        # because it fails to catch ones with partial()-ly bound arguments.
        self._debug("called at {!r}", self.__next)
        try:
            r = self.__cb(self.__next)
        except Exception as e:
            self._debug("callback raised {!r}", e)
            self.__handle_exc(e)
            self.__schedule_next()
        else:
            if not iscoroutine(r):
                self._debug("callback was synchronous")
                self.__handle_ret(r)
                self.__schedule_next()
            elif self.__bg:
                task = self.loop.create_task(r)
                self._debug("scheduled background task {!r}", task)
                try:
                    self.__bg(task)  # catches `True`-not-callable errors too
                except Exception:
                    pass
                self.__schedule_next()
            else:
                task = self.loop.create_task(self.__await_coroutine(r))
                self.__pending = task
                self._debug("scheduled foreground task {!r}", task)

    @coroutine
    def __await_coroutine(self, coro):
        self._debug("awaiting foreground coroutine {!r}", coro)
        try:
            r = yield from coro
        except Exception as e:
            self._debug("{!r} raised {!r}", coro, e)
            self.__handle_exc(e)
        else:
            self._debug("{!r} returned {!r}", coro, r)
            self.__handle_ret(r)
        self.__schedule_next()

    def __handle_ret(self, r):
        try:
            self.__on_ret(r)
        except Exception:  # catches None-not-callable errors too
            pass

    def __handle_exc(self, e):
        try:
            self.__on_exc(e)
        except Exception:  # catches None-not-callable errors too
            pass

    def __schedule_next(self):
        if self.__next is None:
            # self was stopped from within callback
            return
        self.__next += self.__period
        self.__pending = self.loop.call_at(self.__next, self.__handle_expire)
        self._debug("next call at {!r}", self.__next)


@contextmanager
def periodic_calls(*poargs, at=None, **kwargs):
    """Run the ``with`` statement block with periodic calls to a callback.

    All arguments except for *at* is forwarded to the constructor of
    `PeriodicCaller`.  The *at* argument is forwarded to the
    `PeriodicCaller.start()` method.
    """
    caller = PeriodicCaller(*poargs, **kwargs)
    caller.start(at=at)
    try:
        yield caller
    finally:
        caller.stop()


@contextmanager
def signal_handled(signum, handler, *, loop=None):
    """Install/uninstall a signal handler in the `specs` upon enter/exit.

    :param signum: signal to catch.
    :param handler: signal handler.
    :param loop: `asyncio` loop in which to install the handler.

    Example:

    >>> from signal import SIGCONT
    >>> from asyncio import sleep, get_event_loop
    >>> import os
    >>> def handle_sigcont():
    ...     print("SIGCONT received")
    >>> async def signal_handled_test(loop=None):
    ...     with signal_handled(SIGCONT, handle_sigcont, loop):
    ...         print("delivering SIGCONT to self while handling SIGCONT")
    ...         os.kill(os.getpid(), SIGCONT)
    ...         print("sleeping to yield to SIGCONT handler")
    ...         await sleep(0.01)
    ...     print("delivering SIGCONT to self while not handling SIGCONT")
    ...     os.kill(os.getpid(), SIGCONT)
    ...     print("sleeping again (but this time SIGCONT won't be handled)")
    ...     await sleep(0.01)
    ...     print("finishing")
    >>> loop = get_event_loop()
    >>> loop.run_until_complete(signal_handled_test(loop=loop))
    delivering SIGCONT to self while handling SIGCONT
    sleeping to yield to SIGCONT handler
    SIGCONT received
    delivering SIGCONT to self while not handling SIGCONT
    sleeping again (but this time SIGCONT won't be handled)
    finishing
    """
    if loop is None:
        loop = get_event_loop()
    logger.debug("signal %r -> handler %r: adding", signum, handler)
    loop.add_signal_handler(signum, handler)
    logger.debug("signal %r -> handler %r: added", signum, handler)
    try:
        yield
    finally:
        logger.debug("signal %r -> handler %r: removing", signum, handler)
        loop.remove_signal_handler(signum)
        logger.debug("signal %r -> handler %r: removed", signum, handler)
