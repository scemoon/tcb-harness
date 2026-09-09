from __future__ import annotations

from enum import Enum
from pathlib import Path


class VerificationPolicy(Enum):
    EVERY_STEP = "every_step"
    FINAL_ONLY = "final_only"
    CONDITIONAL = "conditional"

    @classmethod
    def from_str(cls, value: str) -> VerificationPolicy:
        for member in cls:
            if member.value == value:
                return member
        return cls.CONDITIONAL


PLATFORM_SOURCE_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs"}


def is_source_file(path: str) -> bool:
    return Path(path).suffix in PLATFORM_SOURCE_EXTENSIONS