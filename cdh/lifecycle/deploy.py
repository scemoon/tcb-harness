from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Deployment:
    cloud: str = "tcb"
    version: Optional[str] = None
    status: str = "pending"
    url: Optional[str] = None
