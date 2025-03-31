__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import os
import shutil
import time
from pathlib import Path

import pytest
from requests.exceptions import SSLError

import oras.client

here = os.path.abspath(os.path.dirname(__file__))


def test_basic_oras(registry):
    """
    Basic tests for oras (without authentication)
    """
    client = oras.client.OrasClient(hostname=registry, insecure=True)
    assert "Python version" in client.version()


@pytest.mark.with_auth(True)
def test_login_logout(registry, credentials):
    """
    Login and logout are all we can test with basic auth!
    """
    client = oras.client.OrasClient(hostname=registry, tls_verify=False)
    res = client.login(
        hostname=registry,
        tls_verify=False,
        username=credentials.user,
        password=credentials.password,
    )
    assert res["Status"] == "Login Succeeded"
    client.logout(registry)


@pytest.mark.with_auth(False)
def test_basic_push_pull(tmp_path, registry, credentials, target):
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


@pytest.mark.with_auth(False)
def test_basic_push_pul_via_sha_ref(tmp_path, registry, credentials, target):
    """
    Basic tests for oras pushing and then pulling with SHA reference
    """
    client = oras.client.OrasClient(hostname=registry, insecure=True)
    artifact = os.path.join(here, "artifact.txt")

    assert os.path.exists(artifact)

    res = client.push(files=[artifact], target=target)
    assert res.status_code in [200, 201]

    # Test pulling elsewhere
    using_ref = f"{registry}/dinosaur/artifact@{res.headers['Docker-Content-Digest']}"
    files = client.pull(target=using_ref, outdir=tmp_path)
    assert len(files) == 1
    assert os.path.basename(files[0]) == "artifact.txt"
    assert str(tmp_path) in files[0]
    assert os.path.exists(files[0])


@pytest.mark.with_auth(False)
def test_get_delete_tags(tmp_path, registry, credentials, target):
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


@pytest.mark.with_auth(False)
def test_directory_push_pull(tmp_path, registry, credentials, target_dir):
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


@pytest.mark.with_auth(True)
def test_directory_push_pull_selfsigned_auth(
    tmp_path, registry, credentials, target_dir
):
    """
    Test push and pull for directory using a self-signed cert registry (`tls_verify=False`) and basic auth (`auth_backend="basic"`)
    """
    client = oras.client.OrasClient(
        hostname=registry, tls_verify=False, auth_backend="basic"
    )
    res = client.login(
        hostname=registry,
        tls_verify=False,
        username=credentials.user,
        password=credentials.password,
    )
    assert res["Status"] == "Login Succeeded"

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


@pytest.mark.with_auth(True)
def test_custom_docker_config_path(tmp_path, registry, credentials, target_dir):
    """
    Custom docker config_path for login, push, pull
    """
    my_dockercfg_path = tmp_path / "myconfig.json"
    client = oras.client.OrasClient(
        hostname=registry, tls_verify=False, auth_backend="basic"
    )
    res = client.login(
        hostname=registry,
        tls_verify=False,
        username=credentials.user,
        password=credentials.password,
        config_path=my_dockercfg_path,  # <-- for login
    )
    assert res["Status"] == "Login Succeeded"

    # Test push/pull with custom docker config_path
    upload_dir = os.path.join(here, "upload_data")
    res = client.push(
        files=[upload_dir], target=target_dir, config_path=my_dockercfg_path
    )
    assert res.status_code == 201

    files = client.pull(
        target=target_dir, outdir=tmp_path, config_path=my_dockercfg_path
    )
    assert len(files) == 1
    assert os.path.basename(files[0]) == "upload_data"
    assert str(tmp_path) in files[0]
    assert os.path.exists(files[0])
    assert "artifact.txt" in os.listdir(files[0])

    client.logout(registry)


@pytest.fixture
def empty_request_ca():
    old_ca = os.environ.get("REQUESTS_CA_BUNDLE", None)
    try:
        # we're setting a fake CA since an empty one won't work
        os.environ["REQUESTS_CA_BUNDLE"] = str(Path(__file__).parent / "snakeoil.crt")
        yield
    finally:
        if old_ca is not None:
            os.environ["REQUESTS_CA_BUNDLE"] = old_ca
        else:
            del os.environ["REQUESTS_CA_BUNDLE"]


def test_ssl_no_verify(empty_request_ca):
    """
    Make sure the client works without a CA file and tls_verify set to False
    """
    client = oras.client.OrasClient(
        hostname="ghcr.io", insecure=False, tls_verify=False
    )
    client.get_tags("channel-mirrors/conda-forge/linux-aarch64/arrow-cpp", N=1)


def test_ssl_verify_fails_if_bad_ca(empty_request_ca):
    """
    Make sure the client fails without a CA file and tls_verify set to True
    """
    client = oras.client.OrasClient(hostname="ghcr.io", insecure=False, tls_verify=True)

    with pytest.raises(SSLError):
        client.get_tags("channel-mirrors/conda-forge/linux-aarch64/arrow-cpp", N=1)


def test_ssl_verify_fails_fast_if_bad_ca(empty_request_ca):
    """
    The client should fail fast in case of SSL errors
    """
    client = oras.client.OrasClient(hostname="ghcr.io", insecure=False, tls_verify=True)
    st = time.monotonic()
    with pytest.raises(SSLError):
        client.get_tags("channel-mirrors/conda-forge/linux-aarch64/arrow-cpp", N=1)
    et = time.monotonic()
    assert et - st < 5
