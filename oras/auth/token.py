__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import requests

import oras.auth.utils as auth_utils
from oras.logger import logger

from .base import AuthBackend


class TokenAuth(AuthBackend):
    """
    Token (OAuth2) style auth.
    """

    def __init__(self):
        self.token = None
        super().__init__()

    def _logout(self):
        self.token = None

    def set_token_auth(self, token: str):
        """
        Set token authentication.

        :param token: the bearer token
        :type token: str
        """
        self.token = token

    def get_auth_header(self):
        return {"Authorization": "Bearer %s" % self.token}

    def reset_basic_auth(self):
        """
        Given we have basic auth, reset it.
        """
        if "Authorization" in self.headers:
            del self.headers["Authorization"]
        if self._basic_auth:
            self.set_header("Authorization", "Basic %s" % self._basic_auth)

    def authenticate_request(
        self, original: requests.Response, headers: dict, refresh=False
    ):
        """
        Authenticate Request
        Given a response, look for a Www-Authenticate header to parse.

        We return True/False to indicate if the request should be retried.

        :param original: original response to get the Www-Authenticate header
        :type original: requests.Response
        """
        if refresh:
            self.token = None
        authHeaderRaw = original.headers.get("Www-Authenticate")
        if not authHeaderRaw:
            logger.debug(
                "Www-Authenticate not found in original response, cannot authenticate."
            )
            return headers, False

        # If we have a token, set auth header (base64 encoded user/pass)
        if self.token:
            headers["Authorization"] = "Bearer %s" % self.token
            return headers, True

        h = auth_utils.parse_auth_header(authHeaderRaw)

        # if no basic auth, try by request an anonymous token
        if not hasattr(self, "_basic_auth"):
            anon_token = self.request_anonymous_token(h)
            if anon_token:
                logger.debug("Successfully obtained anonymous token!")
                self.token = anon_token
                headers["Authorization"] = "Bearer %s" % self.token
                return headers, True

        # basic auth is available, try using auth token
        token = self.request_token(h)
        if token:
            self.token = token
            headers["Authorization"] = "Bearer %s" % self.token
            return headers, True

        logger.error(
            "This endpoint requires a token. Please use "
            "basic auth with a username or password."
        )
        return headers, False

    def request_token(self, h: auth_utils.authHeader) -> bool:
        """
        Request an authenticated token and save for later.
        """
        params = {}
        headers = {}

        # Prepare request to retry
        if h.service:
            logger.debug(f"Service: {h.service}")
            params["service"] = h.service
            headers.update(
                {
                    "Service": h.service,
                    "Accept": "application/json",
                    "User-Agent": "oras-py",
                }
            )

        # Ensure the realm starts with http
        if not h.realm.startswith("http"):  # type: ignore
            h.realm = f"{self.prefix}://{h.realm}"

        # If the www-authenticate included a scope, honor it!
        if h.scope:
            logger.debug(f"Scope: {h.scope}")
            params["scope"] = h.scope

        # Set Basic Auth to receive token
        headers["Authorization"] = "Basic %s" % self._basic_auth

        logger.debug(f"Requesting auth token for: {h}")
        authResponse = self.session.get(h.realm, headers=headers, params=params)  # type: ignore

        if authResponse.status_code != 200:
            logger.debug(f"Auth response was not successful: {authResponse.text}")
            return

        # Request the token
        info = authResponse.json()
        return info.get("token") or info.get("access_token")

    def request_anonymous_token(self, h: auth_utils.authHeader) -> bool:
        """
        Given no basic auth, fall back to trying to request an anonymous token.

        Returns: boolean if headers have been updated with token.
        """
        if not h.realm:
            logger.debug("Request anonymous token: no realm provided, exiting early")
            return

        params = {}
        if h.service:
            params["service"] = h.service
        if h.scope:
            params["scope"] = h.scope

        logger.debug(f"Requesting anon token with params: {params}")
        response = self.session.request("GET", h.realm, params=params)
        if response.status_code != 200:
            logger.debug(f"Response for anon token failed: {response.text}")
            return

        # From https://docs.docker.com/registry/spec/auth/token/ section
        # We can get token OR access_token OR both (when both they are identical)
        data = response.json()
        token = data.get("token") or data.get("access_token")

        # Update the headers but not self.token (expects Basic)
        if token:
            return token
        logger.debug("Warning: no token or access_token present in response.")
