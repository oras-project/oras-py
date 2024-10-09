__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import os
import subprocess
from pathlib import Path

import pytest

import oras.client
import oras.defaults
import oras.oci
import oras.provider
import oras.utils

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
