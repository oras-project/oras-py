#!/usr/bin/env python3


# This shows an example client. You might need to modify the underlying client
# or provider for your use case. See the oras/client.py (client here) and
# oras.provider.py for what is used here (and you might want to customize
# these classes for your needs).

import argparse
import os

import oras.client
from oras.logger import logger, setup_logger


def main(args):
    """
    A wrapper around an oras client pull.
    """
    client = oras.client.OrasClient(insecure=args.insecure)
    print(client.version())
    try:
        client.pull(
            config_path=args.config,
            allowed_media_type=(
                args.allowed_media_type if not args.allow_all_media_types else []
            ),
            overwrite=not args.keep_old_files,
            outdir=args.output,
            target=args.target,
        )
    except Exception as e:
        logger.exit(str(e))


def get_parser():
    parser = argparse.ArgumentParser(
        description="OCI Registry as Storage Python SDK example pull client",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser.add_argument(
        "--quiet",
        dest="quiet",
        help="suppress additional output.",
        default=False,
        action="store_true",
    )

    parser.add_argument(
        "--version",
        dest="version",
        help="Show the oras version information.",
        default=False,
        action="store_true",
    )

    parser.add_argument(
        "--allowed-media-type", help="add an allowed media type.", action="append"
    )
    parser.add_argument(
        "--allow-all-media-types",
        help="allow all media types",
        default=False,
        action="store_true",
    )
    parser.add_argument(
        "-k",
        "--keep-old-files",
        help="do not overwrite existing files.",
        default=False,
        action="store_true",
    )
    parser.add_argument("--output", help="output directory.", default=os.getcwd())
    parser.add_argument("target", help="target")
    parser.add_argument(
        "--debug",
        dest="debug",
        help="debug mode",
        default=False,
        action="store_true",
    )

    parser.add_argument(
        "-c",
        "--config",
        dest="config",
        help="auth config path",
        action="append",
    )

    parser.add_argument("-u", "--username", dest="username", help="registry username")
    parser.add_argument(
        "-p",
        "--password",
        dest="password",
        help="registry password or identity token",
    )
    parser.add_argument(
        "-i",
        "--insecure",
        dest="insecure",
        help="allow connections to SSL registry without certs",
        default=False,
        action="store_true",
    )

    return parser


if __name__ == "__main__":
    parser = get_parser()
    args, _ = parser.parse_known_args()
    setup_logger(quiet=args.quiet, debug=args.debug)
    main(args)
