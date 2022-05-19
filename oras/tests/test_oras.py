import os
import sys
import re
import pytest
import shutil
import oras.client

here = os.path.abspath(os.path.dirname(__file__))

registry_host = os.environ.get("ORAS_HOST")
registry_port = os.environ.get("ORAS_PORT")


def setup_module(module):
    """Ensure the registry port and host is in the environment."""
    if not registry_host or not registry_port:
        sys.exit(
            "You must export ORAS_HOST and ORAS_PORT for a running registry before running tests."
        )


registry = f"{registry_host}:{registry_port}"
target = f"{registry}/dinosaur/artifact:v1"

# TODO test oras auth...


def test_oras(tmp_path):
    """
    Basic tests for oras (without authentication)
    """
    client = oras.client.OrasClient(insecure=True)
    artifact = os.path.join(here, "artifact.txt")

    assert os.path.exists(artifact)
    res = client.push(files=[artifact], target=target)
    assert res.status_code == 201

    # Move artifact outside of context (should not work)
    moved_artifact = tmp_path / os.path.basename(artifact)
    shutil.copyfile(artifact, moved_artifact)
    with pytest.raises(SystemExit):
        client.push(files=[moved_artifact], target=target)

    # This should work because we aren't checking paths
    res = client.push(files=[artifact], target=target, disable_path_validation=True)
    assert res.status_code == 201
