__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

import oras.client
import oras.defaults
import oras.oci
import oras.provider
import oras.utils

here = Path(__file__).resolve().parent


@pytest.mark.parametrize(
    "outcome", ["success", "compression_error", "upload_error", "http_error"]
)
def test_push_cleans_temporary_archive(tmp_path, monkeypatch, outcome):
    client = oras.provider.Registry(hostname="registry.example", insecure=True)
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    (artifact / "content.txt").write_text("artifact contents")
    temporary_root = tmp_path / "temporary"
    temporary_root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temporary_root))
    monkeypatch.setattr(client.auth, "load_configs", lambda *args, **kwargs: None)
    archives = []
    make_targz = oras.utils.make_targz

    def compress(source, destination=None):
        archive = make_targz(source, destination)
        archives.append(Path(archive))
        if outcome == "compression_error":
            raise OSError("compression interrupted")
        return archive

    def upload_blob(path, container, layer, **kwargs):
        if (
            layer.get("annotations", {}).get(oras.defaults.annotation_title)
            == artifact.name
        ):
            with tarfile.open(path) as archive:
                assert (
                    archive.extractfile("artifact/content.txt").read()
                    == b"artifact contents"
                )
            if outcome == "upload_error":
                raise OSError("upload interrupted")
            if outcome == "http_error":
                return Mock(status_code=500)
        return Mock(status_code=201)

    monkeypatch.setattr(oras.utils, "make_targz", compress)
    monkeypatch.setattr(client, "upload_blob", upload_blob)
    monkeypatch.setattr(client, "upload_manifest", lambda *args: Mock(status_code=201))
    if outcome == "success":
        client.push(
            "registry.example/repository:tag",
            files=[artifact],
            disable_path_validation=True,
        )
    else:
        error = ValueError if outcome == "http_error" else OSError
        with pytest.raises(error):
            client.push(
                "registry.example/repository:tag",
                files=[artifact],
                disable_path_validation=True,
            )
    assert len(archives) == 1
    assert not archives[0].exists()
    assert list(temporary_root.iterdir()) == []
    assert (artifact / "content.txt").read_text() == "artifact contents"


@pytest.mark.parametrize("use_default_outdir", [False, True])
@pytest.mark.parametrize("outcome", ["success", "download_error", "invalid_archive"])
def test_pull_cleans_temporary_archive(
    tmp_path, monkeypatch, use_default_outdir, outcome
):
    client = oras.provider.Registry(hostname="registry.example", insecure=True)

    # Archive and describe a directory the same way push does.
    target = "registry.example/repository:tag"
    content_name = "content.txt"
    content = "artifact contents"
    artifact = tmp_path / "source" / "artifact"
    artifact.mkdir(parents=True)
    (artifact / content_name).write_text(content)
    archive = oras.utils.make_targz(str(artifact), str(tmp_path / "artifact.tar.gz"))
    layer = oras.oci.NewLayer(archive, is_dir=True)
    layer["annotations"] = {oras.defaults.annotation_title: artifact.name}

    temporary_root = tmp_path / "temporary"
    temporary_root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temporary_root))
    monkeypatch.setattr(client.auth, "load_configs", lambda *args, **kwargs: None)
    monkeypatch.setattr(client, "get_manifest", lambda *args: {"layers": [layer]})
    downloads = []

    def download_blob(container, digest, destination):
        assert digest == layer["digest"]
        downloads.append(Path(destination))
        if outcome == "download_error":
            Path(destination).write_bytes(b"partial download")
            raise OSError("download interrupted")
        if outcome == "invalid_archive":
            Path(destination).write_bytes(b"invalid archive")
            return
        shutil.copyfile(archive, destination)

    monkeypatch.setattr(client, "download_blob", download_blob)
    outdir = None if use_default_outdir else str(tmp_path / "output")
    if outcome == "success":
        files = client.pull(target, outdir=outdir)
        assert len(files) == 1
        assert (Path(files[0]) / content_name).read_text() == content
    else:
        error = OSError if outcome == "download_error" else tarfile.ReadError
        with pytest.raises(error):
            client.pull(target, outdir=outdir)

    assert len(downloads) == 1
    assert not downloads[0].exists()
    assert not downloads[0].parent.exists()
    # Only the caller's implicit output directory should survive the pull.
    assert len(list(temporary_root.iterdir())) == int(use_default_outdir)


