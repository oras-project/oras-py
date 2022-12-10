#!/usr/bin/env python3

# This shows an example client. You might need to modify the underlying client
# or provider for your use case. See the oras/client.py (client here) and
# oras.provider.py for what is used here (and you might want to customize
# these classes for your needs).

import argparse

import oras.client
from oras.logger import setup_logger


def main(args):
    """
    Main is a light wrapper around the logout command.
    """
    client = oras.client.OrasClient()
    print(client.version())
    client.logout(args.hostname)


def get_parser():
    parser = argparse.ArgumentParser(
        description="OCI Python SDK Example Logout",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser.add_argument(
        "--quiet",
        dest="quiet",
        help="suppress additional output.",
        default=False,
        action="store_true",
    )

    # Login and logout share config and hostname arguments
    parser.add_argument("hostname", help="hostname")
    parser.add_argument(
        "--debug",
        dest="debug",
        help="debug mode",
        default=False,
        action="store_true",
    )
    return parser


if __name__ == "__main__":
    parser = get_parser()
    args, _ = parser.parse_known_args()
    setup_logger(quiet=args.quiet, debug=args.debug)
    main(args)
