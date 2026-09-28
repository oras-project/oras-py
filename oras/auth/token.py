__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

from typing import Optional

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
        if self.token:
            return {"Authorization": "Bearer %s" % self.token}
        return {}

    def reset_basic_auth(self):
        """
        Given we have basic auth, reset it.
        """
        if "Authorization" in self.headers:
            del self.headers["Authorization"]
        if self._basic_auth:
            self.set_header("Authorization", "Basic %s" % self._basic_auth)

    def _begin_challenge(self, original, headers: dict, refresh: bool):
        """
        Work out what answering a challenge requires, before any request.

        This is the half of the flow that only makes decisions, so both the
        synchronous and the asynchronous answer share it.

        :param original: original response to get the Www-Authenticate header
        :param headers: headers of the request to retry
        :type headers: dict
        :param refresh: discard a cached token first
        :type refresh: bool
        :return: (headers, parsed challenge, early result). When the early
                 result is not None the caller is finished and returns it,
                 either because there was no challenge or because a cached
                 token already answers it.
        """
        headers = headers or {}
        if refresh:
            self.token = None
        authHeaderRaw = original.headers.get("Www-Authenticate")
        if not authHeaderRaw:
            logger.debug(
                "Www-Authenticate not found in original response, cannot authenticate."
            )
            return headers, None, (headers, False)

        # If we have a token, set auth header (base64 encoded user/pass)
        if self.token:
            headers["Authorization"] = "Bearer %s" % self.token
            return headers, None, (headers, True)

        return headers, auth_utils.parse_auth_header(authHeaderRaw), None

    def _accept_token(self, token: str, headers: dict):
        """
        Cache a token that was just obtained, and use it for the retry.

        :param token: the bearer token
        :type token: str
        :param headers: headers of the request to retry
        :type headers: dict
        """
        self.token = token
        headers["Authorization"] = "Bearer %s" % self.token
        return headers, True

    def _no_token(self, headers: dict):
        """
        Report that a challenge could not be answered.

        :param headers: headers of the request that was challenged
        :type headers: dict
        """
        logger.error(
            "This endpoint requires a token. Please use "
            "basic auth with a username or password."
        )
        return headers, False

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
        headers, h, early = self._begin_challenge(original, headers, refresh)
        if early is not None:
            return early

        # if no basic auth, try by request an anonymous token
        if not hasattr(self, "_basic_auth"):
            anon_token = self.request_anonymous_token(h)
            if anon_token:
                logger.debug("Successfully obtained anonymous token!")
                return self._accept_token(anon_token, headers)

        # basic auth is available, try using auth token
        token = self.request_token(h)
        if token:
            return self._accept_token(token, headers)

        return self._no_token(headers)

    async def authenticate_request_async(self, original, headers: dict, refresh=False):
        """
        Answer a challenge without blocking the event loop.

        The decisions are the same as the synchronous version, only the token
        request is awaited.

        :param original: original response to get the Www-Authenticate header
        :param headers: headers of the request to retry
        :type headers: dict
        :param refresh: discard a cached token first
        :type refresh: bool
        """
        headers, h, early = self._begin_challenge(original, headers, refresh)
        if early is not None:
            return early

        if not hasattr(self, "_basic_auth"):
            anon_token = await self.request_anonymous_token_async(h)
            if anon_token:
                logger.debug("Successfully obtained anonymous token!")
                return self._accept_token(anon_token, headers)

        token = await self.request_token_async(h)
        if token:
            return self._accept_token(token, headers)

        return self._no_token(headers)

    def _token_request(self, h: auth_utils.authHeader):
        """
        Build the request that asks a realm for a token.

        :param h: the parsed Www-Authenticate header
        :type h: oras.auth.utils.authHeader
        :return: (realm, headers, params) for the token request
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

        # Set Basic Auth to receive token, if available
        if hasattr(self, "_basic_auth") and self._basic_auth:
            headers["Authorization"] = "Basic %s" % self._basic_auth
            logger.debug("Using Basic Auth for token request.")
        else:
            logger.debug(
                "No Basic Auth available or configured for token request. Proceeding without Basic Auth header for token endpoint."
            )

        logger.debug(
            f"Requesting auth token for: {h} with header keys: {list(headers.keys())}"
        )
        return h.realm, headers, params

    def _token_from_response(self, response) -> Optional[str]:
        """
        Read a token out of a realm's answer.

        From https://docs.docker.com/registry/spec/auth/token/ we can get token
        OR access_token OR both (when both they are identical).

        :param response: the answer from the token realm
        """
        if response.status_code != 200:
            logger.debug(f"Auth response was not successful: {response.text}")
            return None

        info = response.json()
        return info.get("token") or info.get("access_token")

    def _anonymous_token_request(self, h: auth_utils.authHeader):
        """
        Build the request that asks a realm for an anonymous token.

        :param h: the parsed Www-Authenticate header
        :type h: oras.auth.utils.authHeader
        :return: (realm, params), or None when there is no realm to ask
        """
        if not h.realm:
            logger.debug("Request anonymous token: no realm provided, exiting early")
            return None

        params = {}
        if h.service:
            params["service"] = h.service
        if h.scope:
            params["scope"] = h.scope

        logger.debug(f"Requesting anon token with params: {params}")
        return h.realm, params

    def request_token(self, h: auth_utils.authHeader) -> Optional[str]:
        """
        Request an authenticated token and save for later.

        :param h: the parsed Www-Authenticate header
        :type h: oras.auth.utils.authHeader
        """
        realm, headers, params = self._token_request(h)
        response = self.transport.request(realm, "GET", headers=headers, params=params)  # type: ignore
        return self._token_from_response(response)

    async def request_token_async(self, h: auth_utils.authHeader) -> Optional[str]:
        """
        Request an authenticated token without blocking the event loop.

        :param h: the parsed Www-Authenticate header
        :type h: oras.auth.utils.authHeader
        """
        realm, headers, params = self._token_request(h)
        response = await self.transport.request(realm, "GET", headers=headers, params=params)  # type: ignore
        return self._token_from_response(response)

    def request_anonymous_token(self, h: auth_utils.authHeader) -> Optional[str]:
        """
        Given no basic auth, fall back to trying to request an anonymous token.

        :param h: the parsed Www-Authenticate header
        :type h: oras.auth.utils.authHeader
        """
        request = self._anonymous_token_request(h)
        if not request:
            return None

        realm, params = request
        response = self.transport.request(realm, "GET", params=params)
        return self._token_from_response(response)

    async def request_anonymous_token_async(
        self, h: auth_utils.authHeader
    ) -> Optional[str]:
        """
        Request an anonymous token without blocking the event loop.

        :param h: the parsed Www-Authenticate header
        :type h: oras.auth.utils.authHeader
        """
        request = self._anonymous_token_request(h)
        if not request:
            return None

        realm, params = request
        response = await self.transport.request(realm, "GET", params=params)
        return self._token_from_response(response)
