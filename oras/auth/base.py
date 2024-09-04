__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import abc
from typing import Dict, Optional, Tuple

import oras.auth.utils as auth_utils
import oras.container
from oras.logger import logger
import oras.utils

import requests


class AuthBackend(abc.ABC):
    """
    Generic (and default) auth backend.
    """

    def __init__(self, session: requests.Session):
        self._auths: dict = {}
        self.session = session
        self.headers: Dict[str, str] = {}

    @abc.abstractmethod
    def authenticate_request(
        self,
        original: requests.Response,
        headers: Optional[dict[str, str]] = None,
        refresh=False,
    ) -> Tuple[dict[str, str], bool]:
        pass

    def set_header(self, name: str, value: str):
        """
        Courtesy function to set a header

        :param name: header name to set
        :type name: str
        :param value: header value to set
        :type value: str
        """
        self.headers.update({name: value})

    def get_auth_header(self):
        raise NotImplementedError

    def logout(self, hostname: str):
        """
        If auths are loaded, remove a hostname.

        :param hostname: the registry hostname to remove
        :type hostname: str
        """
        self._logout()
        if not self._auths:
            logger.info(f"You are not logged in to {hostname}")
            return

        for host in oras.utils.iter_localhosts(hostname):
            if host in self._auths:
                del self._auths[host]
                logger.info(f"You have successfully logged out of {hostname}")
                return
        logger.info(f"You are not logged in to {hostname}")

    def _logout(self):
        pass

    def _load_auth(self, hostname: str) -> bool:
        """
        Look for and load a named authentication token.

        :param hostname: the registry hostname to look for
        :type hostname: str
        """
        # Note that the hostname can be defined without a token
        if hostname in self._auths:
            auth = self._auths[hostname].get("auth")

            # Case 1: they use a credsStore we don't know how to read
            if not auth and "credsStore" in self._auths[hostname]:
                logger.warning(
                    '"credsStore" found in your ~/.docker/config.json, which is not supported by oras-py. Remove it, docker login, and try again.'
                )
                return False

            # Case 2: no auth there (wonky file)
            elif not auth:
                return False
            self._basic_auth = auth
            return True
        return False

    def load_configs(
        self, container: oras.container.Container, configs: Optional[list] = None
    ):
        """
        Load configs to discover credentials for a specific container.

        This is typically just called once. We always add the default Docker
        config to the set.s

        :param container: the parsed container URI with components
        :type container: oras.container.Container
        :param configs: list of configs to read (optional)
        :type configs: list
        """
        if not self._auths:
            self._auths = auth_utils.load_configs(configs)
        for registry in oras.utils.iter_localhosts(container.registry):
            if self._load_auth(registry):
                return

    def set_token_auth(self, token: str):
        """
        Set token authentication.

        :param token: the bearer token
        :type token: str
        """
        self.token = token
        self.set_header("Authorization", "Bearer %s" % token)

    def set_basic_auth(self, username: str, password: str):
        """
        Set basic authentication.

        :param username: the user account name
        :type username: str
        :param password: the user account password
        :type password: str
        """
        self._basic_auth = auth_utils.get_basic_auth(username, password)
