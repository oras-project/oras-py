__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"


def iter_localhosts(name: str):
    """
    Given a url with localhost, always resolve to 127.0.0.1.

    Arguments
    ---------
    name : the name of the original host string
    """
    names = [name]
    if "localhost" in name:
        names.append(name.replace("localhost", "127.0.0.1"))
    elif "127.0.0.1" in name:
        names.append(name.replace("127.0.0.1", "localhost"))
    for name in names:
        yield name


def get_docker_client(insecure: bool = False, **kwargs):
    """
    Get a docker client.

    Arguments
    ---------
    tls : enable tls
    """
    import docker

    return docker.DockerClient(tls=not insecure, **kwargs)
