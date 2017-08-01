# -*- coding: utf-8 -*-

"""Main module."""

from asyncio import Event, Lock, coroutine, create_subprocess_exec
from contextlib import ExitStack
from enum import Enum
from signal import SIGTERM, SIGHUP

from ctorrepr import CtorRepr

from .logging import WithLog
from .asynchelper import periodic_calls, WithEventLoop, signal_handled


class ServiceCommandRunner(WithEventLoop, WithLog, CtorRepr):
    """Serialized service(8) command runner.

    :param `str` name: service name, such as ``apache``.
    """

    def __init__(self, *poargs, name, **kwargs):
        """Initialize this instance."""
        super().__init__(*poargs, **kwargs)
        self.__name = name
        self.__lock = Lock(loop=self.loop)

    def _collect_repr_args(self, poargs, kwargs):
        super()._collect_repr_args(poargs, kwargs)
        kwargs.update(name=self.__name)

    @property
    def name(self):
        """Return the service name."""
        return self.__name

    @coroutine
    def run(self, *args):
        """Run ``service <name> <args>``.

        Do not permit concurrent runs: If another one is already running, wait
        for it to finish.

        :param args: arguments to put after ``service <name>``.
            Its first element should be a service(8) verb such as ``start``.
        :return: the exit status of the given command.
        """
        yield from self.__lock.acquire()
        try:
            args = ('service', self.__name) + args
            self._debug("running {}", args)
            proc = yield from create_subprocess_exec(*args, loop=self.loop)
            result = yield from proc.wait()
            self._debug("{} returned {}", args, result)
            return result
        finally:
            self.__lock.release()


class FatalError(RuntimeError):
    """Fatal errors that abort the execution of the main routine."""


class Sig2Srv(WithLog, CtorRepr):
    """Signal-to-service bridge.

    :param `ServiceCommandRunner` runner: service command runner.
    """

    class State(Enum):
        """`Sig2Srv` state."""

        STOPPED = 0
        STARTING = 1
        RUNNING = 2
        STOPPING = 3
        UNKNOWN = 4

    def __init__(self, *poargs, runner, **kwargs):
        """Initialize this instance."""
        super().__init__(*poargs, **kwargs)
        self.__runner = runner
        self.__finished = Event(loop=runner.loop)
        self.__state = self.State.STOPPED

    def _collect_repr_args(self, poargs, kwargs):
        super()._collect_repr_args(poargs, kwargs)
        kwargs.update(runner=self.__runner)

    @property
    def state(self):
        """Return the state of this bridge.

        The value is one of the `Sig2Srv.State` enums.
        """
        return self.__state

    @property
    def runner(self):
        """Return the `ServiceCommandRunner` for this instance."""
        return self.__runner

    @property
    def __state(self):
        return self.__state_

    @__state.setter
    def __state(self, new_state):
        self._debug("new state is {}", new_state)
        self.__state_ = new_state

    def __signal_handled(self, *poargs, **kwargs):
        return signal_handled(*poargs, loop=self.__runner.loop, **kwargs)

    def __fatal(self, *poargs, **kwargs):
        self.__finished.set()
        try:
            raise FatalError(*poargs, **kwargs)
        except FatalError as e:
            self.__fatal_error = e
            raise

    @coroutine
    def run(self):
        """Run the state machine."""
        assert self.__state == self.State.STOPPED
        with ExitStack() as stack:
            sec = stack.enter_context
            sec(self.__signal_handled(SIGTERM, self.__handle_stop_signal))
            sec(self.__signal_handled(SIGHUP, self.__handle_restart_signal))
            sec(periodic_calls(self.__check_status, 5,
                               loop=self.__runner.loop))
            self.__state = self.State.STARTING
            result = yield from self.__runner.run('start')
            if result != 0:
                self.__state = self.State.STOPPED
                raise FatalError("failed to start service")
            self.__state = self.State.RUNNING
            self.__fatal_error = None
            self.__finished.clear()
            self._debug("awaiting finish")
            yield from self.__finished.wait()
            self._debug("finished")
        if self.__fatal_error is not None:
            raise self.__fatal_error
        assert self.__state == self.State.STOPPED

    @coroutine
    def __check_status(self, timestamp):
        result = yield from self.__runner.run('status')
        if result != 0 and self.__state == self.State.RUNNING:
            self.__fatal("service stopped unexpectedly")

    def __handle_stop_signal(self):
        self.__runner.loop.create_task(self.__stop())

    @coroutine
    def __stop(self):
        if self.__state != self.State.RUNNING:
            self._debug("loop not running, doing nothing")
            return
        self.__state = self.State.STOPPING
        result = yield from self.__runner.run('stop')
        if result != 0:
            self.__state = self.State.UNKNOWN
            self.__fatal("failed to stop service while stopping")
        self.__state = self.State.STOPPED
        self.__finished.set()

    def __handle_restart_signal(self):
        self.__runner.loop.create_task(self.__restart())

    @coroutine
    def __restart(self):
        if self.__state != self.State.RUNNING:
            self._debug("loop not running, doing nothing")
            return
        self.__state = self.State.STOPPING
        result = yield from self.__runner.run('stop')
        if result != 0:
            self.__state = self.State.UNKNOWN
            self.__fatal("failed to stop service while restarting")
        self.__state = self.State.STARTING
        result = yield from self.__runner.run('start')
        if result != 0:
            self.__state = self.State.STOPPED
            self.__fatal("failed to start service while restarting")
        self.__state = self.State.RUNNING
