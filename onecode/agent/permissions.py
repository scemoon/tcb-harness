from __future__ import annotations

import fnmatch
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
        return (
            fnmatch.fnmatch(path, self.pattern) or
            fnmatch.fnmatch(Path(path).name, self.pattern) or
            fnmatch.fnmatch(Path(path).stem, self.pattern)
        )


@dataclass
class CommandRule:
    pattern: str
    permission: PermissionResult = PermissionResult.ALLOW

    def matches(self, cmd: str) -> bool:
        normalized = cmd.strip()
        if fnmatch.fnmatch(normalized, self.pattern):
            return True
        parts = normalized.split()
        if parts:
            cmd_base = parts[0]
            args = " ".join(parts[1:]) if len(parts) > 1 else ""
            if args and fnmatch.fnmatch(f"{cmd_base} {args}", self.pattern):
                return True
            if fnmatch.fnmatch(cmd_base, self.pattern):
                return True
        return False


@dataclass
class PermissionSet:
    path_rules: list[PathRule] = field(default_factory=list)
    command_rules: list[CommandRule] = field(default_factory=list)
    default_path_permission: PermissionResult = PermissionResult.ALLOW
    default_command_permission: PermissionResult = PermissionResult.ALLOW

    def check_path(self, path: str) -> PermissionResult:
        matched = self.default_path_permission
        for rule in self.path_rules:
            if rule.matches(path):
                matched = rule.permission
        return matched

    def check_command(self, cmd: str) -> PermissionResult:
        matched = self.default_command_permission
        for rule in self.command_rules:
            if rule.matches(cmd):
                matched = rule.permission
        return matched

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

    @classmethod
    def from_config(cls, config: dict) -> "PermissionSet":
        ps = cls()
        perm_map = {"allow": PermissionResult.ALLOW, "ask": PermissionResult.ASK, "deny": PermissionResult.DENY}

        if "path" in config:
            for pattern, action in config["path"].items():
                if action in perm_map:
                    getattr(ps, f"{action}_path")(pattern)

        if "command" in config:
            for pattern, action in config["command"].items():
                if action in perm_map:
                    getattr(ps, f"{action}_command")(pattern)

        if "default" in config:
            default = config["default"]
            if "path" in default and default["path"] in perm_map:
                ps.default_path_permission = perm_map[default["path"]]
            if "command" in default and default["command"] in perm_map:
                ps.default_command_permission = perm_map[default["command"]]

        return ps


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
