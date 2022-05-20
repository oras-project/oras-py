__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"


import sys
from typing import List, Optional, Union

import oras.container
import oras.main as main
import oras.provider
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
    ):
        """
        Create an ORAS client.

        The hostname is the remote registry to ping.

        Arguments
        ---------
        hostname : the hostname of the registry to ping
        registry : if provided, use this custom provider instead of default
        insecure : use http instead of https
        """
        self.remote = registry or oras.provider.Registry(hostname, insecure)

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return "[oras-client]"

    def set_basic_auth(self, username: str, password: str):
        """
        Add basic authentication to the request.

        Arguments
        ---------
        username : the user account name
        password : the user account password
        """
        self.remote.set_basic_auth(username, password)

    def version(self, return_items: bool = False) -> Union[dict, str]:
        """
        Get the version of the client.

        Arguments
        ---------
        return_items : return the dict of version info instead of string
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

    def get_tags(self, name: str, N: int = 10_000) -> List[str]:
        """
        Retrieve tags for a package.

        Arguments
        ---------
        name  : container URI to parse
        N     : number of tags
        """
        return self.remote.get_tags(name, N=N).json()

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
        hostname: Optional[str] = None,
        config_path: Optional[List[str]] = None,
    ):
        """
        Login to a registry.

        Arguments
        ---------
        username       : the user account name
        password       : the user account password
        password_stdin : get the password from standard input
        insecure       : use http instead of https
        hostname       : name of the host to login to
        config_path    : list of config paths to add
        """
        login_func = main.login
        if hasattr(self.remote, "login"):
            login_func = self.remote.login  # type: ignore
        return login_func(
            username=username,
            password=password,
            password_stdin=password_stdin,
            insecure=insecure,
            hostname=hostname,
            config_path=config_path,  # type: ignore
        )

    def logout(self, hostname: str):
        """
        Logout from a registry, meaning removing any auth (if loaded)

        Arguments
        ---------
        hostname       : name of the host to login to
        """
        self.remote.logout(hostname)
