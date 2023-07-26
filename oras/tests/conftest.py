import os
from dataclasses import dataclass

import pytest


@dataclass
class TestCredentials:
    with_auth: bool
    user: str
    password: str


@pytest.fixture
def registry():
    host = os.environ.get("ORAS_HOST")
    port = os.environ.get("ORAS_PORT")

    if not host or not port:
        pytest.skip(
            "You must export ORAS_HOST and ORAS_PORT"
            " for a running registry before running tests."
        )

    return f"{host}:{port}"


@pytest.fixture
def credentials(request):
    with_auth = os.environ.get("ORAS_AUTH") == "true"
    user = os.environ.get("ORAS_USER", "myuser")
    pwd = os.environ.get("ORAS_PASS", "mypass")

    if with_auth and not user or not pwd:
        pytest.skip("To test auth you need to export ORAS_USER and ORAS_PASS")

    marks = [m.name for m in request.node.iter_markers()]
    if request.node.parent:
        marks += [m.name for m in request.node.parent.iter_markers()]

    if request.node.get_closest_marker("with_auth"):
        if request.node.get_closest_marker("with_auth").args[0] != with_auth:
            if with_auth:
                pytest.skip("test requires un-authenticated access to registry")
            else:
                pytest.skip("test requires authenticated access to registry")

    return TestCredentials(with_auth, user, pwd)


@pytest.fixture
def target(registry):
    return f"{registry}/dinosaur/artifact:v1"


@pytest.fixture
def target_dir(registry):
    return f"{registry}/dinosaur/directory:v1"
