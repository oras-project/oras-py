__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import os
from pathlib import Path

import pytest

import oras.client
import oras.defaults
import oras.provider
import oras.utils

here = os.path.abspath(os.path.dirname(__file__))


@pytest.mark.with_auth(False)
def test_annotated_registry_push(tmp_path, registry, credentials, target):
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


def test_parse_manifest(registry):
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


def test_sanitize_path():
    HOME_DIR = str(Path.home())
    assert str(oras.utils.sanitize_path(HOME_DIR, HOME_DIR)) == f"{HOME_DIR}"
    assert (
        str(oras.utils.sanitize_path(HOME_DIR, os.path.join(HOME_DIR, "username")))
        == f"{HOME_DIR}/username"
    )
    assert (
        str(oras.utils.sanitize_path(HOME_DIR, os.path.join(HOME_DIR, ".", "username")))
        == f"{HOME_DIR}/username"
    )

    with pytest.raises(Exception) as e:
        assert oras.utils.sanitize_path(HOME_DIR, os.path.join(HOME_DIR, ".."))
    assert (
        str(e.value)
        == f"Filename {Path(os.path.join(HOME_DIR, '..')).resolve()} is not in {HOME_DIR} directory"
    )

    assert oras.utils.sanitize_path("", "") == str(Path(".").resolve())
    assert oras.utils.sanitize_path("/opt", os.path.join("/opt", "image_name")) == str(
        Path("/opt/image_name").resolve()
    )
    assert oras.utils.sanitize_path("/../../", "/") == str(Path("/").resolve())
    assert oras.utils.sanitize_path(
        Path(os.getcwd()).parent.absolute(), os.path.join(os.getcwd(), "..")
    ) == str(Path("..").resolve())

    with pytest.raises(Exception) as e:
        assert oras.utils.sanitize_path(
            Path(os.getcwd()).parent.absolute(), os.path.join(os.getcwd(), "..", "..")
        ) != str(Path("../..").resolve())
    assert (
        str(e.value)
        == f"Filename {Path(os.path.join(os.getcwd(), '..', '..')).resolve()} is not in {Path('../').resolve()} directory"
    )
