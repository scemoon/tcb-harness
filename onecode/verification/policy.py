from __future__ import annotations

from enum import Enum


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

    def should_verify(self, tool_name: str) -> bool:
        if self == VerificationPolicy.EVERY_STEP:
            return True
        if self == VerificationPolicy.FINAL_ONLY:
            return False
        if self == VerificationPolicy.CONDITIONAL:
            write_tools = {"WriteTool", "EditTool", "InsertTool", "ApplyPatchTool", "BashTool"}
            return tool_name in write_tools
        return False

    def should_final_verify(self) -> bool:
        return self in (VerificationPolicy.FINAL_ONLY, VerificationPolicy.CONDITIONAL)