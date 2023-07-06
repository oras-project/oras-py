__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import os
import sys

import pytest

import oras.client
import oras.defaults
import oras.provider
import oras.utils

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


@pytest.mark.skipif(with_auth, reason="token auth is needed for push and pull")
def test_annotated_registry_push(tmp_path):
    """
    Basic tests for oras push with annotations
    """
    # Direct access to registry functions
    remote = oras.provider.Registry(hostname=registry, insecure=True)
    client = oras.client.OrasClient(hostname=registry, insecure=True)
    artifact = os.path.join(here, "artifact.txt")

    assert os.path.exists(artifact)

    # Custom manifest annotations
    annots = {"holiday": "Halloween", "candy": "chocolate"}
    res = client.push(files=[artifact], target=target, manifest_annotations=annots)
    assert res.status_code in [200, 201]

    # Get the manifest
    manifest = remote.get_manifest(target)
    assert "annotations" in manifest
    for k, v in annots.items():
        assert k in manifest["annotations"]
        assert manifest["annotations"][k] == v

    # Annotations from file with $manifest
    annotation_file = os.path.join(here, "annotations.json")
    file_annots = oras.utils.read_json(annotation_file)
    assert "$manifest" in file_annots
    res = client.push(files=[artifact], target=target, annotation_file=annotation_file)
    assert res.status_code in [200, 201]
    manifest = remote.get_manifest(target)

    assert "annotations" in manifest
    for k, v in file_annots["$manifest"].items():
        assert k in manifest["annotations"]
        assert manifest["annotations"][k] == v

    # File that doesn't exist
    annotation_file = os.path.join(here, "annotations-nope.json")
    with pytest.raises(FileNotFoundError):
        res = client.push(
            files=[artifact], target=target, annotation_file=annotation_file
        )


def test_parse_manifest():
    """
    Test parse manifest function.

    Parse manifest function has additional logic for Windows - this isn't included in
    these tests as they don't usually run on Windows.
    """
    testref = "path/to/config:application/vnd.oci.image.config.v1+json"
    remote = oras.provider.Registry(hostname=registry, insecure=True)
    ref, content_type = remote._parse_manifest_ref(testref)
    assert ref == "path/to/config"
    assert content_type == "application/vnd.oci.image.config.v1+json"

    testref = "path/to/config:application/vnd.oci.image.config.v1+json:extra"
    remote = oras.provider.Registry(hostname=registry, insecure=True)
    ref, content_type = remote._parse_manifest_ref(testref)
    assert ref == "path/to/config"
    assert content_type == "application/vnd.oci.image.config.v1+json:extra"

    testref = "/dev/null:application/vnd.oci.image.manifest.v1+json"
    ref, content_type = remote._parse_manifest_ref(testref)
    assert ref == "/dev/null"
    assert content_type == "application/vnd.oci.image.manifest.v1+json"

    testref = "/dev/null"
    ref, content_type = remote._parse_manifest_ref(testref)
    assert ref == "/dev/null"
    assert content_type == oras.defaults.unknown_config_media_type

    testref = "path/to/config.json"
    ref, content_type = remote._parse_manifest_ref(testref)
    assert ref == "path/to/config.json"
    assert content_type == oras.defaults.unknown_config_media_type
