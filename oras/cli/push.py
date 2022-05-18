__author__ = "Vanessa Sochat"
__copyright__ = "Copyright 2021-2022, Vanessa Sochat"
__license__ = "MIT"

import oras.client


def main(args, parser, extra, subparser):
    """
    A wrapper around an oras client push.
    """
    client = oras.client.OrasClient(insecure=args.insecure)
    client.push(
        config_path=args.config,
        disable_path_validation=args.disable_path_validation,
        files=args.filerefs,
        manifest_config=args.manifest_config,
        username=args.username,
        password=args.password,
        quiet=args.quiet,
        target=args.target,
    )
