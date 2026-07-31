"""AIDLC dashboard TUI.

Renders an at-a-glance dashboard of AIDLC project health using a 2x3
grid of rich widgets:

  * ProgressWidget       - current phase + progress bar
  * GateWidget           - quality gate pass/fail/warn status
  * SpecQualityWidget    - EARS / FR / BDD / DAG counts and pass rates
  * ToolsStatusWidget    - installed vs stub tools
  * FRCoverageWidget     - FR -> BDD coverage percentage
  * DeploymentStatusWidget - preview / staging / production env status

Supports:
  - Auto-detect .cdh/ directory (walks up from cwd).
  - Plain-text console rendering (the default).
  - --watch / --interval N to refresh every N seconds (Ctrl-C to stop).
  - --export PATH to save a single-shot snapshot as Markdown (or HTML if
    the suffix is .html) without entering watch mode.

If the `rich` library is unavailable, falls back to plain ANSI escape
codes so the dashboard still renders in a colour-capable terminal.

The dashboard never raises on missing data: every widget gracefully
handles a project that has not been initialised, or a partial project
mid-iteration.  Missing widgets render as a grey "no data" panel.
"""

from __future__ import annotations

import io
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.progress import (
        BarColumn,
        Progress,
        TextColumn,
        SpinnerColumn,
        TimeElapsedColumn,
    )

    _HAVE_RICH = True
except Exception:  # pragma: no cover - rich is optional
    Console = None  # type: ignore[assignment]
    Panel = None  # type: ignore[assignment]
    Table = None  # type: ignore[assignment]
    Text = None  # type: ignore[assignment]
    Progress = None  # type: ignore[assignment]
    BarColumn = None  # type: ignore[assignment]
    TextColumn = None  # type: ignore[assignment]
    SpinnerColumn = None  # type: ignore[assignment]
    TimeElapsedColumn = None  # type: ignore[assignment]
    _HAVE_RICH = False


_PHASE_SEQUENCE = ["init", "understand", "plan", "verify", "deliver"]


# ---------------------------------------------------------------------------
# ANSI fallback helpers
# ---------------------------------------------------------------------------

_ANSI_RESET = "\x1b[0m"
_ANSI_COLORS = {
    "red": "\x1b[31m",
    "green": "\x1b[32m",
    "yellow": "\x1b[33m",
    "blue": "\x1b[34m",
    "magenta": "\x1b[35m",
    "cyan": "\x1b[36m",
    "white": "\x1b[37m",
    "grey": "\x1b[90m",
    "bold": "\x1b[1m",
    "dim": "\x1b[2m",
}


def _ansi(text: str, *styles: str) -> str:
    if not sys.stdout.isatty():
        return text
    prefix = "".join(_ANSI_COLORS.get(s, "") for s in styles)
    if not prefix:
        return text
    return f"{prefix}{text}{_ANSI_RESET}"


def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return bool(sys.stdout.isatty())


# ---------------------------------------------------------------------------
# Data sources
# ---------------------------------------------------------------------------


def _walk_up_parents(workspace_root: Path) -> Iterable[Path]:
    current = workspace_root.resolve()
    yield current
    try:
        git_root = next(
            (
                p
                for p in current.parents
                if (p / ".git").exists() or (p / ".hg").exists()
            ),
            None,
        )
        if git_root:
            yield git_root
    except StopIteration:
        pass


def find_cdh_dir(workspace_root: Path) -> Optional[Path]:
    """Walk up from workspace_root looking for a .cdh/ directory."""
    for parent in _walk_up_parents(workspace_root):
        candidate = parent / ".cdh"
        if candidate.is_dir():
            return candidate
    return None


