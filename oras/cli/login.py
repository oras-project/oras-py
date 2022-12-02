__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import oras.client
from oras.logger import logger


def main(args, parser, extra, subparser):
    """
    Main is a light wrapper around the login command.
    """
    client = oras.client.OrasClient()
    try:
        client.login(
            password=args.password,
            username=args.username,
            config_path=args.config,
            hostname=args.hostname,
            insecure=args.insecure,
            password_stdin=args.password_stdin,
        )
    except Exception as e:
        logger.exit(str(e))
