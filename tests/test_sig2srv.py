#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Tests for `sig2srv` package."""

from asyncio import get_event_loop
from logging import StreamHandler, DEBUG
from os import kill
from signal import SIGHUP, SIGTERM
from unittest.mock import MagicMock, PropertyMock, call, patch, ANY

from asynciotimemachine import TimeMachine
import pytest

from sig2srv.sig2srv import ServiceCommandRunner


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

    @pytest.mark.asyncio
    async def test_run(self, runner, event_loop):
        proc = MagicMock(spec_set=['wait'])
        async def cse_coro():
            assert runner._ServiceCommandRunner__lock.locked()
            return proc
        status = object()
        async def wait_coro():
            assert runner._ServiceCommandRunner__lock.locked()
            return status
        with patch('sig2srv.sig2srv.create_subprocess_exec',
                   autospec=True, return_value=cse_coro()) as cse, \
             patch.object(proc, 'wait', return_value=wait_coro()) as wait:
            result = await runner.run('foo', 'bar')
            cse.assert_called_once_with('service', self.SERVICE_NAME,
                                        'foo', 'bar',
                                        loop=event_loop)
            wait.assert_called_once_with()
            assert result is status
