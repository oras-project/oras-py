__author__ = "Matteo Mortari"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import pathlib

import pytest

import oras.client
import oras.provider
import oras.utils as utils
from oras.layout import Layout, NewLayout


def test_validate_oci_layout_valid_minimal(tmp_path):
    """Test validation of valid OCI layout with minimal required fields"""
    layout_dir = tmp_path / "layout"
    layout_dir.mkdir()

    # blobs directory
    (layout_dir / "blobs").mkdir()

    # valid oci-layout file
    oci_layout = {"imageLayoutVersion": "1.0.0"}
    utils.write_json(oci_layout, str(layout_dir / "oci-layout"))

    # valid index.json
    index = {"schemaVersion": 2}
    utils.write_json(index, str(layout_dir / "index.json"))

    assert Layout(str(layout_dir))


def test_new_layout_courtesy_function(tmp_path):
    """Test NewLayout courtesy function creates Layout instance"""
    layout_dir = tmp_path / "layout"
    layout_dir.mkdir()

    # blobs directory
    (layout_dir / "blobs").mkdir()

    # valid oci-layout file
    oci_layout = {"imageLayoutVersion": "1.0.0"}
    utils.write_json(oci_layout, str(layout_dir / "oci-layout"))

    # valid index.json
    index = {"schemaVersion": 2}
    utils.write_json(index, str(layout_dir / "index.json"))

    # Use NewLayout instead of Layout constructor
    layout = NewLayout(str(layout_dir))
    assert layout
    assert isinstance(layout, Layout)


def test_validate_oci_layout_valid_with_additional_fields(tmp_path):
    """Test validation of valid OCI layout with additional fields"""
    layout_dir = tmp_path / "layout"
    layout_dir.mkdir()

    # blobs directory
    (layout_dir / "blobs").mkdir()

    # oci-layout file with additional fields
    oci_layout = {"imageLayoutVersion": "1.0.0", "customField": "customValue"}
    utils.write_json(oci_layout, str(layout_dir / "oci-layout"))

    # index.json with additional fields
    index = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.index.v1+json",
        "manifests": [],
        "annotations": {"custom": "annotation"},
    }
    utils.write_json(index, str(layout_dir / "index.json"))

    assert Layout(str(layout_dir))


def test_validate_oci_layout_rejects_non_pinned_versions(tmp_path):
    """Test validation fails for versions other than the pinned version 1.0.0"""
    layout_dir = tmp_path / "layout"
    layout_dir.mkdir()

    # blobs directory
    (layout_dir / "blobs").mkdir()

    # oci-layout file will be done below
    # valid index.json
    index = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.index.v1+json",
    }
    utils.write_json(index, str(layout_dir / "index.json"))

    # Test various versions that should be rejected (only "1.0.0" is accepted)
    invalid_versions = ["1.0", "1.1.0", "1.2.3", "1.0.0-rc1", "1.0.1"]

    for version in invalid_versions:
        oci_layout = {"imageLayoutVersion": version}
        utils.write_json(oci_layout, str(layout_dir / "oci-layout"))

        with pytest.raises(ValueError) as exc_info:
            Layout(str(layout_dir))
        assert "imageLayoutVersion" in str(exc_info.value)
        assert "1.0.0" in str(exc_info.value)


def test_validate_oci_layout_nonexistent_path(tmp_path):
    """Test validation fails for non-existent path"""
    nonexistent = tmp_path / "does_not_exist"
    with pytest.raises(FileNotFoundError) as exc_info:
        Layout(str(nonexistent))
    assert "does not exist" in str(exc_info.value).lower()


def test_validate_oci_layout_path_is_file(tmp_path):
    """Test validation fails when path is a file, not a directory"""
    test_file = tmp_path / "file.txt"
    test_file.write_text("not a directory")

    with pytest.raises(ValueError) as exc_info:
        Layout(str(test_file))
    assert "not a directory" in str(exc_info.value).lower()


