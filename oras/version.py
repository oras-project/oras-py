__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

__version__ = "0.0.1"
AUTHOR = "Vanessa Sochat"
EMAIL = "vsoch@users.noreply.github.com"
NAME = "oras"
PACKAGE_URL = "https://github.com/oras-project/oras-python"
KEYWORDS = "oci, registry, storage"
DESCRIPTION = "OCI Registry as Storage Python client"
LICENSE = "LICENSE"

################################################################################
# Global requirements

INSTALL_REQUIRES = (
    ("jsonschema", {"min_version": None}),
    ("requests", {"min_version": None}),
    ("docker", {"exact_version": "5.0.1"}),
)

TESTS_REQUIRES = (
    ("pytest", {"min_version": "4.6.2"}),
    ("mypy", {"min_version": None}),
    ("pyflakes", {"min_version": None}),
    ("black", {"min_version": None}),
    ("types-requests", {"min_version": None}),
    ("isort", {"min_version": None}),
)
INSTALL_REQUIRES_ALL = INSTALL_REQUIRES + TESTS_REQUIRES
