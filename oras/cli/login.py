__author__ = "Vanessa Sochat"
__copyright__ = "Copyright 2021-2022, Vanessa Sochat"
__license__ = "MIT"

import oras.client


def main(args, parser, extra, subparser):
    """
    Main is a light wrapper around the login command.
    """
    client = oras.client.OrasClient()
    client.login(
        args.password,
        args.username,
        config_path=args.config,
        hostname=args.hostname,
        insecure=args.insecure,
        password_stdin=args.password_stdin,
    )
