__author__ = "Vanessa Sochat"
__copyright__ = "Copyright 2021-2022, Vanessa Sochat"
__license__ = "MIT"

import re
import base64


def get_basic_auth(username, password):
    """
    Prepare basic auth from a username and password.
    """
    auth_str = "%s:%s" % (username, password)
    return base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")


def parse_auth_header(authHeaderRaw):
    """
    Parse authentication header into pieces
    """
    regex = re.compile('([a-zA-z]+)="(.+?)"')
    matches = regex.findall(authHeaderRaw)
    lookup = dict()
    for match in matches:
        lookup[match[0]] = match[1]
    return authHeader(lookup)


class authHeader:
    def __init__(self, lookup):
        """
        Given a dictionary of values, match them to class attributes
        """
        for key in lookup:
            if key in ["realm", "service", "scope"]:
                setattr(self, key.capitalize(), lookup[key])
