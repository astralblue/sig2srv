"""Logging for `sig2srv`."""

from logging import getLogger

from ctorrepr import CtorRepr


class BraceMessage(CtorRepr):
    """Brace-style message formatter.

    Taken from the Python logging cookbook.
    """

    def __init__(self, fmt, *poargs, **kwargs):
        """Initialize this instance."""
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
