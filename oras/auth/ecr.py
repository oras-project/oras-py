__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import asyncio
import re
from typing import Optional

import requests

import oras.auth.utils as auth_utils
from oras.auth.token import TokenAuth
from oras.logger import logger
from oras.types import container_type


class EcrAuth(TokenAuth):
    """
    Auth backend for AWS ECR (Elastic Container Registry) using token-based authentication.
    """

    AWS_ECR_PATTERN = re.compile(
        r"(?P<account_id>\d{12})\.dkr\.ecr\.(?P<region>[^.]+)\.amazonaws\.com"
    )
    AWS_ECR_REALM_PATTERN = re.compile(
        r"https://(?P<account_id>\d{12})\.dkr\.ecr\.(?P<region>[^.]+)\.amazonaws\.com/"
    )

    def __init__(self):
        super().__init__()
        self._tokens = {}

    def load_configs(
        self, container: container_type, configs: Optional[list] = None
    ) -> None:
        if not self.AWS_ECR_PATTERN.fullmatch(container.registry):
            super().load_configs(container, configs)

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
        headers = headers or {}
        authHeaderRaw = original.headers.get("Www-Authenticate")
        if not authHeaderRaw:
            logger.debug(
                "Www-Authenticate not found in original response, cannot authenticate."
            )
            return headers, False

        h = auth_utils.parse_auth_header(authHeaderRaw)
        if h.service != "ecr.amazonaws.com" or h.realm is None:
            return super().authenticate_request(original, headers, refresh)
        token = self._tokens.get(h.realm)
        if not token or refresh:
            region = self._region_for(h)
            if region is None:
                return super().request_token(h)
            token = self._fetch_token(h.realm, region)

        return self._authorization(headers, token), True

    async def authenticate_request_async(self, original, headers: dict, refresh=False):
        """
        Answer a challenge for an asynchronous request.

        A non-ECR realm is answered over the async transport by TokenAuth. An
        ECR realm is answered by the AWS SDK, which is synchronous and has no
        async equivalent without taking on another dependency. That one call is
        run in a worker thread so it does not block the event loop; it happens
        once per realm and the result is cached, so the cost is bounded.

        :param original: original response to get the Www-Authenticate header
        :param headers: headers of the request to retry
        :type headers: dict
        :param refresh: discard a cached token first
        :type refresh: bool
        """
        headers = headers or {}
        authHeaderRaw = original.headers.get("Www-Authenticate")
        if not authHeaderRaw:
            logger.debug(
                "Www-Authenticate not found in original response, cannot authenticate."
            )
            return headers, False

        h = auth_utils.parse_auth_header(authHeaderRaw)
        if h.service != "ecr.amazonaws.com" or h.realm is None:
            return await super().authenticate_request_async(original, headers, refresh)

        token = self._tokens.get(h.realm)
        if not token or refresh:
            region = self._region_for(h)
            if region is None:
                return await super().request_token_async(h)
            loop = asyncio.get_running_loop()
            token = await loop.run_in_executor(None, self._fetch_token, h.realm, region)

        return self._authorization(headers, token), True

    def _region_for(self, h: auth_utils.authHeader) -> Optional[str]:
        """
        Get the AWS region a realm belongs to, if it looks like an ECR realm.

        :param h: the parsed Www-Authenticate header
        :type h: oras.auth.utils.authHeader
        """
        m = re.fullmatch(self.AWS_ECR_REALM_PATTERN, h.realm)  # type: ignore
        if not m:
            logger.warning(f"realm: {h.realm} did not match expected pattern.")
            return None
        return m.group("region")

    def _fetch_token(self, realm: str, region: str) -> str:
        """
        Ask AWS for an authorization token, and remember it for the realm.

        This is a blocking SDK call. Callers on an event loop run it in a
        worker thread rather than awaiting it.

        :param realm: the realm the token is for
        :type realm: str
        :param region: the AWS region to ask
        :type region: str
        """
        try:
            import boto3
        except ImportError as e:
            msg = """the `boto3` dependency is required to support authentication to this registry.
            Make sure to install the required extra "ecr", e.g.: pip install oras[ecr].
            """
            raise ImportError(msg) from e
        ecr = boto3.client("ecr", region_name=region)
        auth = ecr.get_authorization_token()["authorizationData"][0]
        token = auth.get("authorizationToken", "")
        self._tokens[realm] = token
        return token

    def _authorization(self, headers: dict, token: str) -> dict:
        """
        Add the ECR token to the headers of the request being retried.

        :param headers: headers of the request to retry
        :type headers: dict
        :param token: the authorization token from AWS
        :type token: str
        """
        result = {}
        if headers is not None:
            result.update(headers)
        result["Authorization"] = "Basic %s" % token
        return result
