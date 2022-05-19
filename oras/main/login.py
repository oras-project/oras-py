__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import sys
from typing import Optional

import oras.utils
from oras.logger import logger


def login(
    username: Optional[str] = None,
    password: Optional[str] = None,
    password_stdin: bool = False,
    insecure: bool = False,
    hostname: Optional[str] = None,
    config_path: Optional[str] = None,
):
    """
    Login to an OCI registry.

    The username and password can come from stdin.
    """
    client = oras.utils.get_docker_client(tls=not insecure)

    # Read password from stdin
    if password_stdin:
        password = readline()

    # No password provided
    elif not password:

        # No username, try to get from stdin
        if not username:
            username = input("Username: ")

        # if we still don't have a username, we require a token
        if not username:
            password = input("Token: ")
            if not password:
                logger.exit("token required")

        # If we do have a username, we just need a passowrd
        else:
            password = input("Password: ")
            if not password:
                logger.exit("password required")

    else:
        logger.warning(
            "WARNING! Using --password via the CLI is insecure. Use --password-stdin."
        )

    # Login
    # https://docker-py.readthedocs.io/en/stable/client.html?highlight=login#docker.client.DockerClient.login
    result = client.login(
        username=username,
        password=password,
        registry=hostname,
        dockercfg_path=config_path,
    )
    logger.info(result["Status"])


def readline() -> str:
    """
    Read lines from stdin
    """
    content = sys.stdin.readlines()
    return content[0].strip()
