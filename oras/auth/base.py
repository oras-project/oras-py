__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"


from typing import Optional

import oras.auth.utils as auth_utils
import oras.container
import oras.decorator as decorator
from oras.logger import logger
from oras.types import container_type


class AuthBackend:
    """
    Generic (and default) auth backend.
    """

    def __init__(self, *args, **kwargs):
        self._auths: dict = {}
        self.prefix: str = "https"

    def get_auth_header(self):
        raise NotImplementedError

    def get_container(self, name: container_type) -> oras.container.Container:
        """
        Courtesy function to get a container from a URI.

        :param name: unique resource identifier to parse
        :type name: oras.container.Container or str
        """
        if isinstance(name, oras.container.Container):
            return name
        return oras.container.Container(name, registry=self.hostname)

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

    @decorator.ensure_container
    def load_configs(self, container: container_type, configs: Optional[list] = None):
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
        for registry in oras.utils.iter_localhosts(container.registry):  # type: ignore
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

    def request_anonymous_token(self, h: auth_utils.authHeader, headers: dict) -> bool:
        """
        Given no basic auth, fall back to trying to request an anonymous token.

        Returns: boolean if headers have been updated with token.
        """
        if not h.realm:
            logger.debug("Request anonymous token: no realm provided, exiting early")
            return headers, False

        params = {}
        if h.service:
            params["service"] = h.service
        if h.scope:
            params["scope"] = h.scope

        logger.debug(f"Final params are {params}")
        response = self.session.request("GET", h.realm, params=params)
        if response.status_code != 200:
            logger.debug(f"Response for anon token failed: {response.text}")
            return headers, False

        # From https://docs.docker.com/registry/spec/auth/token/ section
        # We can get token OR access_token OR both (when both they are identical)
        data = response.json()
        token = data.get("token") or data.get("access_token")

        # Update the headers but not self.token (expects Basic)
        if token:
            headers["Authorization"] = {"Authorization": "Bearer %s" % token}

        logger.debug("Warning: no token or access_token present in response.")
        return headers, False