def test_validate_oci_layout_missing_oci_layout_file(tmp_path):
    """Test validation fails when oci-layout file is missing"""
    layout_dir = tmp_path / "layout"
    layout_dir.mkdir()

    # blobs directory
    (layout_dir / "blobs").mkdir()

    # only index.json, not oci-layout
    index = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.index.v1+json",
    }
    utils.write_json(index, str(layout_dir / "index.json"))

    with pytest.raises(FileNotFoundError) as exc_info:
        Layout(str(layout_dir))
    assert "oci-layout" in str(exc_info.value)
    assert "not found" in str(exc_info.value).lower()


def test_validate_oci_layout_invalid_json_in_oci_layout(tmp_path):
    """Test validation fails when oci-layout contains invalid JSON"""
    layout_dir = tmp_path / "layout"
    layout_dir.mkdir()

    # blobs directory
    (layout_dir / "blobs").mkdir()

    # invalid JSON to oci-layout
    oci_layout_file = layout_dir / "oci-layout"
    oci_layout_file.write_text("{invalid json")

    index = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.index.v1+json",
    }
    utils.write_json(index, str(layout_dir / "index.json"))

    with pytest.raises(ValueError) as exc_info:
        Layout(str(layout_dir))
    assert "oci-layout" in str(exc_info.value)
    assert "not valid JSON" in str(exc_info.value)


def test_validate_oci_layout_oci_layout_not_object(tmp_path):
    """Test validation fails when oci-layout is not a JSON object"""
    layout_dir = tmp_path / "layout"
    layout_dir.mkdir()

    # blobs directory
    (layout_dir / "blobs").mkdir()

    # JSON array instead of object in oci-layout file
    oci_layout_file = layout_dir / "oci-layout"
    oci_layout_file.write_text('["not", "an", "object"]')

    index = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.index.v1+json",
    }
    utils.write_json(index, str(layout_dir / "index.json"))

    with pytest.raises(ValueError) as exc_info:
        Layout(str(layout_dir))
    assert "oci-layout" in str(exc_info.value)
    assert "JSON object" in str(exc_info.value)


def test_validate_oci_layout_missing_imageLayoutVersion(tmp_path):
    """Test validation fails when imageLayoutVersion property is missing"""
    layout_dir = tmp_path / "layout"
    layout_dir.mkdir()

    # blobs directory
    (layout_dir / "blobs").mkdir()

    # oci-layout without imageLayoutVersion
    oci_layout = {"someOtherField": "value"}
    utils.write_json(oci_layout, str(layout_dir / "oci-layout"))

    index = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.index.v1+json",
    }
    utils.write_json(index, str(layout_dir / "index.json"))

    with pytest.raises(ValueError) as exc_info:
        Layout(str(layout_dir))
    assert "imageLayoutVersion" in str(exc_info.value)


def test_validate_oci_layout_version_not_string(tmp_path):
    """Test validation fails when imageLayoutVersion is not a string"""
    layout_dir = tmp_path / "layout"
    layout_dir.mkdir()

    # blobs directory
    (layout_dir / "blobs").mkdir()

    # oci-layout file with non-string version
    oci_layout = {"imageLayoutVersion": 1.0}
    utils.write_json(oci_layout, str(layout_dir / "oci-layout"))

    index = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.index.v1+json",
    }
    utils.write_json(index, str(layout_dir / "index.json"))

    with pytest.raises(ValueError) as exc_info:
        Layout(str(layout_dir))
    assert "imageLayoutVersion" in str(exc_info.value)
    assert "string" in str(exc_info.value)


def test_validate_oci_layout_missing_index_json(tmp_path):
    """Test validation fails when index.json file is missing"""
    layout_dir = tmp_path / "layout"
    layout_dir.mkdir()

    # blobs directory
    (layout_dir / "blobs").mkdir()

    # only oci-layout, not index.json
    oci_layout = {"imageLayoutVersion": "1.0.0"}
    utils.write_json(oci_layout, str(layout_dir / "oci-layout"))

    with pytest.raises(FileNotFoundError) as exc_info:
        Layout(str(layout_dir))
    assert "index.json" in str(exc_info.value)
    assert "not found" in str(exc_info.value).lower()


