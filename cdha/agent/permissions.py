from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class PermissionResult(Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


@dataclass
class PathRule:
    pattern: str
    permission: PermissionResult = PermissionResult.ALLOW

    def matches(self, path: str) -> bool:
        return fnmatch.fnmatch(path, self.pattern) or fnmatch.fnmatch(Path(path).name, self.pattern)


@dataclass
class CommandRule:
    pattern: str
    permission: PermissionResult = PermissionResult.ALLOW

    def matches(self, cmd: str) -> bool:
        return fnmatch.fnmatch(cmd, self.pattern)


@dataclass
class PermissionSet:
    path_rules: list[PathRule] = field(default_factory=list)
    command_rules: list[CommandRule] = field(default_factory=list)
    default_path_permission: PermissionResult = PermissionResult.ALLOW
    default_command_permission: PermissionResult = PermissionResult.ALLOW

    def check_path(self, path: str) -> PermissionResult:
        for rule in self.path_rules:
            if rule.matches(path):
                return rule.permission
        return self.default_path_permission

    def check_command(self, cmd: str) -> PermissionResult:
        for rule in self.command_rules:
            if rule.matches(cmd):
                return rule.permission
        return self.default_command_permission

    def allow_path(self, pattern: str) -> None:
        self.path_rules.append(PathRule(pattern, PermissionResult.ALLOW))

    def deny_path(self, pattern: str) -> None:
        self.path_rules.append(PathRule(pattern, PermissionResult.DENY))

    def ask_path(self, pattern: str) -> None:
        self.path_rules.append(PathRule(pattern, PermissionResult.ASK))

    def allow_command(self, pattern: str) -> None:
        self.command_rules.append(CommandRule(pattern, PermissionResult.ALLOW))

    def deny_command(self, pattern: str) -> None:
        self.command_rules.append(CommandRule(pattern, PermissionResult.DENY))

    def ask_command(self, pattern: str) -> None:
        self.command_rules.append(CommandRule(pattern, PermissionResult.ASK))


class PermissionChecker:
    def __init__(self, permission_set: Optional[PermissionSet] = None):
        self.permission_set = permission_set or PermissionSet()

    def check_file_read(self, path: str) -> PermissionResult:
        return self.permission_set.check_path(path)

    def check_file_write(self, path: str) -> PermissionResult:
        return self.permission_set.check_path(path)

    def check_command(self, cmd: str) -> PermissionResult:
        return self.permission_set.check_command(cmd)

    def is_allowed(self, permission: PermissionResult) -> bool:
        return permission == PermissionResult.ALLOW

    def is_denied(self, permission: PermissionResult) -> bool:
        return permission == PermissionResult.DENY

    def requires_approval(self, permission: PermissionResult) -> bool:
        return permission == PermissionResult.ASK


def create_safe_permission_set() -> PermissionSet:
    ps = PermissionSet()
    ps.deny_path("**/.env")
    ps.deny_path("**/secrets/**")
    ps.deny_path("**/credentials/**")
    ps.deny_command("rm -rf /")
    ps.deny_command("rm -rf /*")
    ps.deny_command("dd if=*")
    ps.deny_command("mkfs.*")
    ps.deny_command(":(){:|:&};:")
    ps.ask_command("sudo *")
    ps.ask_command("chmod 777 *")
    ps.ask_command("curl *")
    ps.ask_command("wget *")
    return ps