#!/usr/bin/env python3

# This shows an example client. You might need to modify the underlying client
# or provider for your use case. See the oras/client.py (client here) and
# oras.provider.py for what is used here (and you might want to customize
# these classes for your needs).

import argparse

import oras.client
from oras.logger import logger, setup_logger


def get_parser():
    parser = argparse.ArgumentParser(
        description="OCI Python SDK Example Login",
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
        "--password-stdin",
        dest="password_stdin",
        help="read password or identity token from stdin",
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


def main(args):
    """
    This is an example of running login, and catching errors.

    We handle login by doing the following:

    1. We default to the login function of the basic client. If a custom
       provider is initiated with the client, we use it instead (self.remote.logic)
    2. For the default, we ask for password / username if they are not provided.
    3. We cut out early if password and username are not defined.
    4. If defined, we set basic auth using them (so the client is ready)
    5. We first try using the docker-py login.
    6. If it fails we fall back to custom setting of credentials.
    """
    client = oras.client.OrasClient(insecure=args.insecure)
    print(client.version())

    # Other ways to handle login:
    # client.set_basic_auth(username, password)
    # client.set_token_auth(token)

    try:
        result = client.login(
            password=args.password,
            username=args.username,
            config_path=args.config,
            hostname=args.hostname,
            password_stdin=args.password_stdin,
        )
        logger.info(result)
    except Exception as e:
        logger.exit(str(e))


if __name__ == "__main__":
    parser = get_parser()
    args, _ = parser.parse_known_args()
    setup_logger(quiet=args.quiet, debug=args.debug)
    main(args)
