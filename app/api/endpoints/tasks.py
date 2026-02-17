from __future__ import annotations

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import StreamingResponse

from app.api.handlers.workflow_generation_review import (
    enqueue_ingest_directory_handler,
    enqueue_ingest_handler,
    task_status_handler,
    task_status_stream_handler,
)
from app.schemas.contracts import (
    BatchIngestDirectoryRequest,
    BatchIngestDirectoryResponse,
    EnqueueIngestResponse,
    TaskStatusResponse,
)

router = APIRouter()


def _ctx():
    from app.api import routes

    return routes


@router.post("/v1/tasks/ingest-upload", response_model=EnqueueIngestResponse)
async def enqueue_ingest(file: UploadFile = File(...)) -> EnqueueIngestResponse:
    ctx = _ctx()
    return await enqueue_ingest_handler(
        file=file,
        resolve_within_base_fn=ctx._resolve_within_base,
        upload_dir=ctx.settings.upload_dir,
        read_upload_with_limit_fn=ctx._read_upload_with_limit,
        ingest_document_task_obj=ctx.ingest_document_task,
        service_unavailable_exc_factory=ctx._service_unavailable,
    )


@router.post("/v1/tasks/ingest-directory", response_model=BatchIngestDirectoryResponse)
def enqueue_ingest_directory(payload: BatchIngestDirectoryRequest) -> BatchIngestDirectoryResponse:
    ctx = _ctx()
    return enqueue_ingest_directory_handler(
        payload,
        resolve_within_base_fn=ctx._resolve_within_base,
        upload_dir=ctx.settings.upload_dir,
        ingest_document_task_obj=ctx.ingest_document_task,
        service_unavailable_exc_factory=ctx._service_unavailable,
    )


@router.get("/v1/tasks/{task_id}", response_model=TaskStatusResponse)
def task_status(task_id: str) -> TaskStatusResponse:
    ctx = _ctx()
    return task_status_handler(task_id, get_task_result_fn=ctx.get_task_result)


@router.get("/v1/tasks/{task_id}/stream")
async def task_status_stream(task_id: str) -> StreamingResponse:
    ctx = _ctx()
    return await task_status_stream_handler(
        task_id,
        get_task_result_fn=ctx.get_task_result,
        timeout_seconds=ctx.settings.task_status_stream_timeout_seconds,
    )