def _read_state(cdh_dir: Optional[Path]) -> dict:
    if cdh_dir is None:
        return {}
    state_path = cdh_dir / "state.json"
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_config(cdh_dir: Optional[Path]) -> dict:
    if cdh_dir is None:
        return {}
    yaml_path = cdh_dir / "config.yaml"
    if yaml_path.exists():
        try:
            import yaml  # type: ignore

            return yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        except Exception:
            pass
    json_path = cdh_dir / "config.json"
    if json_path.exists():
        try:
            return json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _read_project_yaml(project_root: Optional[Path]) -> dict:
    if project_root is None:
        return {}
    p = project_root / "aidlc" / "project.yaml"
    if not p.exists():
        return {}
    try:
        import yaml  # type: ignore

        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Widget result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class WidgetResult:
    """Lightweight value object returned by each widget's collect().

    Attributes:
        title:    widget heading shown in the panel border.
        summary:  short single-line headline (e.g. "3 / 5 passed").
        rows:     list of (label, value, status) tuples; status is one of
                  ``"pass"``, ``"warn"``, ``"fail"``, or ``"info"``.
        progress: optional 0.0..1.0 for widgets that have a progress bar.
        message:  optional free-form note (shown as a footer line).
    """

    title: str
    summary: str = ""
    rows: list[tuple[str, str, str]] = field(default_factory=list)
    progress: Optional[float] = None
    message: Optional[str] = None

    def is_empty(self) -> bool:
        return not self.summary and not self.rows and self.progress is None


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------


class ProgressWidget:
    """Current AI-DLC phase with progress bar."""

    title = "Phase Progress"

    def collect(self, project_root: Optional[Path], cdh_dir: Optional[Path]) -> WidgetResult:
        state = _read_state(cdh_dir)
        current = state.get("current_phase", "")
        completed = state.get("completed_phases", []) or []

        if not current:
            return WidgetResult(
                title=self.title,
                summary="No phase recorded",
                message="Run `cdh aidlc phase <init|understand|plan|verify|deliver>`.",
            )

        try:
            idx = _PHASE_SEQUENCE.index(current)
        except ValueError:
            idx = -1

        total = len(_PHASE_SEQUENCE)
        progress = (idx + 1) / total if idx >= 0 else 0.0

        rows: list[tuple[str, str, str]] = []
        for i, phase in enumerate(_PHASE_SEQUENCE):
            if phase in completed:
                status = "pass"
                marker = "done"
            elif i == idx:
                status = "info"
                marker = "current"
            elif i < idx:
                status = "pass"
                marker = "skipped"
            else:
                status = "info"
                marker = "pending"
            rows.append((phase, marker, status))

        return WidgetResult(
            title=self.title,
            summary=f"{current} ({idx + 1}/{total})",
            rows=rows,
            progress=progress,
        )


class GateWidget:
    """Quality gate status (pass / fail / warn) with icons."""

    title = "Quality Gates"

    _ICONS = {"pass": "[OK]", "fail": "[X]", "warn": "[!]", "info": "[ ]"}

    def collect(self, project_root: Optional[Path], cdh_dir: Optional[Path]) -> WidgetResult:
        state = _read_state(cdh_dir)
        gates: dict[str, dict] = state.get("gate_results", {}) or {}

        if not gates:
            return WidgetResult(
                title=self.title,
                summary="No gates recorded yet",
                message="Use `cdh aidlc gate <name> --status passed|failed`.",
            )

        passed = sum(1 for g in gates.values() if g.get("status") == "passed")
        failed = sum(1 for g in gates.values() if g.get("status") == "failed")
        warned = sum(1 for g in gates.values() if g.get("status") not in ("passed", "failed"))

        rows: list[tuple[str, str, str]] = []
        for name, g in sorted(gates.items()):
            status = g.get("status", "warn")
            s = status if status in ("pass", "fail", "warn") else "warn"
            rows.append((name, status, s))

        summary = f"{passed} passed, {failed} failed, {warned} warn"

        if failed:
            msg = "Some gates failed - review before advancing."
        elif warned:
            msg = "All gates passed but some have warnings."
        else:
            msg = "All gates passed."

        return WidgetResult(
            title=self.title,
            summary=summary,
            rows=rows,
            message=msg,
        )


