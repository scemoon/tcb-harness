from __future__ import annotations

from cdh.lifecycle.manager import LifecycleStage
from cdh.tui.commands.registry import command


@command("spec generate", "Generate specification")
def cmd_spec_generate(app, *args):
    desc = " ".join(args) or "Project specification"
    app.lifecycle.start(LifecycleStage.SPEC)
    app.lifecycle.spec_content = app.lifecycle.spec_content or desc
    return f"Spec generated: {desc[:100]}... Use /spec accept to confirm."


@command("spec accept", "Accept spec and move to Design")
def cmd_spec_accept(app, *args):
    if app.lifecycle.current != LifecycleStage.SPEC:
        return "No active spec phase."
    app.lifecycle.complete(LifecycleStage.SPEC)
    return "Spec accepted. Moving to Design phase."


@command("design generate", "Generate technical design")
def cmd_design_generate(app, *args):
    desc = " ".join(args) or "Technical design"
    app.lifecycle.start(LifecycleStage.DESIGN)
    app.lifecycle.design_content = app.lifecycle.design_content or desc
    return f"Design generated: {desc[:100]}... Use /design accept to confirm."


@command("design accept", "Accept design and move to Testing")
def cmd_design_accept(app, *args):
    if app.lifecycle.current != LifecycleStage.DESIGN:
        return "No active design phase."
    app.lifecycle.complete(LifecycleStage.DESIGN)
    return "Design accepted. Moving to Testing phase."


@command("test run", "Run tests")
def cmd_test_run(app, *args):
    app.lifecycle.start(LifecycleStage.TESTING)
    return "Test execution started. Use /test accept when ready."


@command("test accept", "Accept tests and move to Deploy")
def cmd_test_accept(app, *args):
    if app.lifecycle.current != LifecycleStage.TESTING:
        return "No active testing phase."
    app.lifecycle.complete(LifecycleStage.TESTING)
    return "Tests accepted. Moving to Deploy phase."


@command("deploy", "Deploy to cloud")
def cmd_deploy(app, *args):
    cloud = args[0] if args else app.current_cloud
    app.lifecycle.start(LifecycleStage.DEPLOY)
    app.lifecycle.deploy_version = "v1.0.0"
    app.lifecycle.complete(LifecycleStage.DEPLOY)
    return f"Deployed to {cloud} (v1.0.0). Use /deploy status to check."