def test_validate_oci_layout_invalid_json_in_index(tmp_path):
    """Test validation fails when index.json contains invalid JSON"""
    layout_dir = tmp_path / "layout"
    layout_dir.mkdir()

    # blobs directory, oci-layout
    (layout_dir / "blobs").mkdir()
    oci_layout = {"imageLayoutVersion": "1.0.0"}
    utils.write_json(oci_layout, str(layout_dir / "oci-layout"))

    # invalid JSON to index.json
    index_file = layout_dir / "index.json"
    index_file.write_text("{invalid json")

    with pytest.raises(ValueError) as exc_info:
        Layout(str(layout_dir))
    assert "index.json" in str(exc_info.value)
    assert "not valid JSON" in str(exc_info.value)


def test_validate_oci_layout_index_not_object(tmp_path):
    """Test validation fails when index.json is not a JSON object"""
    layout_dir = tmp_path / "layout"
    layout_dir.mkdir()

    # blobs directory, oci-layout
    (layout_dir / "blobs").mkdir()
    oci_layout = {"imageLayoutVersion": "1.0.0"}
    utils.write_json(oci_layout, str(layout_dir / "oci-layout"))

    # JSON array instead of object
    index_file = layout_dir / "index.json"
    index_file.write_text('["not", "an", "object"]')

    with pytest.raises(ValueError) as exc_info:
        Layout(str(layout_dir))
    assert "index.json" in str(exc_info.value)
    assert "JSON object" in str(exc_info.value)


def test_validate_oci_layout_missing_schemaVersion(tmp_path):
    """Test validation fails when schemaVersion property is missing"""
    layout_dir = tmp_path / "layout"
    layout_dir.mkdir()

    # blobs directory, oci-layout
    (layout_dir / "blobs").mkdir()
    oci_layout = {"imageLayoutVersion": "1.0.0"}
    utils.write_json(oci_layout, str(layout_dir / "oci-layout"))

    # index.json without schemaVersion
    index = {"mediaType": "application/vnd.oci.image.index.v1+json"}
    utils.write_json(index, str(layout_dir / "index.json"))

    with pytest.raises(ValueError) as exc_info:
        Layout(str(layout_dir))
    assert "schemaVersion" in str(exc_info.value)


def test_validate_oci_layout_wrong_schemaVersion(tmp_path):
    """Test validation fails when schemaVersion is not 2"""
    layout_dir = tmp_path / "layout"
    layout_dir.mkdir()

    # blobs directory, oci-layout
    (layout_dir / "blobs").mkdir()
    oci_layout = {"imageLayoutVersion": "1.0.0"}
    utils.write_json(oci_layout, str(layout_dir / "oci-layout"))

    # wrong schemaVersion
    index = {
        "schemaVersion": 1,
        "mediaType": "application/vnd.oci.image.index.v1+json",
    }
    utils.write_json(index, str(layout_dir / "index.json"))

    with pytest.raises(ValueError) as exc_info:
        Layout(str(layout_dir))
    assert "schemaVersion" in str(exc_info.value)
    assert "2" in str(exc_info.value)


def test_validate_oci_layout_without_mediaType(tmp_path):
    """Test validation succeeds when mediaType property is missing (it's optional per spec)"""
    layout_dir = tmp_path / "layout"
    layout_dir.mkdir()

    # blobs directory, oci-layout
    (layout_dir / "blobs").mkdir()
    oci_layout = {"imageLayoutVersion": "1.0.0"}
    utils.write_json(oci_layout, str(layout_dir / "oci-layout"))

    # index.json without mediaType (this is valid per OCI spec)
    index = {"schemaVersion": 2}
    utils.write_json(index, str(layout_dir / "index.json"))

    assert Layout(str(layout_dir))


