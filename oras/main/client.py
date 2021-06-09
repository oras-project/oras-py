__author__ = "Vanessa Sochat"
__copyright__ = "Copyright 2021, Vanessa Sochat"
__license__ = "MIT"


import oras.version
import oras.defaults as defaults
from oras.logger import logger

import os
import re
import shutil
import sys


class Client:
    """
    Create an OCI Registry as Storage Client.
    """

    def __init__(self, quiet=False):
        self.quiet = quiet

    def __repr__(self):
        return str(self)

    def __str__(self):
        return "[oras-client]"

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
        if defaults.git_commit:
            versions["Git commit"] = git_commit

        if defaults.git_tree_state:
            versions["Git tree state"] = defaults.git_tree_state

        # If the user wants the dictionary of items returned
        if return_items:
            return versions

        # Otherwise return a string that can be printed
        return "\n".join(["%s: %s" % (k, v) for k, v in versions.items()])

    def push(self, name, tag=None, **kwargs):
        """
        Push a container.
        """
        print("PUSH")
        import IPython

        IPython.embed()

    def pull(self, name, tag=None):
        """
        Pull a container.
        """
        print("PULL")
        import IPython

        IPython.embed()

    def login(self, username, password, password_stdin=False, insecure=False):
        """
        Login to a registry.
        """
        print("LOGIN")
        import IPython

        IPython.embed()

    def logout(self, sif, module_name):
        """
        Logout from a registry.
        """
        print("LOGOUT")
        import IPython

        IPython.embed()
