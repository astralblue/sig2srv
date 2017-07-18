# -*- coding: utf-8 -*-

"""Main module."""

from asyncio import Event, Lock, create_subprocess_exec
from enum import Enum
from signal import SIGTERM, SIGHUP

from .logging import logger, __
from .asynchelper import periodic_calls, WithEventLoop, signal_handled


class FatalError(RuntimeError):
    """Fatal errors that abort the execution of the main routine."""


class Sig2Srv(WithEventLoop):
    """Signal-to-service bridge."""

    class State(Enum):
        """`Sig2Srv` state."""

        STOPPED = 0
        STARTING = 1
        RUNNING = 2
        STOPPING = 3
        UNKNOWN = 4

    def __init__(self, *poargs, service, **kwargs):
        """Initialize this instance."""
        logger.debug(__("initializing {!r}", self))
        super().__init__(*poargs, **kwargs)
        self.__service = service
        self.__service_lock = Lock()
        self.__finished = Event()
        self.__state = self.State.STOPPED

    @property
    def __state(self):
        return self.__state_

    @__state.setter
    def __state(self, new_state):
        logger.debug(__("new state is {}", new_state))
        self.__state_ = new_state

    def __signal_handled(self, *poargs, **kwargs):
        return signal_handled(*poargs, loop=self.loop, **kwargs)

    def __fatal(self, *poargs, **kwargs):
        self.__finished.set()
        try:
            raise FatalError(*poargs, **kwargs)
        except FatalError as e:
            self.__fatal_error = e
            raise

    async def run(self):
        """Run the state machine."""
        assert self.__state == self.State.STOPPED
        with self.__signal_handled(SIGTERM, self.__handle_stop_signal), \
             self.__signal_handled(SIGHUP, self.__handle_restart_signal), \
             periodic_calls(self.__check_status, 5):
            self.__state = self.State.STARTING
            result = await self.__service_command('start')
            if result != 0:
                self.__state = self.State.STOPPED
                raise FatalError("failed to start service")
            self.__state = self.State.RUNNING
            self.__fatal_error = None
            self.__finished.clear()
            logger.debug("awaiting finish")
            await self.__finished.wait()
            logger.debug("finished")
        if self.__fatal_error is not None:
            raise self.__fatal_error
        assert self.__state == self.State.STOPPED

    async def __check_status(self):
        result = await self.__service_command('status')
        if result != 0 and self.__state == self.State.RUNNING:
            self.__fatal("service stopped unexpectedly")

    def __handle_stop_signal(self):
        self.loop.create_task(self.__stop())

    async def __stop(self):
        if self.__state != self.State.RUNNING:
            logger.debug("loop not running, doing nothing")
            return
        result = await self.__service_command('stop')
        if result != 0:
            self.__state = self.State.UNKNOWN
            self.__fatal("failed to stop service while stopping")
        self.__state = self.State.STOPPED
        self.__finished.set()

    def __handle_restart_signal(self):
        self.loop.create_task(self.__restart())

    async def __restart(self):
        if self.__state != self.State.RUNNING:
            logger.debug("loop not running, doing nothing")
            return
        self.__state = self.State.STOPPING
        result = await self.__service_command('stop')
        if result != 0:
            self.__state = self.State.UNKNOWN
            self.__fatal("failed to stop service while restarting")
        self.__state = self.State.STARTING
        result = await self.__service_command('start')
        if result != 0:
            self.__state = self.State.STOPPED
            self.__fatal("failed to start service while restarting")
        self.__state = self.State.RUNNING

    async def __service_command(self, *args):
        async with self.__service_lock:
            args = ('service', self.__service) + args
            logger.debug(__("running {}", args))
            proc = await create_subprocess_exec(*args, loop=self.loop)
            result = await proc.wait()
            logger.debug(__("{} returned {}", args, result))
            return result
