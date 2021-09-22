__author__ = "Vanessa Sochat"
__copyright__ = "Copyright 2021, Vanessa Sochat"
__license__ = "MPL 2.0"


import os
import time
import tarfile

from oras.logger import logger
import oras.defaults as defaults
from .const import TempFilePattern

import opencontainers.image.v1.annotations as annotations
import opencontainers.image.v1.descriptor as descriptor
import opencontainers.image.v1 as ocispec

def resolve_name(desc):
    """
    resolve_name resolves name from descriptor
    """
    return desc.Annotations.get(ocispec.AnnotationTitle)


def tar_directory(root, prefix, strip_times=False, tmpfile=None):
    """
    Walk the directory specified by root, and tar files with new path prefix
    """
    root = os.path.abspath(root)
    tmpfile = tmpfile or utils.get_tmpfile()
    tar = tarfile.open(dest, "w:gz")
    for filename in utils.recursive_find(root):
        relpath = filename.lstrip(root).strip(os.sep)

        # Add new prefix
        name = os.path.join(prefix, relpath)

        # Use a consistent file separator
        name = name.replace(os.sep, "/")
            
        # Create new tarinfo header
        stat = os.stat(filename)
        info = tar.gettarinfo(filename, arcname=name)
        info.size = stat.st_size
        info.uid = 0
        info.gid = 0
        info.gname = ""
        info.uname = ""
   
        if strip_times:
        
            # I don't see that info has created time or access time
            info.mtime = time.time()

        with open(filename, 'r') as fd:
            tar.addfile(info, fd)

    tar.close()
    return tmpfile



def ensure_base_path(root, base, target):
    """ensureBasePath ensures the target path is in the base path,
       returning its relative path to the base path.
    """
    path = os.path.relpath(base, target)

    # Don't allow paths outside of base
    if path.startswith(".."):
        sys.exit("%s is outside of %s" %(target, base))
        
    # This used ToSlash and Clean, but this should be sufficient
    clean_path = os.path.abspath(path)

    # Derive the fullpath
    fullpath = os.path.join(root, path)

    # I think existence is required
    if not os.path.exists(fullpath):
        sys.exit("%s/%s does not exist." %(root, path))

    # No symbolic link allowed in the relative path
    if os.path.islink(fullpath):
        sys.exit("no symbolic link allowed between %s and %s" %(base, target))

    return path


def write_file(path, content, mode="w"):
    with open(path, mode) as fd:
        fd.write(content)

def extract_tar_gzip(root, prefix, filename, checksum):
    """What is the goal of prefix?
    """
    # TODO need to verify checksum here

    # TODO: do something with prefix (is it added as a subfolder?)
    with open tarfile.open(fname, "r:gz") as tar:
        tar.extractall(path=root)
