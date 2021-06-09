__author__ = "Vanessa Sochat"
__copyright__ = "Copyright 2021, Vanessa Sochat"
__license__ = "MIT"

from oras.logger import logger
import docker
import sys


def readline():
    """Read lines from stdin"""
    content = sys.stdin.readlines()
    return content[0].strip()


def main(args, parser, extra, subparser):

    client = docker.DockerClient(tls=not args.insecure)

    password = args.password
    username = args.username

    # Read password from stdin
    if args.password_stdin:
        password = readline()

    # No password provided
    elif not args.password:

        # No username, try to get from stdin
        if not username:
            username = input("Username: ")

        # if we still don't have a username, we require a token
        if not username:
            prompt = "Token: "
            password = input("Token: ")
            if not password:
                logger.exit("token required")

        # If we do have a username, we just need a passowrd
        else:
            password = input("Token: ")
            if not password:
                logger.exit("password required")

    else:
        logger.warning(
            "WARNING! Using --password via the CLI is insecure. Use --password-stdin."
        )

    # Login
    # https://docker-py.readthedocs.io/en/stable/client.html?highlight=login#docker.client.DockerClient.login
    result = client.login(
        username=username, password=password, registry=args.hostname[0]
    )
    logger.info(result["Status"])
