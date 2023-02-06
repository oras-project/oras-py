__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import os
import shutil
import sys

import pytest

import oras.client

here = os.path.abspath(os.path.dirname(__file__))

registry_host = os.environ.get("ORAS_HOST")
registry_port = os.environ.get("ORAS_PORT")
with_auth = os.environ.get("ORAS_AUTH") == "true"
oras_user = os.environ.get("ORAS_USER", "myuser")
oras_pass = os.environ.get("ORAS_PASS", "mypass")


def setup_module(module):
    """
    Ensure the registry port and host is in the environment.
    """
    if not registry_host or not registry_port:
        sys.exit(
            "You must export ORAS_HOST and ORAS_PORT for a running registry before running tests."
        )
    if with_auth and not oras_user or not oras_pass:
        sys.exit("To test auth you need to export ORAS_USER and ORAS_PASS")


registry = f"{registry_host}:{registry_port}"
target = f"{registry}/dinosaur/artifact:v1"
target_dir = f"{registry}/dinosaur/directory:v1"


def test_basic_oras():
    """
    Basic tests for oras (without authentication)
    """
    client = oras.client.OrasClient(hostname=registry, insecure=True)
    assert "Python version" in client.version()


@pytest.mark.skipif(not with_auth, reason="basic auth is needed for login/logout")
def test_login_logout():
    """
    Login and logout are all we can test with basic auth!
    """
    client = oras.client.OrasClient(hostname=registry, insecure=True)
    res = client.login(
        hostname=registry, username=oras_user, password=oras_pass, insecure=True
    )
    assert res["Status"] == "Login Succeeded"
    client.logout(registry)


@pytest.mark.skipif(with_auth, reason="token auth is needed for push and pull")
def test_basic_push_pull(tmp_path):
    """
    Basic tests for oras (without authentication)
    """
    client = oras.client.OrasClient(hostname=registry, insecure=True)
    artifact = os.path.join(here, "artifact.txt")

    assert os.path.exists(artifact)

    res = client.push(files=[artifact], target=target)
    assert res.status_code in [200, 201]

    # Test pulling elsewhere
    files = client.pull(target=target, outdir=tmp_path)
    assert len(files) == 1
    assert os.path.basename(files[0]) == "artifact.txt"
    assert str(tmp_path) in files[0]
    assert os.path.exists(files[0])

    # Move artifact outside of context (should not work)
    moved_artifact = tmp_path / os.path.basename(artifact)
    shutil.copyfile(artifact, moved_artifact)
    with pytest.raises(ValueError):
        client.push(files=[moved_artifact], target=target)

    # This should work because we aren't checking paths
    res = client.push(files=[artifact], target=target, disable_path_validation=True)
    assert res.status_code == 201


@pytest.mark.skipif(with_auth, reason="token auth is needed for push and pull")
def test_get_delete_tags(tmp_path):
    """
    Test creationg, getting, and deleting tags.
    """
    client = oras.client.OrasClient(hostname=registry, insecure=True)
    artifact = os.path.join(here, "artifact.txt")
    assert os.path.exists(artifact)

    res = client.push(files=[artifact], target=target)
    assert res.status_code in [200, 201]

    # Test getting tags
    tags = client.get_tags(target)
    assert "v1" in tags

    # Test deleting not-existence tag
    assert not client.delete_tags(target, "v1-boop-boop")
    assert "v1" in client.delete_tags(target, "v1")
    tags = client.get_tags(target)
    assert not tags


def test_get_many_tags():
    """
    Test getting many tags
    """
    client = oras.client.OrasClient(hostname="ghcr.io", insecure=False)

    # Test getting tags with a limit set
    tags = client.get_tags(
        "channel-mirrors/conda-forge/linux-aarch64/arrow-cpp", N=1005
    )
    assert len(tags) == 1005

    # This should retrieve all tags (defaults to None)
    tags = client.get_tags("channel-mirrors/conda-forge/linux-aarch64/arrow-cpp")
    assert len(tags) > 1500

    # Same result if explicitly set
    same_tags = client.get_tags(
        "channel-mirrors/conda-forge/linux-aarch64/arrow-cpp", N=None
    )
    assert not set(tags).difference(set(same_tags))

    # Small number of tags
    tags = client.get_tags("channel-mirrors/conda-forge/linux-aarch64/arrow-cpp", N=10)
    assert not set(tags).difference(set(same_tags))
    assert len(tags) == 10


@pytest.mark.skipif(with_auth, reason="token auth is needed for push and pull")
def test_directory_push_pull(tmp_path):
    """
    Test push and pull for directory
    """
    client = oras.client.OrasClient(hostname=registry, insecure=True)

    # Test upload of a directory
    upload_dir = os.path.join(here, "upload_data")
    res = client.push(files=[upload_dir], target=target_dir)
    assert res.status_code == 201
    files = client.pull(target=target_dir, outdir=tmp_path)

    assert len(files) == 1
    assert os.path.basename(files[0]) == "upload_data"
    assert str(tmp_path) in files[0]
    assert os.path.exists(files[0])
    assert "artifact.txt" in os.listdir(files[0])
