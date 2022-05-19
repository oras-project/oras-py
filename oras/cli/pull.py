__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import oras.client


def main(args, parser, extra, subparser):
    """
    A wrapper around an oras client pull.
    """
    client = oras.client.OrasClient(insecure=args.insecure)
    client.pull(
        config_path=args.config,
        allowed_media_type=args.allowed_media_type
        if not args.allow_all_media_types
        else [],
        overwrite=not args.keep_old_files,
        manifest_config_ref=args.manifest_config_ref,
        outdir=args.output,
        password=args.password,
        username=args.username,
        target=args.target,
    )