def test_validate_oci_layout_unsupported_mediaType(tmp_path):
    """Test validation fails when mediaType is unsupported"""
    layout_dir = tmp_path / "layout"
    layout_dir.mkdir()

    # blobs directory, oci-layout
    (layout_dir / "blobs").mkdir()
    oci_layout = {"imageLayoutVersion": "1.0.0"}
    utils.write_json(oci_layout, str(layout_dir / "oci-layout"))

    # Test with unsupported mediaType
    index = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
    }
    utils.write_json(index, str(layout_dir / "index.json"))

    with pytest.raises(ValueError) as exc_info:
        Layout(str(layout_dir))
    assert "mediaType" in str(exc_info.value)
    assert "application/vnd.oci.image.index.v1+json" in str(exc_info.value)


def test_validate_oci_layout_missing_blobs_directory(tmp_path):
    """Test validation fails when blobs directory is missing"""
    layout_dir = tmp_path / "layout"
    layout_dir.mkdir()

    oci_layout = {"imageLayoutVersion": "1.0.0"}
    utils.write_json(oci_layout, str(layout_dir / "oci-layout"))

    index = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.index.v1+json",
    }
    utils.write_json(index, str(layout_dir / "index.json"))

    # Don't create blobs directory

    with pytest.raises(FileNotFoundError) as exc_info:
        Layout(str(layout_dir))
    assert "blobs" in str(exc_info.value).lower()
    assert "not found" in str(exc_info.value).lower()


def test_validate_oci_layout_blobs_is_file_not_directory(tmp_path):
    """Test validation fails when blobs exists but is a file, not a directory"""
    layout_dir = tmp_path / "layout"
    layout_dir.mkdir()

    oci_layout = {"imageLayoutVersion": "1.0.0"}
    utils.write_json(oci_layout, str(layout_dir / "oci-layout"))

    index = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.index.v1+json",
    }
    utils.write_json(index, str(layout_dir / "index.json"))

    # blobs as a file instead of directory
    (layout_dir / "blobs").write_text("not a directory")

    with pytest.raises(ValueError) as exc_info:
        Layout(str(layout_dir))
    assert "blobs" in str(exc_info.value).lower()
    assert "directory" in str(exc_info.value).lower()


def test_validate_oci_layout_empty_blobs_directory(tmp_path):
    """Test validation succeeds with empty blobs directory"""
    layout_dir = tmp_path / "layout"
    layout_dir.mkdir()

    oci_layout = {"imageLayoutVersion": "1.0.0"}
    utils.write_json(oci_layout, str(layout_dir / "oci-layout"))

    index = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.index.v1+json",
    }
    utils.write_json(index, str(layout_dir / "index.json"))

    # empty blobs directory
    (layout_dir / "blobs").mkdir()

    assert Layout(str(layout_dir))


def test_is_oci_layout_returns_true_for_valid(tmp_path):
    """Test is_oci_layout returns True for valid layout"""
    layout_dir = tmp_path / "layout"
    layout_dir.mkdir()

    (layout_dir / "blobs").mkdir()
    oci_layout = {"imageLayoutVersion": "1.0.0"}
    utils.write_json(oci_layout, str(layout_dir / "oci-layout"))

    index = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.index.v1+json",
    }
    utils.write_json(index, str(layout_dir / "index.json"))

    assert Layout.is_oci_layout(str(layout_dir)) is True


def test_is_oci_layout_returns_false_for_nonexistent(tmp_path):
    """Test is_oci_layout returns False for non-existent path"""
    nonexistent = tmp_path / "does_not_exist"
    assert Layout.is_oci_layout(str(nonexistent)) is False


def test_is_oci_layout_returns_false_for_missing_files(tmp_path):
    """Test is_oci_layout returns False when required files are missing"""
    layout_dir = tmp_path / "layout"
    layout_dir.mkdir()

    # Only oci-layout, not index.json
    oci_layout = {"imageLayoutVersion": "1.0.0"}
    utils.write_json(oci_layout, str(layout_dir / "oci-layout"))

    assert Layout.is_oci_layout(str(layout_dir)) is False


