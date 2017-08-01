#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Tests for `sig2srv` package."""

from asyncio import coroutine, get_event_loop
from logging import StreamHandler, DEBUG
from os import getpid, kill
from signal import SIGHUP, SIGTERM
from unittest.mock import MagicMock, PropertyMock, call, patch, ANY

from asynciotimemachine import TimeMachine
import pytest

from sig2srv.sig2srv import ServiceCommandRunner, Sig2Srv, FatalError
from tests.eventloopfixture import event_loop

from sig2srv.logging import logger
logger.setLevel(DEBUG)
logger.addHandler(StreamHandler())


class TestServiceCommandRunner:

    SERVICE_NAME = 'omg'

    @pytest.fixture
    def runner(self, event_loop):
        return ServiceCommandRunner(name=self.SERVICE_NAME, loop=event_loop)

    def test_init_takes_and_avails_name(self, runner):
        assert runner.name == self.SERVICE_NAME

    def test_name_is_readonly(self, runner):
        with pytest.raises(AttributeError):
            runner.name = 'wtf'
            del runner.name

    def test_init_takes_and_avails_loop(self, runner, event_loop):
        assert runner.loop is event_loop

    def test_loop_is_readonly(self, runner, event_loop):
        with pytest.raises(AttributeError):
            runner.loop = event_loop
            del runner.loop

    def test_run(self, runner, event_loop):
        proc = MagicMock(spec_set=['wait'])
        @coroutine
        def cse_coro():
            assert runner._ServiceCommandRunner__lock.locked()
            return proc
        status = object()
        @coroutine
        def wait_coro():
            assert runner._ServiceCommandRunner__lock.locked()
            return status
        with patch('sig2srv.sig2srv.create_subprocess_exec',
                   autospec=True, return_value=cse_coro()) as cse, \
             patch.object(proc, 'wait', return_value=wait_coro()) as wait:
            result = event_loop.run_until_complete(runner.run('foo', 'bar'))
            cse.assert_called_once_with('service', self.SERVICE_NAME,
                                        'foo', 'bar',
                                        loop=event_loop)
            wait.assert_called_once_with()
            assert result is status

    def test_lock_is_in_the_same_loop(self, runner, event_loop):
        assert runner._ServiceCommandRunner__lock._loop is event_loop