class SpecQualityWidget:
    """EARS / FR / BDD / DAG counts and pass rates."""

    title = "Spec Quality"

    def collect(self, project_root: Optional[Path], cdh_dir: Optional[Path]) -> WidgetResult:
        from cdh.validators import (
            run_bdd_check,
            run_dag_check,
            run_ears_check,
            run_fr_check,
        )

        if project_root is None:
            return WidgetResult(
                title=self.title,
                summary="No project root",
                message="Run from inside an AIDLC project.",
            )

        runners: list[tuple[str, str, Callable[[Path], dict]]] = [
            ("EARS", "ears", run_ears_check),
            ("FR", "fr", run_fr_check),
            ("BDD", "bdd", run_bdd_check),
            ("DAG", "dag", run_dag_check),
        ]

        rows: list[tuple[str, str, str]] = []
        total_pass = 0
        total_checks = 0

        for label, key, runner in runners:
            try:
                result = runner(project_root)
            except Exception as e:
                rows.append((label, f"error: {e}", "warn"))
                continue

            checks = result.get("checks", []) or []
            passed = sum(1 for c in checks if c.get("status") == "pass")
            failed = sum(1 for c in checks if c.get("status") == "fail")
            warned = sum(1 for c in checks if c.get("status") == "warn")

            overall = "pass" if result.get("passed") else "fail"
            value = f"{passed}P / {warned}W / {failed}F"
            rows.append((label, value, overall))

            total_pass += passed
            total_checks += len(checks)

        pass_rate = (total_pass / total_checks * 100.0) if total_checks else 0.0
        summary = f"{total_pass}/{total_checks} checks pass ({pass_rate:.0f}%)"

        return WidgetResult(
            title=self.title,
            summary=summary,
            rows=rows,
            progress=(pass_rate / 100.0) if total_checks else None,
        )


class ToolsStatusWidget:
    """Installed vs stub AIDLC tools."""

    title = "AIDLC Tools"

    def collect(self, project_root: Optional[Path], cdh_dir: Optional[Path]) -> WidgetResult:
        from cdh.tools import tools_status as _tools_status

        if project_root is None:
            return WidgetResult(
                title=self.title,
                summary="No project root",
            )

        try:
            result = _tools_status(project_root)
        except Exception as e:
            return WidgetResult(
                title=self.title,
                summary="error",
                message=str(e),
            )

        if not result:
            return WidgetResult(
                title=self.title,
                summary="No tools defined",
            )

        rows: list[tuple[str, str, str]] = []
        installed = stub = missing = 0
        for name, status in sorted(result.items()):
            short = name.replace(".py", "")
            if status == "installed":
                installed += 1
                rows.append((short, "installed", "pass"))
            elif status == "stub":
                stub += 1
                rows.append((short, "stub", "warn"))
            else:
                missing += 1
                rows.append((short, status, "fail"))

        total = installed + stub + missing
        progress = installed / total if total else 0.0
        summary = f"{installed} installed, {stub} stub, {missing} missing"

        msg = None
        if stub or missing:
            msg = "Run `cdh aidlc tools install` to replace stubs."

        return WidgetResult(
            title=self.title,
            summary=summary,
            rows=rows,
            progress=progress,
            message=msg,
        )