def test_is_oci_layout_returns_false_for_invalid_structure(tmp_path):
    """Test is_oci_layout returns False for invalid structure"""
    layout_dir = tmp_path / "layout"
    layout_dir.mkdir()

    oci_layout = {"imageLayoutVersion": "1.0.0"}
    utils.write_json(oci_layout, str(layout_dir / "oci-layout"))

    # Wrong schemaVersion
    index = {
        "schemaVersion": 1,
        "mediaType": "application/vnd.oci.image.index.v1+json",
    }
    utils.write_json(index, str(layout_dir / "index.json"))

    assert Layout.is_oci_layout(str(layout_dir)) is False


def test_is_oci_layout_returns_false_for_file_path(tmp_path):
    """Test is_oci_layout returns False when path is a file"""
    test_file = tmp_path / "file.txt"
    test_file.write_text("not a directory")

    assert Layout.is_oci_layout(str(test_file)) is False


def test_is_oci_layout_returns_false_for_missing_blobs(tmp_path):
    """Test is_oci_layout returns False when blobs directory is missing"""
    layout_dir = tmp_path / "layout"
    layout_dir.mkdir()

    oci_layout = {"imageLayoutVersion": "1.0.0"}
    utils.write_json(oci_layout, str(layout_dir / "oci-layout"))

    index = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.index.v1+json",
    }
    utils.write_json(index, str(layout_dir / "index.json"))

    # Don't create blobs directory
    assert Layout.is_oci_layout(str(layout_dir)) is False


def test_get_ordered_blobs_single_arch():
    """Test blob ordering for single-arch image"""
    layout_path = str(pathlib.Path(__file__).parent / "ocilayout_data/ocilayout1")
    blobs = Layout(layout_path).get_ordered_blobs("latest")

    # Assert exact order: layer -> config -> manifest
    assert blobs == [
        "sha256:1a88c78449cd2ce9961de409273deac250a60e55b1d8c4beef858b8618ddaba5",  # layer
        "sha256:6a315ec0732bc64a9763b6da6df8326f836c3661991c8ba3f5e83e1ad4fd57b7",  # config
        "sha256:cfcb44ade8c9b2579247ceec82c2f18bf03d956b9b2c050753b7d47d1edd369d",  # manifest
    ]
    assert (
        len(blobs) == 3
    )  # using this to sanity check as I built the oci-layout manually


def test_get_ordered_blobs_multi_arch():
    """Test blob ordering for multi-arch image index"""
    layout_path = str(pathlib.Path(__file__).parent / "ocilayout_data/ocilayout2")
    blobs = Layout(layout_path).get_ordered_blobs("latest")

    # Verify no duplicates
    # Note: layer is shared between amd64 and arm64, so appears only once
    assert len(blobs) == len(set(blobs)), "Blobs should not contain duplicates"

    # Assert exact order: amd64 (layer->config->manifest), arm64 (config->manifest), index
    assert blobs == [
        "sha256:1a88c78449cd2ce9961de409273deac250a60e55b1d8c4beef858b8618ddaba5",  # layer (shared)
        "sha256:857894c250a4fb84159019980de46d258b686bef248398a7bdec63c2fa4ad763",  # config (amd64)
        "sha256:05434dd68af92e66c28c48e357b464ae61b57c878854f2366c65236e77d5bd78",  # manifest (amd64)
        "sha256:6a315ec0732bc64a9763b6da6df8326f836c3661991c8ba3f5e83e1ad4fd57b7",  # config (arm64)
        "sha256:cfcb44ade8c9b2579247ceec82c2f18bf03d956b9b2c050753b7d47d1edd369d",  # manifest (arm64)
        "sha256:d735159cc5866be4d080e23d77b24ec8fbec115b879712c3792ca92413df8bf4",  # index
    ]
    assert (
        len(blobs) == 6
    )  # using this to sanity check as I built the oci-layout manually


