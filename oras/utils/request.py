__author__ = "Vanessa Sochat"
__copyright__ = "Copyright 2021-2022, Vanessa Sochat"
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