class FRCoverageWidget:
    """FR -> BDD coverage percentage."""

    title = "FR Coverage"

    _FR_RE = re.compile(r"\b([A-Z]{2,8})-FR-(\d{3})\b")

    def collect(self, project_root: Optional[Path], cdh_dir: Optional[Path]) -> WidgetResult:
        if project_root is None:
            return WidgetResult(
                title=self.title,
                summary="No project root",
            )

        spec_frs: set[str] = set()
        spec_dir = project_root / "aidlc" / "openspec" / "changes"
        if spec_dir.exists():
            for f in spec_dir.rglob("spec-delta.md"):
                try:
                    text = f.read_text(encoding="utf-8")
                except Exception:
                    continue
                for m in self._FR_RE.finditer(text):
                    spec_frs.add(f"{m.group(1)}-FR-{m.group(2)}")

        feature_frs: set[str] = set()
        for f in project_root.rglob("*.feature"):
            try:
                text = f.read_text(encoding="utf-8")
            except Exception:
                continue
            for m in self._FR_RE.finditer(text):
                feature_frs.add(f"{m.group(1)}-FR-{m.group(2)}")

        if not spec_frs and not feature_frs:
            return WidgetResult(
                title=self.title,
                summary="No FR references found",
                message="Add FR ids to spec-delta.md and feature files.",
            )

        if not spec_frs:
            covered = 0
            total = len(feature_frs)
            progress = 0.0
        else:
            covered = len(spec_frs & feature_frs)
            total = len(spec_frs)
            progress = covered / total if total else 0.0

        uncovered = sorted(spec_frs - feature_frs)
        rows: list[tuple[str, str, str]] = []
        rows.append(("spec FRs", str(len(spec_frs)), "info"))
        rows.append(("feature FRs", str(len(feature_frs)), "info"))
        rows.append(("covered", str(covered), "pass"))

        if uncovered:
            rows.append(("uncovered", ", ".join(uncovered[:5]) + (
                f" (+{len(uncovered) - 5})" if len(uncovered) > 5 else ""
            ), "warn"))

        summary = f"{covered}/{total} FRs covered ({progress * 100:.0f}%)"

        return WidgetResult(
            title=self.title,
            summary=summary,
            rows=rows,
            progress=progress,
        )


class DeploymentStatusWidget:
    """Preview / staging / production environment status."""

    title = "Deployment"

    _ENVS = ("preview", "staging", "production")

    def collect(self, project_root: Optional[Path], cdh_dir: Optional[Path]) -> WidgetResult:
        if project_root is None:
            return WidgetResult(
                title=self.title,
                summary="No project root",
            )

        project_yaml = _read_project_yaml(project_root)
        provider = (
            project_yaml.get("stack", {}).get("cross_cutting", {}).get("provider")
            or project_yaml.get("provider")
            or "tcb"
        )

        rows: list[tuple[str, str, str]] = []
        any_defined = False

        for env in self._ENVS:
            file1 = project_root / "aidlc" / "providers" / provider / f"{env}.yaml"
            file2 = project_root / "aidlc" / "providers" / provider / "deployment.yaml"

            defined = False
            config_summary = "not configured"
            status = "warn"
            for f in (file1, file2):
                if not f.exists():
                    continue
                defined = True
                try:
                    import yaml  # type: ignore

                    data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
                except Exception:
                    data = {}

                envs_block = data.get("environments", {}) if isinstance(data, dict) else {}
                env_cfg = envs_block.get(env) if isinstance(envs_block, dict) else None

                if env == "preview" and isinstance(data, dict) and "preview" in data:
                    env_cfg = data.get("preview")
                if env_cfg is None and isinstance(data, dict) and env in data:
                    env_cfg = data.get(env)

                if env_cfg is not None:
                    orch = (
                        env_cfg.get("orchestrator")
                        if isinstance(env_cfg, dict)
                        else None
                    ) or "deploy_stack"
                    ttl = env_cfg.get("ttl") if isinstance(env_cfg, dict) else None
                    pre = env_cfg.get("pre_conditions") if isinstance(env_cfg, dict) else None
                    bits = [f"orch={orch}"]
                    if ttl:
                        bits.append(f"ttl={ttl}")
                    if pre:
                        bits.append(f"pre={','.join(pre)}")
                    config_summary = " ".join(bits)
                    status = "pass"
                else:
                    config_summary = "no env entry"
                    status = "warn"

            if not defined:
                rows.append((env, "no config", "warn"))
            else:
                rows.append((env, config_summary, status))
                any_defined = True

        summary = (
            f"{provider}: {sum(1 for _, _, s in rows if s == 'pass')}/{len(rows)} envs configured"
        )

        msg = None
        if not any_defined:
            msg = (
                "Run `cdh aidlc project init --with-ci` to scaffold provider "
                "configs, or `cdh aidlc config provider <name>` to generate them."
            )

        return WidgetResult(
            title=self.title,
            summary=summary,
            rows=rows,
            message=msg,
        )


