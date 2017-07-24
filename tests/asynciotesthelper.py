"""`asyncio` test helpers."""


class TimeMachine:
    """A monkey-patch helper to advance an event loop's time.

    :param `~asyncio.AbstractEventLoop` event_loop:
        the event loop to monkey-patch.
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
