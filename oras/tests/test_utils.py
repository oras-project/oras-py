__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import json
import os
import pathlib
import shutil

import pytest

import oras.utils as utils


def test_write_read_files(tmp_path):
    print("Testing utils.write_file...")

    tmpfile = str(tmp_path / "written_file.txt")
    assert not os.path.exists(tmpfile)
    utils.write_file(tmpfile, "hello!")
    assert os.path.exists(tmpfile)

    print("Testing utils.read_file...")

    content = utils.read_file(tmpfile)
    assert content == "hello!"


def test_workdir(tmp_path):
    print("Testing utils.workdir")
    noodle_base = os.path.join(tmp_path, "noodles")
    os.makedirs(noodle_base)
    pathlib.Path(os.path.join(noodle_base, "pasta.txt")).touch()
    assert "pasta.txt" not in os.listdir()
    with utils.workdir(noodle_base):
        assert "pasta.txt" in os.listdir()


def test_write_bad_json(tmp_path):
    bad_json = {"Wakkawakkawakka'}": [{True}, "2", 3]}
    tmpfile = str(tmp_path / "json_file.txt")
    assert not os.path.exists(tmpfile)
    with pytest.raises(TypeError):
        utils.write_json(bad_json, tmpfile)


def test_write_json(tmp_path):
    good_json = {"Wakkawakkawakka": [True, "2", 3]}
    tmpfile = str(tmp_path / "good_json_file.txt")

    assert not os.path.exists(tmpfile)
    utils.write_json(good_json, tmpfile)
    with open(tmpfile, "r") as f:
        content = json.loads(f.read())
    assert isinstance(content, dict)
    assert "Wakkawakkawakka" in content
    content = utils.read_json(tmpfile)
    assert "Wakkawakkawakka" in content


def test_copyfile(tmp_path):
    print("Testing utils.copyfile")

    original = str(tmp_path / "location1.txt")
    dest = str(tmp_path / "location2.txt")
    print(original)
    print(dest)
    utils.write_file(original, "CONTENT IN FILE")
    utils.copyfile(original, dest)
    assert os.path.exists(original)
    assert os.path.exists(dest)


def test_get_tmpdir_tmpfile():
    print("Testing utils.get_tmpdir, get_tmpfile")

    tmpdir = utils.get_tmpdir()
    assert os.path.exists(tmpdir)
    assert os.path.basename(tmpdir).startswith("oras")
    shutil.rmtree(tmpdir)
    tmpdir = utils.get_tmpdir(prefix="name")
    assert os.path.basename(tmpdir).startswith("name")
    shutil.rmtree(tmpdir)
    tmpfile = utils.get_tmpfile()
    assert "oras" in tmpfile
    os.remove(tmpfile)
    tmpfile = utils.get_tmpfile(prefix="pancakes")
    assert "pancakes" in tmpfile
    os.remove(tmpfile)


def test_mkdir_p(tmp_path):
    print("Testing utils.mkdir_p")

    dirname = str(tmp_path / "input")
    result = os.path.join(dirname, "level1", "level2", "level3")
    utils.mkdir_p(result)
    assert os.path.exists(result)


def test_print_json():
    print("Testing utils.print_json")
    result = utils.print_json({1: 1})
    assert result == '{\n    "1": 1\n}'


def test_split_path_and_content():
    """
    Test split path and content function.

    Function has additional logic for Windows - this isn't included in these tests as
    they don't usually run on Windows.
    """
    testref = "path/to/config:application/vnd.oci.image.config.v1+json"
    path_content = utils.split_path_and_content(testref)
    assert path_content.path == "path/to/config"
    assert path_content.content == "application/vnd.oci.image.config.v1+json"

    testref = "/dev/null:application/vnd.oci.image.config.v1+json"
    path_content = utils.split_path_and_content(testref)
    assert path_content.path == "/dev/null"
    assert path_content.content == "application/vnd.oci.image.config.v1+json"

    testref = "/dev/null"
    path_content = utils.split_path_and_content(testref)
    assert path_content.path == "/dev/null"
    assert not path_content.content

    testref = "path/to/config.json"
    path_content = utils.split_path_and_content(testref)
    assert path_content.path == "path/to/config.json"
    assert not path_content.content
