__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"


import sys
from typing import List, Optional, Union

import oras.auth
import oras.container
import oras.main.login as login
import oras.provider
import oras.utils
import oras.version


class OrasClient:
    """
    Create an OCI Registry as Storage (ORAS) Client.

    This is intended for controlled interactions. The user of oras-py can use
    this client, the terminal command line wrappers, or the functions in main
    in isolation as an internal Python API. The user can provide a custom
    registry as a parameter, if desired. If not provided we default to standard
    oras.
    """

    def __init__(
        self,
        hostname: Optional[str] = None,
        registry: Optional[oras.provider.Registry] = None,
        insecure: bool = False,
        tls_verify: bool = True,
    ):
        """
        Create an ORAS client.

        The hostname is the remote registry to ping.

        :param hostname: the hostname of the registry to ping
        :type hostname: str
        :param registry: if provided, use this custom provider instead of default
        :type registry: oras.provider.Registry or None
        :param insecure: use http instead of https
        :type insecure: bool
        """
        self.remote = registry or oras.provider.Registry(hostname, insecure, tls_verify)

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return "[oras-client]"

    def set_token_auth(self, token: str):
        """
        Set token authentication.

        :param token: the bearer token
        :type token: str
        """
        self.remote.set_token_auth(token)

    def set_basic_auth(self, username: str, password: str):
        """
        Add basic authentication to the request.

        :param username: the user account name
        :type username: str
        :param password: the user account password
        :type password: str
        """
        self.remote.set_basic_auth(username, password)

    def version(self, return_items: bool = False) -> Union[dict, str]:
        """
        Get the version of the client.

        :param return_items : return the dict of version info instead of string
        :type return_items: bool
        """
        version = oras.version.__version__

        python_version = "%s.%s.%s" % (
            sys.version_info.major,
            sys.version_info.minor,
            sys.version_info.micro,
        )
        versions = {"Version": version, "Python version": python_version}

        # If the user wants the dictionary of items returned
        if return_items:
            return versions

        # Otherwise return a string that can be printed
        return "\n".join(["%s: %s" % (k, v) for k, v in versions.items()])

    def get_tags(self, name: str, N=None) -> List[str]:
        """
        Retrieve tags for a package.

        :param name: container URI to parse
        :type name: str
        :param N: number of tags (None to get all tags)
        :type N: int
        """
        return self.remote.get_tags(name, N=N)

    def delete_tags(self, name: str, tags=Union[str, list]) -> List[str]:
        """
        Delete one or more tags for a unique resource identifier.

        Returns those successfully deleted.

        :param name: container URI to parse
        :type name: str
        :param tags: single or multiple tags name to delete
        :type N: string or list
        """
        if isinstance(tags, str):
            tags = [tags]
        deleted = []
        for tag in tags:
            if self.remote.delete_tag(name, tag):
                deleted.append(tag)
        return deleted

    def push(self, *args, **kwargs):
        """
        Push a container to the remote.
        """
        return self.remote.push(*args, **kwargs)

    def pull(self, *args, **kwargs):
        """
        Pull a container from the remote.
        """
        return self.remote.pull(*args, **kwargs)

    def login(
        self,
        username: str,
        password: str,
        password_stdin: bool = False,
        insecure: bool = False,
        tls_verify: bool = True,
        hostname: Optional[str] = None,
        config_path: Optional[List[str]] = None,
    ) -> dict:
        """
        Login to a registry.

        :param registry: if provided, use this custom provider instead of default
        :type registry: oras.provider.Registry or None
        :param username: the user account name
        :type username: str
        :param password: the user account password
        :type password: str
        :param password_stdin: get the password from standard input
        :type password_stdin: bool
        :param insecure: use http instead of https
        :type insecure: bool
        :param tls_verify: verify tls
        :type tls_verify: bool
        :param hostname: the hostname to login to
        :type hostname: str
        :param config_path: list of config paths to add
        :type config_path: list
        """
        login_func = self._login
        if hasattr(self.remote, "login"):
            login_func = self.remote.login  # type: ignore
        return login_func(
            username=username,
            password=password,
            password_stdin=password_stdin,
            tls_verify=tls_verify,
            hostname=hostname,
            config_path=config_path,  # type: ignore
        )

    def logout(self, hostname: str):
        """
        Logout from a registry, meaning removing any auth (if loaded)

        :param hostname: the hostname to login to
        :type hostname: str
        """
        self.remote.logout(hostname)

    def _login(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        password_stdin: bool = False,
        tls_verify: bool = True,
        hostname: Optional[str] = None,
        config_path: Optional[str] = None,
    ) -> dict:
        """
        Login to an OCI registry.

        The username and password can come from stdin. Most people use username
        password to get a token, so we are disabling providing just a token for
        now. A tool that wants to provide a token should use set_token_auth.
        """
        # Read password from stdin
        if password_stdin:
            password = oras.utils.readline()

        # No username, try to get from stdin
        if not username:
            username = input("Username: ")

        # No password provided
        if not password:
            password = input("Password: ")
            if not password:
                raise ValueError("password required")

        # Cut out early if we didn't get what we need
        if not password or not username:
            return {"Login": "Not successful"}

        # Set basic auth for the client
        self.set_basic_auth(username, password)

        # Login
        # https://docker-py.readthedocs.io/en/stable/client.html?highlight=login#docker.client.DockerClient.login
        try:
            client = oras.utils.get_docker_client(tls_verify=tls_verify)
            return client.login(
                username=username,
                password=password,
                registry=hostname,
                dockercfg_path=config_path,
            )

        # Fallback to manual login
        except Exception:
            return login.DockerClient().login(
                username=username,  # type: ignore
                password=password,  # type: ignore
                registry=hostname,  # type: ignore
                dockercfg_path=config_path,
            )
