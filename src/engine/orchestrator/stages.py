"""Stage model and transition rules for the coding orchestrator."""

from __future__ import annotations

from enum import Enum


class Stage(str, Enum):
    IDLE = "IDLE"
    PLAN = "PLAN"
    CODE = "CODE"
    TEST = "TEST"
    DEBUG = "DEBUG"
    REVIEW = "REVIEW"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class StageStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"


ALLOWED_TRANSITIONS: dict[Stage, set[Stage]] = {
    Stage.IDLE: {Stage.PLAN, Stage.FAILED},
    Stage.PLAN: {Stage.CODE, Stage.FAILED},
    Stage.CODE: {Stage.TEST, Stage.REVIEW, Stage.COMPLETE, Stage.FAILED},
    Stage.TEST: {Stage.DEBUG, Stage.REVIEW, Stage.COMPLETE, Stage.FAILED},
    Stage.DEBUG: {Stage.CODE, Stage.FAILED},
    Stage.REVIEW: {Stage.CODE, Stage.COMPLETE, Stage.FAILED},
    Stage.COMPLETE: set(),
    Stage.FAILED: set(),
}


class InvalidStageTransition(ValueError):
    """Raised when a task attempts an invalid stage transition."""


def can_transition(current: Stage | str, target: Stage | str) -> bool:
    """Return whether a task may move from ``current`` to ``target``."""
    current_stage = Stage(current)
    target_stage = Stage(target)
    return target_stage in ALLOWED_TRANSITIONS[current_stage]


def assert_transition(current: Stage | str, target: Stage | str) -> None:
    """Validate a stage transition or raise a deterministic error."""
    if not can_transition(current, target):
        raise InvalidStageTransition(f"invalid stage transition: {current} -> {target}")