# ---------------------------------------------------------------------------
# Dashboard renderer
# ---------------------------------------------------------------------------


_ALL_WIDGETS: list[type] = [
    ProgressWidget,
    GateWidget,
    SpecQualityWidget,
    ToolsStatusWidget,
    FRCoverageWidget,
    DeploymentStatusWidget,
]


@dataclass
class DashboardSnapshot:
    project_root: Optional[Path]
    cdh_dir: Optional[Path]
    project_name: str
    widgets: list[tuple[str, WidgetResult]]


def collect_snapshot(
    workspace_root: Path,
    widgets: Optional[list[type]] = None,
) -> DashboardSnapshot:
    """Run every widget's collect() and return a DashboardSnapshot."""
    cdh_dir = find_cdh_dir(workspace_root)
    project_root = cdh_dir.parent if cdh_dir else workspace_root

    cfg = _read_config(cdh_dir)
    name = cfg.get("name") or (project_root.name if project_root else workspace_root.name)

    chosen = widgets or _ALL_WIDGETS
    out: list[tuple[str, WidgetResult]] = []
    for wcls in chosen:
        try:
            w = wcls()
            res = w.collect(project_root, cdh_dir)
        except Exception as e:  # pragma: no cover - safety net
            res = WidgetResult(
                title=wcls.title,
                summary="error",
                message=str(e),
            )
        out.append((wcls.title, res))

    return DashboardSnapshot(
        project_root=project_root,
        cdh_dir=cdh_dir,
        project_name=name,
        widgets=out,
    )


# ---------------------------------------------------------------------------
# Rich rendering
# ---------------------------------------------------------------------------


_STATUS_STYLES = {
    "pass": ("green", "OK"),
    "fail": ("red", "X"),
    "warn": ("yellow", "!"),
    "info": ("blue", "-"),
}


def _render_widget_rich(console: Console, result: WidgetResult) -> Panel:
    if result.is_empty():
        body = Text("no data", style="dim")
    else:
        lines: list[Any] = []
        if result.summary:
            lines.append(Text(result.summary, style="bold"))

        if result.progress is not None:
            pct = max(0.0, min(1.0, result.progress))
            bar_width = 24
            filled = int(round(bar_width * pct))
            bar = "█" * filled + "░" * (bar_width - filled)
            pct_text = f"{pct * 100:5.1f}%"
            lines.append(Text(f"  [{bar}] {pct_text}", style="cyan"))

        if result.rows:
            table = Table(
                show_header=False,
                show_edge=False,
                box=None,
                padding=(0, 1),
            )
            table.add_column(justify="left", style="bold", no_wrap=True)
            table.add_column(justify="left")
            table.add_column(justify="left", width=4)
            for label, value, status in result.rows:
                colour, icon = _STATUS_STYLES.get(status, ("white", "?"))
                table.add_row(
                    Text(label, style="white"),
                    Text(str(value), style="white"),
                    Text(icon, style=colour),
                )
            lines.append(table)

        if result.message:
            lines.append(Text(result.message, style="dim italic"))

        if len(lines) == 1:
            body = lines[0]
        else:
            from rich.console import Group

            body = Group(*lines)

    border_style = "cyan"
    if any(s == "fail" for _, _, s in result.rows):
        border_style = "red"
    elif any(s == "warn" for _, _, s in result.rows):
        border_style = "yellow"

    return Panel(
        body,
        title=f"[bold]{result.title}[/bold]",
        border_style=border_style,
        padding=(0, 1),
        expand=True,
    )


