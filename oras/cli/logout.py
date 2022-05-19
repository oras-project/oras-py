__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import oras.client


def main(args, parser, extra, subparser):
    """
    Main is a light wrapper around the logout command.
    """
    client = oras.client.OrasClient()
    client.logout(args.hostname)
