__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import errno
import hashlib
import io
import json
import os
import pathlib
import re
import shutil
import stat
import sys
import tarfile
import tempfile
from contextlib import contextmanager
from typing import Generator, Optional, TextIO, Union


class PathAndOptionalContent:
    """Class for holding a path reference and optional content parsed from a string."""

    def __init__(self, path: str, content: Optional[str] = None):
        self.path = path
        self.content = content


def make_targz(source_dir: str, dest_name: Optional[str] = None) -> str:
    """
    Make a targz (compressed) archive from a source directory.
    """
    dest_name = dest_name or get_tmpfile(suffix=".tar.gz")
    with tarfile.open(dest_name, "w:gz") as tar:
        tar.add(source_dir, arcname=os.path.basename(source_dir))
    return dest_name


def sanitize_path(expected_dir, path):
    """
    Ensure a path resolves to be in the expected parent directory.

    It can be directly there or a child, but not outside it.
    We raise an error if it does not - this should not happen
    """
    # It's OK to pull to PWD exactly
    if os.path.abspath(expected_dir) == os.path.abspath(path):
        return os.path.abspath(expected_dir)
    base_dir = pathlib.Path(expected_dir)
    test_path = (base_dir / path).resolve()
    if not base_dir.resolve() in test_path.resolve().parents:
        raise Exception(f"Filename {test_path} is not in {base_dir} directory")
    return str(test_path.resolve())


@contextmanager
def workdir(dirname):
    """
    Provide context for a working directory, e.g.,

    with workdir(name):
       # do stuff
    """
    here = os.getcwd()
    os.chdir(dirname)
    try:
        yield
    finally:
        os.chdir(here)


def readline() -> str:
    """
    Read lines from stdin
    """
    content = sys.stdin.readlines()
    return content[0].strip()


def extract_targz(targz: str, outdir: str, numeric_owner: bool = False):
    """
    Extract a .tar.gz to an output directory.
    """
    with tarfile.open(targz, "r:gz") as tar:
        for member in tar.getmembers():
            member_path = os.path.join(outdir, member.name)
            if not is_within_directory(outdir, member_path):
                raise Exception("Attempted Path Traversal in Tar File")
        tar.extractall(outdir, members=None, numeric_owner=numeric_owner)


def is_within_directory(directory: str, target: str) -> bool:
    """
    Determine whether a file is within a directory
    """
    abs_directory = os.path.abspath(directory)
    abs_target = os.path.abspath(target)
    prefix = os.path.commonprefix([abs_directory, abs_target])
    return prefix == abs_directory


def get_size(path: str) -> int:
    """
    Get the size of a blob

    :param path : the path to get the size for
    :type path: str
    """
    return pathlib.Path(path).stat().st_size


def get_file_hash(path: str, algorithm: str = "sha256") -> str:
    """
    Return an sha256 hash of the file based on an algorithm
    Raises AttributeError if incorrect algorithm supplied.

    :param path: the path to get the size for
    :type path: str
    :param algorithm: the algorithm to use
    :type algorithm: str
    """
    hasher = getattr(hashlib, algorithm)()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def mkdir_p(path: str):
    """
    Make a directory path if it does not exist, akin to mkdir -p

    :param path : the path to create
    :type path: str
    """
    try:
        os.makedirs(path)
    except OSError as e:
        if e.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise ValueError(f"Error creating path {path}.")


def get_tmpfile(
    tmpdir: Optional[str] = None, prefix: str = "", suffix: str = ""
) -> str:
    """
    Get a temporary file with an optional prefix.

    :param tmpdir : an optional temporary directory
    :type tmpdir: str
    :param prefix: an optional prefix for the temporary path
    :type prefix: str
    :param suffix: an optional suffix (extension)
    :type suffix: str
    """
    # First priority for the base goes to the user requested.
    tmpdir = get_tmpdir(tmpdir)

    # If tmpdir is set, add to prefix
    if tmpdir:
        prefix = os.path.join(tmpdir, os.path.basename(prefix))

    fd, tmp_file = tempfile.mkstemp(prefix=prefix, suffix=suffix)
    os.close(fd)

    return tmp_file


def get_tmpdir(
    tmpdir: Optional[str] = None, prefix: Optional[str] = "", create: bool = True
) -> str:
    """
    Get a temporary directory for an operation.

    :param tmpdir: an optional temporary directory
    :type tmpdir: str
    :param prefix: an optional prefix for the temporary path
    :type prefix: str
    :param create: create the directory
    :type create: bool
    """
    tmpdir = tmpdir or tempfile.gettempdir()
    prefix = prefix or "oras-tmp"
    prefix = "%s.%s" % (prefix, next(tempfile._get_candidate_names()))  # type: ignore
    tmpdir = os.path.join(tmpdir, prefix)

    if not os.path.exists(tmpdir) and create is True:
        os.mkdir(tmpdir)

    return tmpdir