def _render_widget_plain(result: WidgetResult, width: int = 36) -> str:
    color = _supports_color()
    inner_w = max(10, width - 4)

    title = result.title
    header = f"┤ {title} ├"
    bar = "─" * max(1, width - len(header) - 1)
    top = f"┌─{header}{bar}┐"

    lines: list[str] = []
    if result.summary:
        lines.append(_fit(result.summary, inner_w, color, "bold"))
    if result.progress is not None:
        pct = max(0.0, min(1.0, result.progress))
        bar_w = max(8, inner_w - 10)
        filled = int(round(bar_w * pct))
        bar_str = "█" * filled + "░" * (bar_w - filled)
        line = f"[{bar_str}] {pct * 100:5.1f}%"
        lines.append(_fit(line, inner_w, color, "cyan"))

    for label, value, status in result.rows:
        _, icon = _STATUS_STYLES.get(status, ("white", "?"))
        icon_styled = _ansi(icon, {"pass": "green", "fail": "red", "warn": "yellow"}.get(status, "white")) if color else icon
        text = f"{icon_styled} {label}: {value}"
        # Truncate cleanly to inner_w
        text = _truncate(text, inner_w)
        lines.append(text)

    if result.message:
        lines.append(_fit(result.message, inner_w, color, dim_style="dim"))

    if not lines:
        lines.append(_fit("no data", inner_w, color, "dim"))

    body_lines = [f"│ {ln.ljust(inner_w)} │" for ln in lines]
    bottom = f"└{'─' * (width - 2)}┘"
    return "\n".join([top, *body_lines, bottom])


def _fit(text: str, width: int, color: bool, style: str = "") -> str:
    if len(text) > width:
        text = text[: max(0, width - 1)] + "…"
    return _ansi(text, style) if color and style else text


def _truncate(text: str, width: int) -> str:
    if len(text) > width:
        return text[: max(0, width - 1)] + "…"
    return text


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def render_console(snapshot: DashboardSnapshot) -> str:
    """Render the snapshot to a string suitable for the terminal.

    Uses rich if available; otherwise falls back to plain ANSI text.
    """
    if _HAVE_RICH:
        buf = io.StringIO()
        console = Console(file=buf, width=Console().width, force_terminal=False, color_system=None)
        _render_to_console(console, snapshot)
        return buf.getvalue()

    return _render_plain(snapshot)


def _render_to_console(console: Console, snapshot: DashboardSnapshot) -> None:
    from rich.columns import Columns

    console.rule(f"[bold cyan]AIDLC Dashboard[/bold cyan] - {snapshot.project_name}")
    console.print(
        f"[dim]project:[/dim] {snapshot.project_root}    "
        f"[dim].cdh/:[/dim] {snapshot.cdh_dir or '(none)'}"
    )

    pairs: list[Panel] = []
    for _, result in snapshot.widgets:
        pairs.append(_render_widget_rich(console, result))

    # 2 columns x 3 rows
    for i in range(0, len(pairs), 2):
        row = pairs[i : i + 2]
        if len(row) == 1:
            console.print(row[0])
        else:
            console.print(Columns(row, equal=True, expand=True))


