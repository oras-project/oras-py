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
import tarfile
import tempfile
from typing import Generator, Optional, TextIO, Union

from oras.logger import logger


def make_targz(source_dir: str, dest_name: Optional[str] = None) -> str:
    """
    Make a targz (compressed) archive from a source directory.
    """
    dest_name = dest_name or get_tmpfile(suffix=".tar.gz")
    with tarfile.open(dest_name, "w:gz") as tar:
        tar.add(source_dir, arcname=os.path.basename(source_dir))
    return dest_name


def extract_targz(targz: str, outdir: str) -> str:
    """
    Extract a .tar.gz to an output directory.
    """
    with tarfile.open(targz, "r:gz") as fd:
        fd.extractall(outdir)
    return outdir


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

    :param path: the path to get the size for
    :type path: str
    :param algorithm: the algorithm to use
    :type algorithm: str
    """
    try:
        hasher = getattr(hashlib, algorithm)()
    except AttributeError:
        logger.error("%s is an invalid algorithm.")
        logger.exit(" ".join(hashlib.algorithms_guaranteed))

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
            logger.exit("Error creating path %s, exiting." % path)


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
    :type image; TextIO or io.BufferedReader
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
