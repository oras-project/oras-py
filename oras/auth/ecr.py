__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

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
            m = re.fullmatch(
                self.AWS_ECR_REALM_PATTERN,
                h.realm,
            )
            if not m:
                logger.warning(f"realm: {h.realm} did not match expected pattern.")
                return super().request_token(h)
            region = m.group("region")
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
            self._tokens[h.realm] = token

        result = {}
        if headers is not None:
            result.update(headers)
        result["Authorization"] = "Basic %s" % token
        return result, True
