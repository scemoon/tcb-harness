import pytest
from pathlib import Path
from cdh.storage.project import ProjectConfig


def test_create_project(tmp_path):
    project = ProjectConfig.create("test-proj", tmp_path / "test-proj")
    assert (tmp_path / "test-proj").exists()
    assert (tmp_path / "test-proj" / "cdh.project.yaml").exists()
    assert project.get("name") == "test-proj"


def test_project_config(tmp_path):
    project = ProjectConfig.create("cfg-test", tmp_path / "cfg-test")
    project.set("custom_key", "custom_value")
    project.save()
    project2 = ProjectConfig(tmp_path / "cfg-test")
    assert project2.get("custom_key") == "custom_value"
