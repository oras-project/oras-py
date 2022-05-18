__author__ = "Vanessa Sochat"
__copyright__ = "Copyright 2021-2022, Vanessa Sochat"
__license__ = "MIT"


import oras.version
import oras.defaults as defaults
import oras.main as main
import oras.container
import oras.provider

import sys


class OrasClient:
    """
    Create an OCI Registry as Storage (ORAS) Client.

    This is intended for controlled interactions. The user of oras-py can use
    this client, the terminal command line wrappers, or the functions in main
    in isolation as an internal Python API. The user can provide a custom
    registry as a parameter, if desired. If not provided we default to standard
    oras.
    """

    def __init__(self, hostname=None, registry=None, insecure=False):
        """
        Create an ORAS client.

        The hostname is the remote registry to ping.
        """
        self.remote = registry or oras.provider.Registry(hostname, insecure)

    def __repr__(self):
        return str(self)

    def __str__(self):
        return "[oras-client]"

    def set_basic_auth(self, username, password):
        """
        Add basic authentication to the request.
        """
        self.remote.set_basic_auth(username, password)

    def version(self, return_items=False):
        """
        Get the version of the client.
        """
        version = oras.version.__version__
        if defaults.build_metadata:
            version = "%s+%s" % (version, defaults.build_metadata)

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

    def push(self, *args, **kwargs):
        """
        Push a container to the remote.

        TODO: a push will eventually be a copy from source to destination.
        """
        return self.remote.push(*args, **kwargs)

    def pull(self, *args, **kwargs):
        """
        Pull a container from the remote.

        TODO: a push will eventually be a copy from destination to source.
        """
        return self.remote.pull(*args, **kwargs)

    def login(
        self,
        username,
        password,
        password_stdin=False,
        insecure=False,
        hostname=None,
        config_path=None,
    ):
        """
        Login to a registry.

        A registry can implement a custom login. Otherwise, we use a standard
        docker login.
        """
        login_func = main.login
        if hasattr(self.remote, "login"):
            login_func = self.remote.login
        return login_func(
            username=username,
            password=password,
            password_stdin=password_stdin,
            insecure=insecure,
            hostname=hostname,
            config_path=config_path,
        )

    def logout(self, sif, module_name):
        """
        Logout from a registry.
        """
        print("LOGOUT")
        import IPython

        IPython.embed()
