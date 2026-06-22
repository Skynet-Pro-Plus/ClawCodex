"""Tool execution routes."""

from __future__ import annotations

from fastapi import APIRouter

from src.engine.tools.base import ToolContext
from src.engine.tools.commands import run_command
from src.engine.tools.filesystem import read_file, write_file
from src.engine.tools.git import git_diff
from src.engine.tools.search import search_repo
from src.engine.tools.tests import run_tests
from src.server.schemas import (
    ApiEnvelope,
    GitDiffRequest,
    ReadFileRequest,
    RunCommandRequest,
    RunTestsRequest,
    SearchRepoRequest,
    WriteFileRequest,
)

router = APIRouter()


@router.post("/read_file")
def api_read_file(payload: ReadFileRequest) -> ApiEnvelope:
    return ApiEnvelope(
        data=read_file(
            payload.path,
            payload.start_line,
            payload.end_line,
            task_id=payload.task_id,
            repo_path=payload.repo_path,
        )
    )


@router.post("/write_file")
def api_write_file(payload: WriteFileRequest) -> ApiEnvelope:
    return ApiEnvelope(
        data=write_file(
            payload.path,
            payload.content,
            payload.mode,
            task_id=payload.task_id,
            repo_path=payload.repo_path,
            allowed_paths=payload.allowed_paths,
            denied_paths=payload.denied_paths,
        )
    )


@router.post("/search_repo")
def api_search_repo(payload: SearchRepoRequest) -> ApiEnvelope:
    return ApiEnvelope(data=search_repo(payload.query, payload.kind, payload.limit, repo_path=payload.repo_path, task_id=payload.task_id))


@router.post("/run_command")
def api_run_command(payload: RunCommandRequest) -> ApiEnvelope:
    context = ToolContext(task_id=payload.task_id, repo_path=payload.repo_path, confirmed=payload.confirmed)
    return ApiEnvelope(data=run_command(payload.command, payload.timeout_sec, payload.requires_confirmation, context=context))


@router.post("/run_tests")
def api_run_tests(payload: RunTestsRequest) -> ApiEnvelope:
    context = ToolContext(task_id=payload.task_id, repo_path=payload.repo_path, confirmed=True)
    return ApiEnvelope(data=run_tests(payload.command, payload.target, payload.timeout_sec, context=context))


@router.post("/git_diff")
def api_git_diff(payload: GitDiffRequest) -> ApiEnvelope:
    return ApiEnvelope(data=git_diff(payload.base, payload.paths, repo_path=payload.repo_path))