@pytest.mark.timeout(5)
class TestSig2Srv:

    SERVICE_NAME = 'omg'

    @pytest.fixture
    def runner(self, event_loop):
        runner = MagicMock(name='runner', spec=ServiceCommandRunner)
        type(runner).name = PropertyMock(name='name',
                                         return_value=self.SERVICE_NAME)
        type(runner).loop = PropertyMock(name='event_loop',
                                         return_value=event_loop)
        runner.run = MagicMock(name='run')
        return runner

    def test_init_takes_and_avails_runner(self, runner):
        assert Sig2Srv(runner=runner).runner is runner

    def test_init_requires_kwarg_runner(self, runner):
        with pytest.raises(TypeError):
            Sig2Srv()

    @pytest.fixture
    def sig2srv(self, runner):
        return Sig2Srv(runner=runner)

    def test_start_failure_aborts_run(self, sig2srv, event_loop):
        @coroutine
        def run(verb, *args):
            return 1 if verb == 'start' else 0
        sig2srv.runner.run.side_effect = run
        with pytest.raises(FatalError):
            event_loop.run_until_complete(sig2srv.run())
        assert sig2srv.runner.run.call_args_list == [call('start')]

    def test_run_installs_sigterm_sighup_handlers(self, sig2srv, event_loop):
        with patch.object(sig2srv.runner.loop, 'add_signal_handler') as ash, \
             patch.object(sig2srv.runner.loop, 'remove_signal_handler') as rsh:
            @coroutine
            def run(verb, *args):
                assert sorted(ash.call_args_list) == sorted([
                        call(SIGHUP, ANY),
                        call(SIGTERM, ANY),
                ])
                ash.reset_mock()
                assert not rsh.call_args_list
                return 1
            sig2srv.runner.run.side_effect = run
            with pytest.raises(FatalError):
                event_loop.run_until_complete(sig2srv.run())
            assert not ash.call_args_list
            assert sorted(rsh.call_args_list) == sorted([
                    call(SIGHUP),
                    call(SIGTERM),
            ])

    def test_status_failure_aborts_run(self, sig2srv, event_loop):
        tm = TimeMachine(event_loop=sig2srv.runner.loop)
        remaining = 1
        @coroutine
        def run(verb, *args):
            nonlocal remaining
            tm.advance_by(5)
            if verb == 'status':
                if not remaining:
                    return 1
                remaining -= 1
            return 0
        sig2srv.runner.run.side_effect = run
        with pytest.raises(FatalError):
            event_loop.run_until_complete(sig2srv.run())
        assert sig2srv.runner.run.call_args_list == [
                call('start'),
                call('status'),
                call('status'),
        ]

    def test_sigterm_stops_run(self, sig2srv, event_loop):
        signaled = False
        @coroutine
        def run(verb, *args):
            nonlocal signaled
            if not signaled:
                kill(getpid(), SIGTERM)
                signaled = True
            return 0
        sig2srv.runner.run.side_effect = run
        event_loop.run_until_complete(sig2srv.run())
        assert sig2srv.runner.run.call_args_list == [
                call('start'),
                call('stop'),
        ]

    def test_state_transitions(self, sig2srv, event_loop):
        started = False
        tm = TimeMachine(event_loop=sig2srv.runner.loop)
        @coroutine
        def run(verb, *args):
            if verb == 'start':
                assert sig2srv.state is Sig2Srv.State.STARTING
                tm.advance_by(5)
            elif verb == 'status':
                assert sig2srv.state is Sig2Srv.State.RUNNING
                kill(getpid(), SIGTERM)
            elif verb == 'stop':
                assert sig2srv.state is Sig2Srv.State.STOPPING
            return 0
        sig2srv.runner.run.side_effect = run
        event_loop.run_until_complete(sig2srv.run())
        assert sig2srv.runner.run.call_args_list == [
                call('start'),
                call('status'),
                call('stop'),
        ]

    def test_sighup_restarts_run(self, sig2srv, event_loop):
        restarted = False
        stopped = False
        @coroutine
        def run(verb, *args):
            nonlocal restarted, stopped
            if verb == 'start':
                assert sig2srv.state is Sig2Srv.State.STARTING
                if not restarted:
                    kill(getpid(), SIGHUP)
                    restarted = True
                elif not stopped:
                    kill(getpid(), SIGTERM)
                    stopped = True
            elif verb == 'stop':
                assert sig2srv.state is Sig2Srv.State.STOPPING
            return 0
        sig2srv.runner.run.side_effect = run
        event_loop.run_until_complete(sig2srv.run())
        assert sig2srv.runner.run.call_args_list == [
                call('start'),
                call('stop'),
                call('start'),
                call('stop'),
        ]

    def test_stop_failure_aborts_run(self, sig2srv, event_loop):
        @coroutine
        def run(verb, *args):
            if verb == 'start':
                kill(getpid(), SIGTERM)
            return 1 if verb == 'stop' else 0
        sig2srv.runner.run.side_effect = run
        with pytest.raises(FatalError):
            event_loop.run_until_complete(sig2srv.run())
        assert sig2srv.runner.run.call_args_list == [
                call('start'),
                call('stop'),
        ]

    def test_stop_failure_aborts_run_while_restarting(self, sig2srv,
                                                      event_loop):
        @coroutine
        def run(verb, *args):
            if verb == 'start':
                kill(getpid(), SIGHUP)
            return 1 if verb == 'stop' else 0
        sig2srv.runner.run.side_effect = run
        with pytest.raises(FatalError):
            event_loop.run_until_complete(sig2srv.run())
        assert sig2srv.runner.run.call_args_list == [
                call('start'),
                call('stop'),
        ]

    def test_start_failure_aborts_run_while_restarting(self, sig2srv,
                                                       event_loop):
        started = False
        @coroutine
        def run(verb, *args):
            nonlocal started
            if verb == 'start':
                if not started:
                    kill(getpid(), SIGHUP)
                    started = True
                else:
                    return 1
            return 0
        sig2srv.runner.run.side_effect = run
        with pytest.raises(FatalError):
            event_loop.run_until_complete(sig2srv.run())
        assert sig2srv.runner.run.call_args_list == [
                call('start'),
                call('stop'),
                call('start'),
        ]

    def test_finished_event_is_in_the_same_loop(self, sig2srv, event_loop):
        assert sig2srv._Sig2Srv__finished._loop is event_loop
