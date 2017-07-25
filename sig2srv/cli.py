"""Main CLI module."""

from argparse import ArgumentParser
from asyncio import get_event_loop
from contextlib import closing
from logging import StreamHandler, DEBUG
import sys

from .logging import logger
from .sig2srv import Sig2Srv, ServiceCommandRunner, FatalError


def main():
    """Run one `Sig2Srv` instance as a command-line utility."""
    parser = ArgumentParser(description="Start/stop service(8) script.")
    parser.add_argument('--debug', action='store_const', const=True,
                        help="enable debug logging")
    parser.add_argument('service', help="service name")
    parser.set_defaults(debug=False)
    args = parser.parse_args()
    handler = StreamHandler()
    logger.addHandler(handler)
    if args.debug:
        logger.setLevel(DEBUG)
    with closing(get_event_loop()) as loop:
        runner = ServiceCommandRunner(name=args.service, loop=loop)
        sig2srv = Sig2Srv(runner=runner, loop=loop)
        try:
            loop.run_until_complete(sig2srv.run())
        except FatalError as e:
            print("error:", str(e), file=sys.stderr)
            sys.exit(1)


if __name__ == '__main__':
    main()
