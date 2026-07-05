__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import oras.client
import oras.defaults
import oras.oci
import oras.provider
import oras.utils
from oras.copy.options import CopyOptions
from oras.layout import Layout

here = Path(__file__).resolve().parent


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


@pytest.mark.with_auth(False)
def test_file_contains_column(tmp_path, registry, credentials, target):
    """
    Test for file containing column symbol
    """
    client = oras.client.OrasClient(hostname=registry, insecure=True)
    artifact = os.path.join(here, "artifact.txt")
    assert os.path.exists(artifact)

    # file containing `:`
    try:
        contains_column = here / "some:file"
        with open(contains_column, "w") as f:
            f.write("hello world some:file")

        res = client.push(files=[contains_column], target=target)
        assert res.status_code in [200, 201]

        files = client.pull(target, outdir=tmp_path / "download")
        download = str(tmp_path / "download/some:file")
        assert download in files
        assert oras.utils.get_file_hash(
            str(contains_column)
        ) == oras.utils.get_file_hash(download)
    finally:
        contains_column.unlink()

    # file containing `:` as prefix, pushed with type
    try:
        contains_column = here / ":somefile"
        with open(contains_column, "w") as f:
            f.write("hello world :somefile")

        res = client.push(files=[f"{contains_column}:text/plain"], target=target)
        assert res.status_code in [200, 201]

        files = client.pull(target, outdir=tmp_path / "download")
        download = str(tmp_path / "download/:somefile")
        assert download in files
        assert oras.utils.get_file_hash(
            str(contains_column)
        ) == oras.utils.get_file_hash(download)
    finally:
        contains_column.unlink()

    # error: file does not exist
    with pytest.raises(FileNotFoundError):
        client.push(files=[".doesnotexist"], target=target)

    with pytest.raises(FileNotFoundError):
        client.push(files=[":doesnotexist"], target=target)

    with pytest.raises(FileNotFoundError, match=r".*does:not:exists .*"):
        client.push(files=["does:not:exists:text/plain"], target=target)

    with pytest.raises(FileNotFoundError, match=r".*does:not:exists .*"):
        client.push(files=["does:not:exists:text/plain+ext"], target=target)


@pytest.mark.with_auth(False)
def test_chunked_push(tmp_path, registry, credentials, target):
    """
    Basic tests for oras chunked push
    """
    # Direct access to registry functions
    client = oras.client.OrasClient(hostname=registry, insecure=True)
    artifact = os.path.join(here, "artifact.txt")

    assert os.path.exists(artifact)

    res = client.push(files=[artifact], target=target, do_chunked=True)
    assert res.status_code in [200, 201, 202]

    files = client.pull(target, outdir=tmp_path)
    assert str(tmp_path / "artifact.txt") in files
    assert oras.utils.get_file_hash(artifact) == oras.utils.get_file_hash(files[0])

    # large file upload
    base_size = oras.defaults.default_chunksize * 1024  # 16GB
    tmp_chunked = here / "chunked"
    try:
        subprocess.run(
            [
                "dd",
                "if=/dev/null",
                f"of={tmp_chunked}",
                "bs=1",
                "count=0",
                f"seek={base_size}",
            ],
        )

        res = client.push(
            files=[tmp_chunked],
            target=target,
            do_chunked=True,
        )
        assert res.status_code in [200, 201, 202]

        files = client.pull(target, outdir=tmp_path / "download")
        download = str(tmp_path / "download/chunked")
        assert download in files
        assert oras.utils.get_file_hash(str(tmp_chunked)) == oras.utils.get_file_hash(
            download
        )
    finally:
        tmp_chunked.unlink()

    # File that doesn't exist
    with pytest.raises(FileNotFoundError):
        res = client.push(files=[tmp_path / "none"], target=target)


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


# ---------------------------------------------------------------------------
# Tests: Registry.copy — unit (mock-based)
# ---------------------------------------------------------------------------


def test_copy_calls_copy_engine():
    """
    Registry.copy() should resolve src/dst refs and invoke the copy engine.
    Verified using a mock copy_fn that captures arguments.
    """
    remote = oras.provider.Registry(insecure=True)

    captured = {}

    def fake_copy(src_target, src_ref, dst_target, dst_ref, opts):
        captured["src_ref"] = src_ref
        captured["dst_ref"] = dst_ref
        captured["src_target"] = src_target
        captured["dst_target"] = dst_target
        return {"mediaType": "application/vnd.oci.image.manifest.v1+json", "digest": "sha256:abc", "size": 42}

    with patch("oras.provider.copy_fn", side_effect=fake_copy):
        result = remote.copy(
            "registry.example.com/user/repo:v1.0",
            "registry.example.com/user/other:v2.0",
        )

    assert captured["src_ref"] == "v1.0"
    assert captured["dst_ref"] == "v2.0"
    assert result["digest"] == "sha256:abc"


def test_copy_uses_digest_ref_when_present():
    """When src contains a digest, that digest becomes src_ref (not the tag)."""
    remote = oras.provider.Registry(insecure=True)

    captured = {}

    def fake_copy(src_target, src_ref, dst_target, dst_ref, opts):
        captured["src_ref"] = src_ref
        captured["dst_ref"] = dst_ref
        return {"digest": "sha256:deadbeef", "size": 0, "mediaType": ""}

    with patch("oras.provider.copy_fn", side_effect=fake_copy):
        remote.copy(
            "registry.example.com/user/repo@sha256:deadbeef",
            "registry.example.com/user/other:stable",
        )

    assert captured["src_ref"] == "sha256:deadbeef"
    assert captured["dst_ref"] == "stable"


