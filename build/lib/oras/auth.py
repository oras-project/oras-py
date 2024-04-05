__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import base64
import os
import re
from typing import List, Optional

import oras.utils
from oras.logger import logger


def load_configs(configs: Optional[List[str]] = None):
    """
    Load one or more configs with credentials from the filesystem.

    :param configs: list of configuration paths to load, defaults to None
    :type configs: optional list
    """
    configs = configs or []
    default_config = oras.utils.find_docker_config()

    # Add the default docker config
    if default_config:
        configs.append(default_config)
    configs = set(configs)  # type: ignore

    # Load configs until we find our registry hostname
    auths = {}
    for config in configs:
        if not os.path.exists(config):
            logger.warning(f"{config} does not exist.")
            continue
        cfg = oras.utils.read_json(config)
        auths.update(cfg.get("auths", {}))
    return auths


def get_basic_auth(username: str, password: str):
    """
    Prepare basic auth from a username and password.

    :param username: the user account name
    :type username: str
    :param password: the user account password
    :type password: str
    """
    auth_str = "%s:%s" % (username, password)
    return base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")


class authHeader:
    def __init__(self, lookup: dict):
        """
        Given a dictionary of values, match them to class attributes

        :param lookup : dictionary of key,value pairs to parse into auth header
        :type lookup: dict
        """
        self.service: Optional[str] = None
        self.realm: Optional[str] = None
        self.scope: Optional[str] = None
        for key in lookup:
            if key in ["realm", "service", "scope"]:
                setattr(self, key, lookup[key])


def parse_auth_header(authHeaderRaw: str) -> authHeader:
    """
    Parse authentication header into pieces

    :param username: the user account name
    :type username: str
    :param password: the user account password
    :type password: str
    """
    regex = re.compile('([a-zA-z]+)="(.+?)"')
    matches = regex.findall(authHeaderRaw)
    lookup = dict()
    for match in matches:
        lookup[match[0]] = match[1]
    return authHeader(lookup)