def recursive_find(base: str, pattern: str = None) -> Generator:
    """
    Find filenames that match a particular pattern, and yield them.

    :param base    : the root to search
    :type base: str
    :param pattern: an optional file pattern to use with fnmatch
    :type pattern: str
    """
    # We can identify modules by finding module.lua
    for root, folders, files in os.walk(base):
        for file in files:
            fullpath = os.path.abspath(os.path.join(root, file))

            if pattern and not re.search(pattern, fullpath):
                continue

            yield fullpath


def copyfile(source: str, destination: str, force: bool = True) -> str:
    """
    Copy a file from a source to its destination.

    :param source: the source to copy from
    :type source: str
    :param destination: the destination to copy to
    :type destination: str
    :param force: force copy if destination already exists
    :type force: bool
    """
    # Case 1: It's already there, we aren't replacing it :)
    if source == destination and force is False:
        return destination

    # Case 2: It's already there, we ARE replacing it :)
    if os.path.exists(destination) and force is True:
        os.remove(destination)

    shutil.copyfile(source, destination)
    return destination


def write_file(
    filename: str, content: str, mode: str = "w", make_exec: bool = False
) -> str:
    """
    Write content to a filename

    :param filename: filname to write
    :type filename: str
    :param content: content to write
    :type content: str
    :param mode: mode to write
    :type mode: str
    :param make_exec: make executable
    :type make_exec: bool
    """
    with open(filename, mode) as filey:
        filey.writelines(content)
    if make_exec:
        st = os.stat(filename)

        # Execute / search permissions for the user and others
        os.chmod(filename, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return filename


def read_in_chunks(image: Union[TextIO, io.BufferedReader], chunk_size: int = 1024):
    """
    Helper function to read file in chunks, with default size 1k.

    :param image: file descriptor
    :type image: TextIO or io.BufferedReader
    :param chunk_size: size of the chunk
    :type chunk_size: int
    """
    while True:
        data = image.read(chunk_size)
        if not data:
            break
        yield data


def write_json(json_obj: dict, filename: str, mode: str = "w") -> str:
    """
    Write json to a filename

    :param json_obj: json object to write
    :type json_obj: dict
    :param filename: filename to write
    :type filename: str
    :param mode: mode to write
    :type mode: str
    """
    with open(filename, mode) as filey:
        filey.writelines(print_json(json_obj))
    return filename


def print_json(json_obj: dict) -> str:
    """
    Pretty print json.

    :param json_obj: json object to print
    :type json_obj: dict
    """
    return json.dumps(json_obj, indent=4, separators=(",", ": "))


def read_file(filename: str, mode: str = "r") -> str:
    """
    Read a file.

    :param filename: filename to read
    :type filename: str
    :param mode: mode to read
    :type mode: str
    """
    with open(filename, mode) as filey:
        content = filey.read()
    return content


def read_json(filename: str, mode: str = "r") -> dict:
    """
    Read a json file to a dictionary.

    :param filename: filename to read
    :type filename: str
    :param mode: mode to read
    :type mode: str
    """
    return json.loads(read_file(filename))


def split_path_and_content(ref: str) -> PathAndOptionalContent:
    """
    Parse a string containing a path and an optional content

    Examples
    --------
    <path>:<content-type>
    path/to/config:application/vnd.oci.image.config.v1+json
    /dev/null:application/vnd.oci.image.config.v1+json
    C:\\myconfig:application/vnd.oci.image.config.v1+json

    Or,
    <path>
    /dev/null
    C:\\myconfig

    :param ref: the manifest reference to parse (examples above)
    :type ref: str
    : return: A Tuple of the path in the reference, and the content-type if one found,
              otherwise None.
    """
    if ":" not in ref:
        return PathAndOptionalContent(ref, None)

    if pathlib.Path(ref).drive:
        # Running on Windows and Path has Windows drive letter in it, it definitely has
        # one colon and could have two or feasibly more, e.g.
        # C:\test.tar
        # C:\test.tar:application/vnd.oci.image.layer.v1.tar
        # C:\test.tar:application/vnd.oci.image.layer.v1.tar:somethingelse
        #
        # This regex matches two colons in the string and returns everything before
        # the second colon as the "path" group and everything after the second colon
        # as the "context" group.
        # i.e.
        # (C:\test.tar):(application/vnd.oci.image.layer.v1.tar)
        # (C:\test.tar):(application/vnd.oci.image.layer.v1.tar:somethingelse)
        # But C:\test.tar along will not match and we just return it as is.
        path_and_content = re.search(r"(?P<path>.*?:.*?):(?P<content>.*)", ref)
        if path_and_content:
            return PathAndOptionalContent(
                path_and_content.group("path"), path_and_content.group("content")
            )
        return PathAndOptionalContent(ref, None)
    else:
        path_content_list = ref.split(":", 1)
        return PathAndOptionalContent(path_content_list[0], path_content_list[1])
