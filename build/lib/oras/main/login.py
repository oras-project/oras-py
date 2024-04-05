__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import os
from typing import Optional

import oras.auth
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
        if not dockercfg_path:
            dockercfg_path = oras.utils.find_docker_config(exists=False)
        if os.path.exists(dockercfg_path):  # type: ignore
            cfg = oras.utils.read_json(dockercfg_path)  # type: ignore
        else:
            oras.utils.mkdir_p(os.path.dirname(dockercfg_path))  # type: ignore
            cfg = {"auths": {}}
        if registry in cfg["auths"]:
            cfg["auths"][registry]["auth"] = oras.auth.get_basic_auth(
                username, password
            )
        else:
            cfg["auths"][registry] = {
                "auth": oras.auth.get_basic_auth(username, password)
            }
        oras.utils.write_json(cfg, dockercfg_path)  # type: ignore
        return {"Status": "Login Succeeded"}
