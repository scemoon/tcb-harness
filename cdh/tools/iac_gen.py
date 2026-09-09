#!/usr/bin/env python3
"""Generate Pulumi and Terraform resource declarations from provider YAML."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

PROVIDERS = {"tcb", "aliyun"}
ENVIRONMENTS = {"preview", "staging", "production"}
FORMATS = {"pulumi-py", "pulumi-ts", "terraform", "all"}


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    if yaml is None:
        raise RuntimeError("PyYAML is required; install the 'pyyaml' package")
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _project_components(project: dict[str, Any]) -> list[str]:
    stack = project.get("stack", {})
    components = stack.get("components", []) if isinstance(stack, dict) else []
    result: list[str] = []
    for component in components:
        if isinstance(component, str):
            result.append(component)
        elif isinstance(component, dict) and component.get("id"):
            result.append(str(component["id"]))
    return result


def _resource_map(provider: str, name: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    kind = str(config.get("type", name)).lower()
    if provider == "tcb":
        types = {
            "backend": "cloudbase_run.Service",
            "cloudbase_run": "cloudbase_run.Service",
            "web": "hosting.StaticSite",
            "cloudbase_hosting": "hosting.StaticSite",
            "database": "document_db.Database",
            "documentdb": "document_db.Database",
            "storage": "storage.Bucket",
        }
        return [{"name": name, "type": types.get(kind, kind), "config": config}]
    types = {
        "backend": "fc.Function",
        "function": "fc.Function",
        "web": "oss.Bucket",
        "oss": "oss.Bucket",
        "database": "rds.Instance",
        "rds": "rds.Instance",
        "storage": "oss.Bucket",
    }
    resources = [{"name": name, "type": types.get(kind, kind), "config": config}]
    if name == "web" and config.get("cdn_enabled"):
        resources.append({"name": "web_cdn", "type": "cdn.Distribution", "config": config})
    return resources


def _resources(provider: str, deployment: dict[str, Any], project: dict[str, Any]) -> list[dict[str, Any]]:
    declared = deployment.get("resources", {})
    if not isinstance(declared, dict):
        declared = {}
    names = list(declared)
    for name in _project_components(project):
        if name not in names and name in {"backend", "web", "database", "storage"}:
            names.append(name)
    result: list[dict[str, Any]] = []
    for name in names:
        config = declared.get(name, {})
        result.extend(_resource_map(provider, str(name), config if isinstance(config, dict) else {}))
    return result


def _identifier(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_]", "_", value)
    return value if value and not value[0].isdigit() else f"resource_{value}"


def _py_value(value: Any, indent: int = 0) -> str:
    return repr(value)


def render_pulumi_py(provider: str, environment: str, resources: list[dict[str, Any]]) -> str:
    module = "pulumi_tcb" if provider == "tcb" else "pulumi_alicloud"
    lines = [f"import {module} as cloud", "", f"environment = {_py_value(environment)}", ""]
    for resource in resources:
        config = resource["config"]
        args: list[str] = []
        for key, value in config.items():
            if key == "type":
                continue
            args.append(f"    {key}={_py_value(value)},")
        lines.append(f'{_identifier(resource["name"])} = cloud.{resource["type"]}({resource["name"]!r},')
        lines.extend(args)
        lines.append(")")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _hcl_key(key: str) -> str:
    return {"runtime": "runtime_environment", "memory_mb": "memory", "timeout_sec": "timeout"}.get(key, key)


def _hcl_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return json.dumps(value)
    if isinstance(value, dict):
        return json.dumps(value)
    return json.dumps(str(value))


def _terraform_type(provider: str, resource: dict[str, Any]) -> str:
    name = resource["name"]
    kind = resource["type"]
    if provider == "tcb":
        return {"cloudbase_run.Service": "tencentcloud_cloud_run_service", "hosting.StaticSite": "tencentcloud_cos_bucket", "document_db.Database": "tencentcloud_mongodb_instance", "storage.Bucket": "tencentcloud_cos_bucket"}.get(kind, "tencentcloud_resource")
    if name == "web_cdn":
        return "tencentcloud_cdn_domain"
    return {"fc.Function": "alicloud_fc_function", "oss.Bucket": "alicloud_oss_bucket", "rds.Instance": "alicloud_db_instance"}.get(kind, "alicloud_resource")


def render_terraform(provider: str, environment: str, resources: list[dict[str, Any]]) -> str:
    lines = [f'variable "environment" {{', f'  default = {environment!r}', "}", ""]
    for resource in resources:
        lines.append(f'resource "{_terraform_type(provider, resource)}" "{_identifier(resource["name"])}" {{')
        for key, value in resource["config"].items():
            if key != "type":
                lines.append(f"  {_hcl_key(key)} = {_hcl_value(value)}")
        lines.append("}")
        lines.append("")
    return "\n".join(lines)


def generate(project_root: Path, provider: str, environment: str, output_format: str, outdir: Path) -> list[Path]:
    provider_dir = project_root / "aidlc" / "providers" / provider
    deployment = _load_yaml(provider_dir / "deployment.yaml")
    preview = _load_yaml(provider_dir / "preview.yaml")
    project = _load_yaml(project_root / "aidlc" / "project.yaml")
    deployment = {**preview, **deployment}
    resources = _resources(provider, deployment, project)
    target = project_root / outdir
    target.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    if output_format in {"pulumi-py", "all"}:
        path = target / "pulumi" / f"{environment}.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_pulumi_py(provider, environment, resources), encoding="utf-8")
        written.append(path)
    if output_format in {"pulumi-ts", "all"}:
        path = target / "pulumi" / f"{environment}.ts"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_pulumi_ts(provider, environment, resources), encoding="utf-8")
        written.append(path)
    if output_format in {"terraform", "all"}:
        path = target / "terraform" / f"{environment}.tf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_terraform(provider, environment, resources), encoding="utf-8")
        written.append(path)
    return written


def _ts_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value)
    return json.dumps(value)


def render_pulumi_ts(provider: str, environment: str, resources: list[dict[str, Any]]) -> str:
    module = "@pulumi/tcb" if provider == "tcb" else "@pulumi/alicloud"
    lines = [f'import * as cloud from "{module}";', "", f"const environment = {_ts_value(environment)};", ""]
    for resource in resources:
        lines.append(f"const {_identifier(resource['name'])} = new cloud.{resource['type']}({_ts_value(resource['name'])}, {{")
        for key, value in resource["config"].items():
            if key != "type":
                lines.append(f"  {key}: {_ts_value(value)},")
        lines.extend(["});", ""])
    return "\n".join(lines).rstrip() + "\n"


def self_test() -> None:
    deployment = {"resources": {"backend": {"type": "cloudbase_run", "runtime": "python3.11", "memory_mb": 512, "timeout_sec": 30, "env_vars": ["DATABASE_URL"]}, "web": {"type": "cloudbase_hosting", "cdn_enabled": True}}}
    resources = _resources("tcb", deployment, {"stack": {"components": []}})
    assert "runtime_environment" in render_terraform("tcb", "preview", resources)
    assert "cloudbase_run.Service" in render_pulumi_py("tcb", "preview", resources)
    print("self-test passed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--provider", choices=sorted(PROVIDERS), required=False, default="tcb")
    parser.add_argument("--environment", choices=sorted(ENVIRONMENTS), default="preview")
    parser.add_argument("--format", dest="output_format", choices=sorted(FORMATS), default="all")
    parser.add_argument("--outdir", type=Path, default=Path("aidlc/iac"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    for path in generate(args.project_root, args.provider, args.environment, args.output_format, args.outdir):
        print(path)


if __name__ == "__main__":
    main()
