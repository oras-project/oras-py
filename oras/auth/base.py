__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import json
import subprocess
from typing import Optional

import requests

import oras.auth.utils as auth_utils
import oras.container
import oras.decorator as decorator
from oras.logger import logger
from oras.types import container_type


class AuthBackend:
    """
    Generic (and default) auth backend.
    """

    session: requests.Session
    _tls_verify: bool

    def __init__(self, *args, **kwargs):
        self._auth_config: dict = {}
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
        if not self._auth_config or not self._auth_config.get("auths"):
            logger.info(f"You are not logged in to {hostname}")
            return

        for host in oras.utils.iter_localhosts(hostname):
            auths = self._auth_config.get("auths", {})
            if host in auths:
                del auths[host]
                logger.info(f"You have successfully logged out of {hostname}")
                return
        logger.info(f"You are not logged in to {hostname}")

    def _logout(self):
        pass

    def _get_auth_from_creds_store(self, suffix: str, hostname: str) -> Optional[str]:
        binary = f"docker-credential-{suffix}"
        try:
            proc = subprocess.run(
                [binary, "get"],
                input=hostname.encode(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
        except FileNotFoundError:
            logger.warning(f"Credential helper '{binary}' not found in PATH")
            return None
        except subprocess.CalledProcessError as exc:
            logger.warning(
                f"Credential helper '{binary}' failed: {exc.stderr.decode().strip()}"
            )
            return None
        payload = json.loads(proc.stdout)
        return auth_utils.get_basic_auth(payload["Username"], payload["Secret"])

    def _load_auth(self, hostname: str) -> bool:
        """
        Look for and load a named authentication token.

        :param hostname: the registry hostname to look for
        :type hostname: str
        """
        # Note that the hostname can be defined without a token
        auths = self._auth_config.get("auths", {})
        auth = auths.get(hostname)
        if auth is not None:
            auth = auths[hostname].get("auth")

            if not auth:
                # no auth there (wonky file)
                return False
            self._basic_auth = auth
            return True
        # Check for credHelper
        if self._auth_config.get("credHelpers", {}).get(hostname):
            auth = self._get_auth_from_creds_store(
                self._auth_config["credHelpers"][hostname], hostname
            )
            if auth is not None:
                self._basic_auth = auth
                auths[hostname] = {"auth": auth}
                return True
        # Check for credsStore:
        if self._auth_config.get("credsStore"):
            auth = self._get_auth_from_creds_store(
                self._auth_config["credsStore"], hostname
            )
            if auth is not None:
                self._basic_auth = auth
                auths[hostname] = {"auth": auth}
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
        if not self._auth_config:
            self._auth_config = auth_utils.load_configs(configs)
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
