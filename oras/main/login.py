__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import os
import sys
from typing import Optional

import oras.auth
import oras.utils
from oras.logger import logger


class DockerClient:
    """
    If running inside a container (or similar without docker) do a manual login
    """

    def login(
        self,
        username: str,
        password: str,
        registry: str,
        dockercfg_path: Optional[str] = None,
    ) -> dict:
        """
        Manual login means loading and checking the config file

        :param registry: if provided, use this custom provider instead of default
        :type registry: oras.provider.Registry or None
        :param username: the user account name
        :type username: str
        :param password: the user account password
        :type password: str
        :param dockercfg_str: docker config path
        :type dockercfg_str: list
        """
        if not dockercfg_path:
            dockercfg_path = oras.utils.find_docker_config(exists=False)
        if os.path.exists(dockercfg_path):  # type: ignore
            cfg = oras.utils.read_json(dockercfg_path)  # type: ignore
        else:
            oras.utils.mkdir_p(os.path.dirname(dockercfg_path))  # type: ignore
            cfg = {"auths": {}}
        if registry in cfg["auths"]:
            cfg["auths"][registry]["auth"] = oras.auth.get_basic_auth(
                username, password
            )
        else:
            cfg["auths"][registry] = {
                "auth": oras.auth.get_basic_auth(username, password)
            }
        oras.utils.write_json(cfg, dockercfg_path)  # type: ignore
        return {"Status": "Login Succeeded"}


def login(
    username: Optional[str] = None,
    password: Optional[str] = None,
    password_stdin: bool = False,
    insecure: bool = False,
    hostname: Optional[str] = None,
    config_path: Optional[str] = None,
) -> dict:
    """
    Login to an OCI registry.

    The username and password can come from stdin.
    """
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
                raise ValueError("token required")

        # If we do have a username, we just need a passowrd
        else:
            password = input("Password: ")
            if not password:
                raise ValueError("password required")

    else:
        logger.warning(
            "WARNING! Using --password via the CLI is insecure. Use --password-stdin."
        )

    # Login
    # https://docker-py.readthedocs.io/en/stable/client.html?highlight=login#docker.client.DockerClient.login
    try:
        client = oras.utils.get_docker_client(insecure=insecure)
        return client.login(
            username=username,
            password=password,
            registry=hostname,
            dockercfg_path=config_path,
        )

    # Fallback to manual login
    except Exception:
        return DockerClient().login(
            username=username,  # type: ignore
            password=password,  # type: ignore
            registry=hostname,  # type: ignore
            dockercfg_path=config_path,
        )


def readline() -> str:
    """
    Read lines from stdin
    """
    content = sys.stdin.readlines()
    return content[0].strip()
