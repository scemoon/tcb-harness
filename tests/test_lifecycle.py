import pytest
from cdha.lifecycle.manager import (
    LifecycleManager,
    LifecycleStage,
    StageStatus,
    STAGE_ORDER,
)


def test_initial_state():
    lm = LifecycleManager()
    assert lm.current == LifecycleStage.NONE
    for stage in STAGE_ORDER:
        assert lm.stages[stage] == StageStatus.PENDING


def test_start_spec():
    lm = LifecycleManager()
    lm.start(LifecycleStage.SPEC)
    assert lm.current == LifecycleStage.SPEC
    assert lm.stages[LifecycleStage.SPEC] == StageStatus.IN_PROGRESS


def test_complete_spec():
    lm = LifecycleManager()
    lm.start(LifecycleStage.SPEC)
    lm.complete(LifecycleStage.SPEC)
    assert lm.stages[LifecycleStage.SPEC] == StageStatus.COMPLETED


def test_can_advance():
    lm = LifecycleManager()
    assert lm.can_advance_to(LifecycleStage.SPEC) is True
    assert lm.can_advance_to(LifecycleStage.DESIGN) is False
    lm.start(LifecycleStage.SPEC)
    lm.complete(LifecycleStage.SPEC)
    assert lm.can_advance_to(LifecycleStage.DESIGN) is True


def test_full_lifecycle():
    lm = LifecycleManager()
    lm.start(LifecycleStage.SPEC)
    lm.complete(LifecycleStage.SPEC)
    lm.start(LifecycleStage.DESIGN)
    lm.complete(LifecycleStage.DESIGN)
    lm.start(LifecycleStage.CODING)
    lm.complete(LifecycleStage.CODING)
    lm.start(LifecycleStage.TESTING)
    lm.complete(LifecycleStage.TESTING)
    lm.start(LifecycleStage.DEPLOY)
    lm.complete(LifecycleStage.DEPLOY)
    for stage in STAGE_ORDER:
        assert lm.stages[stage] == StageStatus.COMPLETED


def test_fail():
    lm = LifecycleManager()
    lm.start(LifecycleStage.SPEC)
    lm.fail(LifecycleStage.SPEC)
    assert lm.stages[LifecycleStage.SPEC] == StageStatus.FAILED


def test_summary():
    lm = LifecycleManager()
    summary = lm.summary()
    assert "Spec" in summary
    assert "Design" in summary
    assert "Testing" in summary
    assert "Deploy" in summary


def test_serialization():
    lm = LifecycleManager()
    lm.start(LifecycleStage.SPEC)
    lm.complete(LifecycleStage.SPEC)
    data = lm.to_dict()
    assert data["stages"]["spec"] == "completed"
    assert data["stages"]["design"] == "pending"
    lm2 = LifecycleManager()
    lm2.from_dict(data)
    assert lm2.stages[LifecycleStage.SPEC] == StageStatus.COMPLETED
    assert lm2.stages[LifecycleStage.DESIGN] == StageStatus.PENDING
