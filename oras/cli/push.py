__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import os

import oras.client
import oras.utils
from oras.logger import logger


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


def main(args, parser, extra, subparser):
    """
    A wrapper around an oras client push.
    """
    manifest_annotations = load_manifest_annotations(
        args.annotation_file, args.annotation
    )
    client = oras.client.OrasClient(insecure=args.insecure)
    try:
        client.push(
            config_path=args.config,
            disable_path_validation=args.disable_path_validation,
            files=args.filerefs,
            manifest_config=args.manifest_config,
            annotation_file=args.annotation_file,
            manifest_annotations=manifest_annotations,
            username=args.username,
            password=args.password,
            quiet=args.quiet,
            target=args.target,
        )
    except Exception as e:
        logger.exit(str(e))