def test_get_ordered_blobs_tag_not_found():
    """Test error when tag annotation is not found"""
    layout_path = str(pathlib.Path(__file__).parent / "ocilayout_data/ocilayout1")

    with pytest.raises(ValueError, match="Tag 'nonexistent' not found"):
        Layout(layout_path).get_ordered_blobs("nonexistent")


@pytest.mark.with_auth(False)
def test_push_from_layout_single_arch(
    registry, credentials, target_layout_single
):  # using `with_auth` marker requires `credentials` fixture
    """
    Test pushing single-arch OCI layout to registry.
    Requires running registry (ORAS_HOST and ORAS_PORT env variables).
    """
    layout_path = str(pathlib.Path(__file__).parent / "ocilayout_data/ocilayout1")

    # Create provider and push layout
    provider = oras.provider.Registry(insecure=True)
    response = Layout(layout_path).push_to_registry(
        provider=provider,
        target=target_layout_single,
        tag="latest",
    )

    # Verify push succeeded
    assert response.status_code in [
        200,
        201,
    ], f"Push failed with status {response.status_code}"

    # Check expected tag exists:
    client = oras.client.OrasClient(hostname=registry, insecure=True)
    ref_without_tag = target_layout_single.rsplit(":", 1)[0]
    tags = client.get_tags(ref_without_tag)
    assert "v1" in tags, "Pushed tag not found in registry"


@pytest.mark.with_auth(False)
def test_push_from_layout_multi_arch(
    registry, credentials, target_layout_multi, caplog
):  # using `with_auth` marker requires `credentials` fixture
    """
    Test pushing multi-arch OCI layout (with image index) to registry.
    Also verifies that shared blobs are only uploaded once (deduplication) via caplog.
    Requires running registry (ORAS_HOST and ORAS_PORT env variables).
    """
    import logging

    # Get path to test data
    layout_path = str(pathlib.Path(__file__).parent / "ocilayout_data/ocilayout2")

    # Enable debug logging to track blob uploads
    caplog.set_level(logging.DEBUG)

    # Create provider and push layout
    provider = oras.provider.Registry(insecure=True)
    response = Layout(layout_path).push_to_registry(
        provider=provider,
        target=target_layout_multi,
        tag="latest",
    )

    # Verify push succeeded
    assert response.status_code in [
        200,
        201,
    ], f"Push failed with status {response.status_code}"

    # Check expected tag exists:
    client = oras.client.OrasClient(hostname=registry, insecure=True)
    ref_without_tag = target_layout_multi.rsplit(":", 1)[0]
    tags = client.get_tags(ref_without_tag)
    assert "v1" in tags, "Pushed tag not found in registry"

    # Verify deduplication: shared layer should appear at most once in upload logs
    log_messages = [record.message for record in caplog.records]
    shared_layer = (
        "sha256:f64d04d7dad53e091bf339798f95eb0962ab0452f68156304eb90160e8f39f71"
    )
    upload_logs = [
        msg for msg in log_messages if shared_layer in msg and "Uploading" in msg
    ]
    assert (
        len(upload_logs) <= 1
    ), f"Shared blob should be uploaded at most once, found {len(upload_logs)}"


@pytest.mark.with_auth(False)
def test_push_from_layout_invalid_tag(
    registry, credentials
):  # using `with_auth` marker requires `credentials` fixture
    """
    Test error handling when pushing with non-existent tag from layout.
    """
    layout_path = str(pathlib.Path(__file__).parent / "ocilayout_data/ocilayout1")
    target = f"{registry}/dinosaur/layout-error:v1"

    provider = oras.provider.Registry(insecure=True)

    # Try to push with non-existent tag from layout
    with pytest.raises(ValueError, match="Tag 'nonexistent' not found"):
        Layout(layout_path).push_to_registry(
            provider=provider,
            target=target,
            tag="nonexistent",  # This tag doesn't exist in ocilayout1's index.json
        )
