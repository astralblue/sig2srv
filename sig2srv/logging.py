"""Logging for `sig2srv`."""

from logging import getLogger, DEBUG, INFO, WARNING, ERROR, CRITICAL
from traceback import extract_stack

from ctorrepr import CtorRepr


class BraceMessage(CtorRepr):
    """Brace-style message formatter.

    Taken from the Python logging cookbook.
    """

    def __init__(self, fmt, *poargs, **kwargs):
        """Initialize this instance."""
        super().__init__()
        self.fmt = fmt
        self.poargs = poargs
        self.kwargs = kwargs

    def _collect_repr_args(self, poargs, kwargs):
        super()._collect_repr_args(poargs, kwargs)
        poargs[:0] = (self.fmt,) + self.poargs
        kwargs.update(kwargs)

    def __str__(self):
        """Lazy-format the given logging arguments into the format string."""
        return self.fmt.format(*self.poargs, **self.kwargs)


logger = getLogger(__name__)
"""The `sig2srv` logger."""

__ = BraceMessage
"""Convenience alias for `BraceMessage`."""


class WithLog(CtorRepr):
    """Logging mixin."""

    def __init__(self, *poargs, logger=None, **kwargs):
        """Initialize this instance."""
        super().__init__(*poargs, **kwargs)
        if logger is None:
            logger = globals()['logger']
        self.__logger = logger

    def _collect_repr_args(self, poargs, kwargs):
        super()._collect_repr_args(poargs, kwargs)
        kwargs.update(logger=self.__logger)

    @property
    def logger(self):
        """Return the logger to which this instance will log."""
        return self.__logger

    def _log(self, level, fmt, *poargs, log_depth=0, **kwargs):
        caller = extract_stack()[-2 - log_depth][2]
        header = ("{!r}.{}(): "
                  .format(self, caller)
                  .translate({ord('{'): '{{', ord('}'): '}}'}))
        self.__logger.log(level, BraceMessage(header + fmt, *poargs, **kwargs))

    def _debug(self, fmt, *poargs, log_depth=0, **kwargs):
        self._log(DEBUG, fmt, *poargs, log_depth=(log_depth + 1), **kwargs)

    def _info(self, fmt, *poargs, log_depth=0, **kwargs):
        self._log(INFO, fmt, *poargs, log_depth=(log_depth + 1), **kwargs)

    def _warning(self, fmt, *poargs, log_depth=0, **kwargs):
        self._log(WARNING, fmt, *poargs, log_depth=(log_depth + 1), **kwargs)

    def _error(self, fmt, *poargs, log_depth=0, **kwargs):
        self._log(ERROR, fmt, *poargs, log_depth=(log_depth + 1), **kwargs)

    def _critical(self, fmt, *poargs, log_depth=0, **kwargs):
        self._log(CRITICAL, fmt, *poargs, log_depth=(log_depth + 1), **kwargs)
