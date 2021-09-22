__author__ = "Vanessa Sochat"
__copyright__ = "Copyright 2021, Vanessa Sochat"
__license__ = "MPL 2.0"

import opencontainers.digest as digest
from dataclasses import dataclass
from datetime import datetime

@dataclass
class Status:
    """
    Status of a content operation
    """
    ref: str
    offset: int
    total: int
    digest: digest.Digest    
    started_at: datetime
    updated_at: datetime
