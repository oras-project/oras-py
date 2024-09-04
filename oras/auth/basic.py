__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import os
from typing import Optional, Tuple

import requests

from .base import AuthBackend


class BasicAuth(AuthBackend):
    """
    Generic (and default) auth backend.
    """

    def __init__(self, session: requests.Session):
        username = os.environ.get("ORAS_USER")
        password = os.environ.get("ORAS_PASS")
        super().__init__(session=session)
        if username and password:
            self.set_basic_auth(username, password)

    def _logout(self):
        self._basic_auth = None

    def get_auth_header(self):
        return {"Authorization": "Basic %s" % self._basic_auth}

    def authenticate_request(
        self,
        original: requests.Response,
        headers: Optional[dict[str, str]] = None,
        refresh=False,
    ) -> Tuple[dict[str, str], bool]:
        """
        Authenticate Request
        Given a response, look for a Www-Authenticate header to parse.

        We return True/False to indicate if the request should be retried.

        :param originalResponse: original response to get the Www-Authenticate header
        :type originalResponse: requests.Response
        """
        result = {}
        if headers is not None:
            result.update(headers)
        result.update(self.get_auth_header())
        return result, True