def _render_plain(snapshot: DashboardSnapshot) -> str:
    width = 80
    if _HAVE_RICH:
        try:
            width = max(80, Console().width)
        except Exception:
            width = 80

    widget_w = (width // 2) - 2
    out: list[str] = []
    out.append("=" * width)
    out.append(f"AIDLC Dashboard - {snapshot.project_name}".center(width))
    out.append("=" * width)
    out.append(f"project: {snapshot.project_root}    .cdh/: {snapshot.cdh_dir or '(none)'}")
    out.append("")

    rendered = [_render_widget_plain(r, width=widget_w) for _, r in snapshot.widgets]
    for i in range(0, len(rendered), 2):
        left = rendered[i].splitlines()
        right = rendered[i + 1].splitlines() if i + 1 < len(rendered) else [""]
        max_h = max(len(left), len(right))
        while len(left) < max_h:
            left.append(" " * widget_w)
        while len(right) < max_h:
            right.append(" " * widget_w)
        for a, b in zip(left, right):
            out.append(f"{a}  {b}")
        out.append("")

    out.append(f"generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    return "\n".join(out)


def render_markdown(snapshot: DashboardSnapshot) -> str:
    """Render the snapshot as a Markdown report."""
    lines: list[str] = []
    lines.append(f"# AIDLC Dashboard - {snapshot.project_name}")
    lines.append("")
    lines.append(f"- **Project root**: `{snapshot.project_root}`")
    lines.append(f"- **.cdh/**: `{snapshot.cdh_dir or '(none)'}`")
    lines.append(f"- **Generated**: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    for _, r in snapshot.widgets:
        lines.append(f"## {r.title}")
        lines.append("")
        if r.summary:
            lines.append(f"**{r.summary}**")
            lines.append("")
        if r.progress is not None:
            pct = r.progress * 100
            lines.append(f"- Progress: `{pct:.1f}%`")
        if r.rows:
            lines.append("")
            lines.append("| Item | Value | Status |")
            lines.append("|------|-------|--------|")
            for label, value, status in r.rows:
                _, icon = _STATUS_STYLES.get(status, ("white", "?"))
                lines.append(f"| {label} | {value} | {icon} |")
        if r.message:
            lines.append("")
            lines.append(f"> {r.message}")
        lines.append("")

    return "\n".join(lines)


def render_html(snapshot: DashboardSnapshot) -> str:
    """Render the snapshot as a self-contained HTML report."""
    rows_html: list[str] = []
    for _, r in snapshot.widgets:
        body_rows = "".join(
            f"<tr><td>{_html_escape(label)}</td><td>{_html_escape(value)}</td>"
            f"<td class='{status}'>{_html_escape(_STATUS_STYLES.get(status, ('', '?'))[1])}</td></tr>"
            for label, value, status in r.rows
        )
        progress_html = ""
        if r.progress is not None:
            pct = r.progress * 100
            progress_html = (
                f"<div class='progress'><div class='bar' style='width:{pct:.1f}%'></div>"
                f"<span>{pct:.1f}%</span></div>"
            )
        msg_html = f"<p class='msg'>{_html_escape(r.message)}</p>" if r.message else ""
        rows_html.append(
            f"""
            <section class='widget'>
              <h2>{_html_escape(r.title)}</h2>
              <p class='summary'><strong>{_html_escape(r.summary)}</strong></p>
              {progress_html}
              <table>
                <thead><tr><th>Item</th><th>Value</th><th>Status</th></tr></thead>
                <tbody>{body_rows}</tbody>
              </table>
              {msg_html}
            </section>
            """
        )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>AIDLC Dashboard - {_html_escape(snapshot.project_name)}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         margin: 2rem; color: #222; }}
  h1 {{ border-bottom: 2px solid #0aa; padding-bottom: .3rem; }}
  .grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 1rem; }}
  .widget {{ border: 1px solid #ddd; border-radius: 8px; padding: 1rem;
             background: #fafafa; }}
  .summary {{ margin: 0 0 .5rem 0; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ text-align: left; padding: .25rem .5rem; border-bottom: 1px solid #eee; }}
  .pass {{ color: #0a0; }}
  .fail {{ color: #c00; }}
  .warn {{ color: #c80; }}
  .info {{ color: #06c; }}
  .progress {{ background:#eee; border-radius:4px; height:14px; position:relative;
              margin-bottom:.5rem; }}
  .progress .bar {{ background:#0aa; height:100%; border-radius:4px; }}
  .progress span {{ position:absolute; right:.5rem; top:0; font-size:.75rem; }}
  .msg {{ color:#666; font-style:italic; }}
</style>
</head>
<body>
  <h1>AIDLC Dashboard - {_html_escape(snapshot.project_name)}</h1>
  <p><strong>Project root:</strong> <code>{_html_escape(str(snapshot.project_root))}</code><br>
     <strong>.cdh/:</strong> <code>{_html_escape(str(snapshot.cdh_dir) if snapshot.cdh_dir else '(none)')}</code><br>
     <strong>Generated:</strong> {time.strftime('%Y-%m-%d %H:%M:%S')}</p>
  <div class='grid'>
    {''.join(rows_html)}
  </div>
</body>
</html>
"""


def _html_escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ---------------------------------------------------------------------------
# CLI driver
# ---------------------------------------------------------------------------


def run_dashboard(
    workspace_root: Optional[Path] = None,
    *,
    watch: bool = False,
    interval: float = 2.0,
    export_path: Optional[Path] = None,
) -> int:
    """Render the dashboard once, repeatedly (watch), or export to a file.

    Args:
        workspace_root: Path to scan for .cdh/. Defaults to cwd.
        watch:          If True, re-render every ``interval`` seconds.
        interval:       Seconds between refreshes in watch mode.
        export_path:    If given, write a snapshot (Markdown or HTML) and
                        exit without entering watch mode.

    Returns:
        Process exit code (0 on success, 2 on missing project root when
        explicitly required, 1 on export errors).
    """
    ws = (workspace_root or Path.cwd()).expanduser().resolve()

    if export_path is not None:
        snap = collect_snapshot(ws)
        suffix = export_path.suffix.lower()
        try:
            export_path.parent.mkdir(parents=True, exist_ok=True)
            if suffix in (".html", ".htm"):
                export_path.write_text(render_html(snap), encoding="utf-8")
            else:
                export_path.write_text(render_markdown(snap), encoding="utf-8")
        except Exception as e:
            print(f"Failed to export dashboard: {e}", file=sys.stderr)
            return 1
        print(f"Wrote dashboard snapshot to {export_path}")
        return 0

    if not watch:
        snap = collect_snapshot(ws)
        print(render_console(snap))
        return 0

    # Watch mode
    if _HAVE_RICH:
        return _run_watch_rich(ws, interval)
    return _run_watch_plain(ws, interval)


def _run_watch_plain(workspace_root: Path, interval: float) -> int:
    """Plain (no-rich) watch loop with screen clears."""
    try:
        while True:
            snap = collect_snapshot(workspace_root)
            sys.stdout.write("\x1b[2J\x1b[H")
            sys.stdout.write(render_console(snap))
            sys.stdout.flush()
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nwatch stopped")
        return 0


def _run_watch_rich(workspace_root: Path, interval: float) -> int:
    """Rich-powered watch loop using Live for clean refreshes."""
    from rich.live import Live

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        transient=True,
    )
    task_id = progress.add_task("Refreshing dashboard...", total=None)

    def _make_layout() -> Any:
        snap = collect_snapshot(workspace_root)
        return _build_rich_group(snap, progress)

    try:
        with Live(_make_layout(), refresh_per_second=4, screen=True) as live:
            while True:
                progress.update(task_id, description="Refreshing dashboard...")
                live.update(_make_layout())
                time.sleep(interval)
    except KeyboardInterrupt:
        return 0


def _build_rich_group(snapshot: DashboardSnapshot, progress: Progress) -> Any:
    from rich.columns import Columns
    from rich.console import Group

    header_parts: list[Any] = [
        Text(f"AIDLC Dashboard - {snapshot.project_name}", style="bold cyan"),
        Text(
            f"project: {snapshot.project_root}    .cdh/: {snapshot.cdh_dir or '(none)'}",
            style="dim",
        ),
        progress,
        "",
    ]

    pairs: list[Panel] = []
    for _, result in snapshot.widgets:
        pairs.append(_render_widget_rich(Console(record=True), result))

    body_parts: list[Any] = []
    for i in range(0, len(pairs), 2):
        row = pairs[i : i + 2]
        body_parts.append(Columns(row, equal=True, expand=True))

    return Group(*header_parts, *body_parts)