def test_push_quiet_output_does_not_write_stdout(tmp_path, monkeypatch, capsys):
    client = oras.provider.Registry(hostname="registry.example", insecure=True)
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("content")

    class Response:
        status_code = 201

    container = client.get_container("registry.example/repository:tag")
    monkeypatch.setattr(client, "get_container", lambda target: container)
    monkeypatch.setattr(client.auth, "load_configs", lambda *args, **kwargs: None)
    monkeypatch.setattr(client, "upload_blob", lambda *args, **kwargs: Response())
    monkeypatch.setattr(client, "upload_manifest", lambda *args, **kwargs: Response())
    monkeypatch.setattr(client, "_check_200_response", lambda response: None)
    info = Mock()
    monkeypatch.setattr(oras.provider.logger, "info", info)

    client.push(
        files=[artifact],
        target="registry.example/repository:tag",
        disable_path_validation=True,
        quiet=False,
    )

    assert capsys.readouterr().out == ""
    info.assert_called_once_with(f"Successfully pushed {container}")


@pytest.mark.parametrize("backend", ["docker", "fallback"])
@pytest.mark.parametrize("password_source", ["prompt", "argument", "stdin"])
def test_login_prompts_for_missing_credentials(monkeypatch, backend, password_source):
    client = oras.provider.Registry(hostname="registry.example", insecure=True)
    username_prompt = Mock(return_value="alice")
    password_prompt = Mock(return_value="secret")
    stdin = Mock(return_value="secret")
    monkeypatch.setattr("builtins.input", username_prompt)
    monkeypatch.setattr(oras.provider.getpass, "getpass", password_prompt)
    monkeypatch.setattr(oras.utils, "readline", stdin)
    set_basic_auth = Mock()
    monkeypatch.setattr(client.auth, "set_basic_auth", set_basic_auth)
    docker_client = Mock()
    docker_client.login.return_value = {"Status": "Login Succeeded"}
    get_client = Mock(return_value=docker_client)
    if backend == "fallback":
        get_client.side_effect = RuntimeError("Docker unavailable")
        monkeypatch.setattr(oras.provider.login, "DockerClient", lambda: docker_client)
    monkeypatch.setattr(oras.utils, "get_docker_client", get_client)

    kwargs = {}
    if password_source == "argument":
        kwargs["password"] = "secret"
    elif password_source == "stdin":
        kwargs["password_stdin"] = True
    if password_source == "stdin":
        kwargs["username"] = "alice"
    result = client.login(hostname="registry.example", **kwargs)

    assert result == {"Status": "Login Succeeded"}
    if password_source == "stdin":
        username_prompt.assert_not_called()
    else:
        username_prompt.assert_called_once_with("Username: ")
    if password_source == "prompt":
        password_prompt.assert_called_once_with("Password: ")
    else:
        password_prompt.assert_not_called()
    if password_source == "stdin":
        stdin.assert_called_once_with()
    else:
        stdin.assert_not_called()
    set_basic_auth.assert_called_once_with("alice", "secret")
    docker_client.login.assert_called_once_with(
        username="alice",
        password="secret",
        registry="registry.example",
        dockercfg_path=None,
    )


@pytest.mark.parametrize("username", [None, ""])
def test_login_stdin_requires_username(monkeypatch, username):
    client = oras.provider.Registry()
    stdin = Mock()
    prompt = Mock()
    get_client = Mock()
    monkeypatch.setattr(oras.utils, "readline", stdin)
    monkeypatch.setattr("builtins.input", prompt)
    monkeypatch.setattr(oras.utils, "get_docker_client", get_client)
    with pytest.raises(
        ValueError, match="username is required when password_stdin is set"
    ):
        client.login(username=username, password_stdin=True)
    stdin.assert_not_called()
    prompt.assert_not_called()
    get_client.assert_not_called()


def test_login_rejects_empty_prompted_username(monkeypatch):
    client = oras.provider.Registry()
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    get_client = Mock()
    monkeypatch.setattr(oras.utils, "get_docker_client", get_client)
    with pytest.raises(ValueError, match="username required"):
        client.login(password="secret", hostname="registry.example")
    get_client.assert_not_called()


def test_push_quiet_suppresses_completion_message(tmp_path, monkeypatch):
    client = oras.provider.Registry(hostname="registry.example", insecure=True)
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("content")

    class Response:
        status_code = 201

    container = client.get_container("registry.example/repository:tag")
    monkeypatch.setattr(client, "get_container", lambda target: container)
    monkeypatch.setattr(client.auth, "load_configs", lambda *args, **kwargs: None)
    monkeypatch.setattr(client, "upload_blob", lambda *args, **kwargs: Response())
    monkeypatch.setattr(client, "upload_manifest", lambda *args, **kwargs: Response())
    monkeypatch.setattr(client, "_check_200_response", lambda response: None)
    info = Mock()
    monkeypatch.setattr(oras.provider.logger, "info", info)

    client.push(
        files=[artifact],
        target="registry.example/repository:tag",
        disable_path_validation=True,
        quiet=True,
    )

    info.assert_not_called()


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
