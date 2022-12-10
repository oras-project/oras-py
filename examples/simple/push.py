#!/usr/bin/env python3


# This shows an example client. You might need to modify the underlying client
# or provider for your use case. See the oras/client.py (client here) and
# oras.provider.py for what is used here (and you might want to customize
# these classes for your needs).

import argparse
import os

import oras.client
import oras.utils
from oras.logger import logger, setup_logger


def load_manifest_annotations(annotation_file, annotations):
    """
    Disambiguate annotations.
    """
    annotations = annotations or []
    if annotation_file and not os.path.exists(annotation_file):
        logger.exit(f"Annotation file {annotation_file} does not exist.")
    if annotation_file:
        lookup = oras.utils.read_json(annotation_file)

        # not allowed to define both, mirroring oras-go
        if "$manifest" in lookup and lookup["$manifest"]:
            raise ValueError(
                "`--annotation` and `--annotation-file` with $manifest cannot be both specified."
            )

    # Finally, parse the list of annotations
    parsed = {}
    for annot in annotations:
        if "=" not in annot:
            logger.exit(
                "Annotation {annot} invalid format, needs to be key=value pair."
            )
        key, value = annot.split("=", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def main(args):
    """
    A wrapper around an oras client push.
    """
    manifest_annotations = load_manifest_annotations(
        args.annotation_file, args.annotation
    )
    client = oras.client.OrasClient(insecure=args.insecure)
    try:
        if args.username and args.password:
            client.set_basic_auth(args.username, args.password)
        client.push(
            config_path=args.config,
            disable_path_validation=args.disable_path_validation,
            files=args.filerefs,
            manifest_config=args.manifest_config,
            annotation_file=args.annotation_file,
            manifest_annotations=manifest_annotations,
            quiet=args.quiet,
            target=args.target,
        )
    except Exception as e:
        logger.exit(str(e))


def get_parser():
    parser = argparse.ArgumentParser(
        description="OCI Registry as Storage Python SDK example push client",
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

    parser.add_argument("--annotation-file", help="manifest annotation file")
    parser.add_argument(
        "--annotation",
        help="single manifest annotation (e.g., key=value)",
        action="append",
    )
    parser.add_argument("--manifest-config", help="manifest config file")
    parser.add_argument(
        "--disable-path-validation",
        help="skip path validation",
        default=False,
        action="store_true",
    )
    parser.add_argument("target", help="target")
    parser.add_argument("filerefs", help="file references", nargs="+")

    # Debug is added on the level of the command
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
