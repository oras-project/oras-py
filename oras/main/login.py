__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import os
from typing import Optional

import oras.auth.utils as auth_utils
import oras.utils


class DockerClient:
    """
    If running inside a container (or similar without docker) do a manual login
    """

    def login(
        self,
        username: str,
        password: str,
        registry: str,
        dockercfg_path: Optional[str] = None,
    ) -> dict:
        """
        Manual login means loading and checking the config file

        :param registry: if provided, use this custom provider instead of default
        :type registry: oras.provider.Registry or None
        :param username: the user account name
        :type username: str
        :param password: the user account password
        :type password: str
        :param dockercfg_str: docker config path
        :type dockercfg_str: list
        """
        _dockercfg_path = dockercfg_path or "~/.docker/config.json"
        if os.path.exists(_dockercfg_path):
            cfg = oras.utils.read_json(_dockercfg_path)
        else:
            oras.utils.mkdir_p(os.path.dirname(_dockercfg_path))
            cfg = {"auths": {}}
        if registry in cfg["auths"]:
            cfg["auths"][registry]["auth"] = auth_utils.get_basic_auth(
                username, password
            )
        else:
            cfg["auths"][registry] = {
                "auth": auth_utils.get_basic_auth(username, password)
            }
        oras.utils.write_json(cfg, _dockercfg_path)
        return {"Status": "Login Succeeded"}
