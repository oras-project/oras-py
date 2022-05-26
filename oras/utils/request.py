__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import os


def iter_localhosts(name: str):
    """
    Given a url with localhost, always resolve to 127.0.0.1.

    :param name : the name of the original host string
    :type name: str
    """
    names = [name]
    if "localhost" in name:
        names.append(name.replace("localhost", "127.0.0.1"))
    elif "127.0.0.1" in name:
        names.append(name.replace("127.0.0.1", "localhost"))
    for name in names:
        yield name


def find_docker_config(exists: bool = True):
    """
    Return the docker default config path.
    """
    path = os.path.expanduser("~/.docker/config.json")

    # Allow the caller to request the path regardless of existing
    if os.path.exists(path) or not exists:
        return path


def get_docker_client(insecure: bool = False, **kwargs):
    """
    Get a docker client.

    :param tls : enable tls
    :type tls: bool
    """
    import docker

    return docker.DockerClient(tls=not insecure, **kwargs)
