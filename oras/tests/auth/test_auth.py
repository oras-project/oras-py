from types import SimpleNamespace

import boto3

import oras.auth.utils as auth_utils
from oras.auth.ecr import EcrAuth
from oras.auth.token import TokenAuth


class DummyResponse:
    """Bare-minimum imitation of requests.Response for testing."""

    def __init__(self, headers):
        self.headers = headers


def test_no_auth_header(monkeypatch):
    auth = EcrAuth()
    original = DummyResponse(headers={})

    out_headers, retry = auth.authenticate_request(original, {})

    assert retry is False
    assert out_headers == {}
    assert auth._tokens == {}


def test_fallback_to_super(monkeypatch):
    monkeypatch.setattr(
        auth_utils,
        "parse_auth_header",
        lambda _: SimpleNamespace(service="not-ecr", realm="https://foo/"),
    )

    called = {}

    def fake_super(self, original, headers, refresh):
        called["yes"] = True
        return {}, True

    monkeypatch.setattr(TokenAuth, "authenticate_request", fake_super)

    auth = EcrAuth()
    resp = DummyResponse({"Www-Authenticate": 'Bearer realm="https://foo/"'})
    result = auth.authenticate_request(resp, {})

    assert called == {"yes": True}
    assert result == ({}, True)


def test_ecr_token_flow(monkeypatch):
    region = "eu-west-1"
    account = "123456789012"
    realm = f"https://{account}.dkr.ecr.{region}.amazonaws.com/"
    ww_auth = f'Bearer realm="{realm}",service="ecr.amazonaws.com"'

    monkeypatch.setattr(
        auth_utils,
        "parse_auth_header",
        lambda _: SimpleNamespace(service="ecr.amazonaws.com", realm=realm),
    )

    tokens_given = []

    def fake_boto3_client(service, region_name):
        assert service == "ecr"
        assert region_name == region

        token = f"token{len(tokens_given)+1}"
        tokens_given.append(token)

        class FakeEcr:
            def get_authorization_token(self):
                return {"authorizationData": [{"authorizationToken": token}]}

        return FakeEcr()

    monkeypatch.setattr(boto3, "client", fake_boto3_client)

    auth = EcrAuth()
    resp = DummyResponse({"Www-Authenticate": ww_auth})

    # 1st call – always triggers AWS client
    hdrs1, retry1 = auth.authenticate_request(resp, {})
    assert retry1 is True
    assert hdrs1["Authorization"] == "Basic token1"
    assert tokens_given == ["token1"]

    # 2nd call
    hdrs2, retry2 = auth.authenticate_request(resp, {}, refresh=False)

    assert len(tokens_given) == 1
    assert hdrs2["Authorization"] == "Basic token1"

    # 3rd call
    hdrs3, retry3 = auth.authenticate_request(resp, {}, refresh=True)

    assert len(tokens_given) == 2
    assert hdrs3["Authorization"] == "Basic token2"

    # Cache should contain the most recent token for the realm
    assert auth._tokens[realm] == "token2"