def test_copy_passes_opts_to_engine():
    """opts kwarg is forwarded unchanged to the copy engine."""
    remote = oras.provider.Registry(insecure=True)
    opts = CopyOptions()

    captured = {}

    def fake_copy(src_target, src_ref, dst_target, dst_ref, received_opts):
        captured["opts"] = received_opts
        return {"digest": "sha256:x", "size": 0, "mediaType": ""}

    with patch("oras.provider.copy_fn", side_effect=fake_copy):
        remote.copy(
            "registry.example.com/user/repo:v1",
            "registry.example.com/user/other:v1",
            opts=opts,
        )

    assert captured["opts"] is opts


# ---------------------------------------------------------------------------
# Tests: Registry.push / pull — unit (mock-based, no live registry)
# ---------------------------------------------------------------------------


def test_pull_returns_empty_for_index_without_downloading(tmp_path):
    """
    Pulling a reference whose manifest has no layers (e.g. an image index)
    returns [] and must NOT copy the content DAG (no multi-arch over-fetch).
    """
    remote = oras.provider.Registry(insecure=True)

    index_manifest = {
        "mediaType": "application/vnd.oci.image.index.v1+json",
        "manifests": [
            {
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "digest": "sha256:abc",
                "size": 10,
            }
        ],
    }

    with patch.object(
        oras.provider.Registry, "get_manifest", return_value=index_manifest
    ), patch("oras.layout.Layout.copy_from_registry") as mock_copy:
        files = remote.pull(
            "registry.example.com/user/repo:v1", outdir=str(tmp_path)
        )

    assert files == []
    mock_copy.assert_not_called()


def test_pack_files_to_layout_roundtrip(tmp_path):
    """
    _pack_files_to_layout writes the layer, config, and manifest blobs into an
    OCI layout and tags the manifest, without any registry interaction.
    """
    remote = oras.provider.Registry(insecure=True)

    artifact = tmp_path / "hello.txt"
    artifact.write_text("hello world")

    layout = Layout(str(tmp_path / "layout"), validate=False)
    target = layout.as_target()

    manifest_desc = remote._pack_files_to_layout(
        target,
        files=[str(artifact)],
        disable_path_validation=True,
        tag="v1",
    )

    # Manifest descriptor is a manifest media type and is tagged in the layout
    assert manifest_desc["mediaType"] == oras.defaults.default_manifest_media_type
    assert manifest_desc["digest"].startswith("sha256:")
    assert target.resolve("v1")["digest"] == manifest_desc["digest"]

    # The manifest has one layer (our file) plus a config, all present on disk
    manifest = oras.utils.read_json(
        str(layout.digest_to_blob_path(manifest_desc["digest"]))
    )
    assert len(manifest["layers"]) == 1
    layer = manifest["layers"][0]
    assert layer["annotations"][oras.defaults.annotation_title] == "hello.txt"
    assert layout.blob_exists(layer["digest"])
    assert layout.blob_exists(manifest["config"]["digest"])

    # Layer blob content matches the original file byte-for-byte
    assert (
        layout.digest_to_blob_path(layer["digest"]).read_bytes() == b"hello world"
    )


def test_push_returns_manifest_put_response(tmp_path):
    """
    push() routes through the copy engine and returns the real manifest PUT
    response captured by the RegistryTarget (not a follow-up GET).
    """
    remote = oras.provider.Registry(insecure=True)

    artifact = tmp_path / "a.txt"
    artifact.write_text("hi")

    put_response = MagicMock()
    put_response.status_code = 201

    def fake_copy(src, src_ref, dst, dst_ref, opts):
        # Emulate the engine's atomic push+tag, which records the PUT response.
        dst.last_manifest_response = put_response
        return {
            "mediaType": oras.defaults.default_manifest_media_type,
            "digest": "sha256:deadbeef",
            "size": 1,
        }

    with patch("oras.provider.copy_fn", side_effect=fake_copy):
        response = remote.push(
            files=[str(artifact)],
            target="registry.example.com/user/repo:v1",
            disable_path_validation=True,
        )

    assert response is put_response
    assert response.status_code == 201


# ---------------------------------------------------------------------------
# Tests: Registry.copy — integration (requires live registry)
# ---------------------------------------------------------------------------


@pytest.mark.with_auth(False)
def test_copy_registry_to_registry(
    registry, credentials, target_copy_src, target_copy_dst, tmp_path
):
    """
    Push an artifact, copy it to a new tag, pull from the copy and verify bytes.
    Requires running registry (ORAS_HOST and ORAS_PORT env variables).
    """
    artifact = os.path.join(here, "artifact.txt")
    assert os.path.exists(artifact)

    client = oras.client.OrasClient(hostname=registry, insecure=True)
    remote = oras.provider.Registry(insecure=True)

    # Push source artifact
    res = client.push(files=[artifact], target=target_copy_src)
    assert res.status_code in [200, 201]

    # Copy to destination
    root = remote.copy(target_copy_src, target_copy_dst)
    assert root is not None
    assert "digest" in root

    # Pull from destination and verify content matches source
    files = client.pull(target_copy_dst, outdir=str(tmp_path))
    assert files, "No files pulled from copy destination"
    pulled = str(tmp_path / "artifact.txt")
    assert pulled in files
    assert oras.utils.get_file_hash(artifact) == oras.utils.get_file_hash(pulled)
