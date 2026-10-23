"""Internal stateless compute API and the independent pull Worker in one process."""

import asyncio
import hmac
import logging
import os
import threading
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from devproof_agent.compute.document_parser import DocumentExtractionError, detect_media_type, supported_extensions
from devproof_agent.compute.processor import Computation
from devproof_agent.compute.git_capture import GitCapture
from devproof_agent.compute.git_types import GitCaptureRequest, GitSettings
from devproof_agent.compute.settings import ComputeSettings, digest
from devproof_agent.compute.types import ConfigurationResponse, DocumentInspection, EmbeddingBatchRequest
from devproof_agent.models import AgentError
from devproof_agent.worker import main as run_worker

LOG = logging.getLogger(__name__)


def observe_worker(task: asyncio.Task):
    if task.cancelled():
        return
    error = task.exception()
    LOG.error("pull_worker_stopped code=%s", error.code if isinstance(error, AgentError) else "WORKER_STOPPED")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.compute = ComputeSettings()
    app.state.git = GitSettings()
    app.state.slots = asyncio.Semaphore(app.state.compute.compute_concurrency)
    app.state.inspection_slots = asyncio.Semaphore(app.state.compute.compute_concurrency)
    worker = asyncio.create_task(run_worker(), name="agent-pull-worker")
    worker.add_done_callback(observe_worker)
    app.state.worker = worker
    try:
        yield
    finally:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)


app = FastAPI(title="DevProof internal computation", docs_url=None, redoc_url=None,
    openapi_url=None, lifespan=lifespan)


async def authenticate(request: Request):
    settings: ComputeSettings = request.app.state.compute
    supplied = request.headers.get("authorization", "")
    if not hmac.compare_digest(supplied.encode("utf-8"), ("Bearer " + settings.compute_service_token).encode("utf-8")):
        raise AgentError("COMPUTE_AUTH_INVALID", "内部计算身份校验失败")
    return settings


@app.exception_handler(AgentError)
async def failure(request: Request, exc: AgentError):
    code = 401 if exc.code == "COMPUTE_AUTH_INVALID" else 409 if exc.code in {
        "COMPUTE_CONFIG_CHANGED", "SOURCE_HASH_MISMATCH", "REPOSITORY_BUSY"} else 413 if exc.code in {
        "SOURCE_TOO_LARGE", "COMPUTE_RESULT_TOO_LARGE"} else 422 if exc.code.startswith(("SOURCE_MEDIA_", "SOURCE_ENCODING_")) or exc.code in {
        "COMPUTE_INPUT_INVALID", "SOURCE_EMPTY", "SOURCE_PARSER_FAILED", "MODEL_SCHEMA_INVALID",
        "GIT_RANGE_INVALID", "GIT_DIFF_EMPTY", "GIT_SHA_INVALID"} else 503
    return JSONResponse(status_code=code, content={"code": exc.code, "message": exc.message})


@app.get("/internal/v1/compute/configuration", dependencies=[Depends(authenticate)])
async def configuration(request: Request):
    settings = request.app.state.compute
    return ConfigurationResponse(configuration=settings.configuration(), configurationHash=settings.configuration_hash(),
        embeddingCredentialConfigured=bool(settings.embedding_api_key and settings.embedding_api_key.strip()),
        mineruCredentialConfigured=bool(settings.mineru_api_token and settings.mineru_api_token.strip()),
        supportedExtensions=supported_extensions())


@app.get("/internal/v1/health/live")
async def live(request: Request):
    worker = request.app.state.worker
    return {"status": "live", "workerStatus": "STOPPED" if worker.done() else "RUNNING"}


async def read_body(request: Request, limit: int) -> bytes:
    body = bytearray()
    async for part in request.stream():
        body.extend(part)
        if len(body) > limit:
            raise AgentError("SOURCE_TOO_LARGE", "计算输入超过服务端配置的大小上限")
    return bytes(body)


@asynccontextmanager
async def computation_slot(request: Request, *, inspection: bool = False):
    gate = request.app.state.inspection_slots if inspection else request.app.state.slots
    if gate.locked():
        raise AgentError("COMPUTE_BUSY", "内部计算执行槽已占用，请稍后重试")
    await gate.acquire()
    try:
        yield
    finally:
        gate.release()


async def calculate(request: Request, operation):
    stop = threading.Event()

    async def watch_disconnect():
        while not await request.is_disconnected():
            await asyncio.sleep(0.5)
        stop.set()

    monitor = asyncio.create_task(watch_disconnect())
    try:
        # Keep the bounded execution slot until the synchronous provider work returns.
        try:
            result = await run_in_threadpool(operation, Computation(request.app.state.compute, stop.is_set))
        except AgentError:
            raise
        except Exception as exc:
            LOG.warning("compute_failed type=%s", type(exc).__name__)
            raise AgentError("COMPUTE_FAILED", "资料解析或计算失败，请检查实际服务响应和输入格式") from None
        raw = result.model_dump_json().encode("utf-8")
        if len(raw) > request.app.state.compute.compute_result_max_bytes:
            raise AgentError("COMPUTE_RESULT_TOO_LARGE", "计算结果超过配置的返回上限")
        return Response(content=raw, media_type="application/json")
    finally:
        stop.set()
        monitor.cancel()
        await asyncio.gather(monitor, return_exceptions=True)


@app.post("/internal/v1/compute/documents/inspect")
async def inspect(request: Request, filename: str, settings: ComputeSettings = Depends(authenticate)):
    async with computation_slot(request, inspection=True):
        raw = await read_body(request, settings.source_max_bytes)
        try:
            media = await run_in_threadpool(detect_media_type, filename=filename, claimed_media_type=None, content=raw)
        except DocumentExtractionError as exc:
            raise AgentError(exc.code, exc.message) from None
        return DocumentInspection(contentHash=digest(raw), mediaType=media, byteSize=len(raw))


@app.get("/internal/v1/compute/git/configuration", dependencies=[Depends(authenticate)])
async def git_configuration(request: Request):
    settings = request.app.state.git
    return {"configuration": settings.configuration(), "configurationHash": settings.configuration_hash()}


@app.post("/internal/v1/compute/git/capture")
async def git_capture(request: Request, settings: ComputeSettings = Depends(authenticate)):
    async with computation_slot(request):
        raw = await read_body(request, 1048576)
        try:
            body = GitCaptureRequest.model_validate_json(raw)
        except ValidationError:
            raise AgentError("COMPUTE_INPUT_INVALID", "Git 采集请求不符合契约") from None
        return await calculate(request, lambda computation:
            GitCapture(request.app.state.git, computation.cancelled).capture(body, digest(raw)))


@app.post("/internal/v1/compute/documents/extract")
async def extract(request: Request, filename: str, forceOcr: bool = False,
                  settings: ComputeSettings = Depends(authenticate)):
    async with computation_slot(request):
        if request.headers.get("x-compute-configuration-hash") != settings.configuration_hash():
            raise AgentError("COMPUTE_CONFIG_CHANGED", "资料计算配置与冻结任务不一致")
        raw = await read_body(request, settings.source_max_bytes)
        if request.headers.get("x-content-hash") != digest(raw):
            raise AgentError("SOURCE_HASH_MISMATCH", "资料实际字节与冻结摘要不一致")
        return await calculate(request, lambda computation: computation.extract(raw, filename, forceOcr))


@app.post("/internal/v1/compute/embeddings")
async def embeddings(request: Request, settings: ComputeSettings = Depends(authenticate)):
    async with computation_slot(request):
        raw = await read_body(request, min(settings.source_max_bytes, 32 * 1024 * 1024))
        try:
            body = EmbeddingBatchRequest.model_validate_json(raw)
        except ValidationError:
            raise AgentError("COMPUTE_INPUT_INVALID", "嵌入计算请求不符合契约") from None
        if body.configurationHash != settings.configuration_hash():
            raise AgentError("COMPUTE_CONFIG_CHANGED", "嵌入配置与冻结任务不一致")
        return await calculate(request, lambda computation: computation.embed(body.texts))


@app.post("/internal/v1/compute/documents/rechunk")
async def rechunk(request: Request, settings: ComputeSettings = Depends(authenticate)):
    async with computation_slot(request):
        if request.headers.get("x-compute-configuration-hash") != settings.configuration_hash():
            raise AgentError("COMPUTE_CONFIG_CHANGED", "索引解析配置与冻结任务不一致")
        raw = await read_body(request, settings.compute_result_max_bytes)
        if request.headers.get("x-content-hash") != digest(raw):
            raise AgentError("SOURCE_HASH_MISMATCH", "规范化资料与冻结摘要不一致")
        return await calculate(request, lambda computation: computation.rechunk(raw))


if __name__ == "__main__":
    import uvicorn
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    uvicorn.run(app, host=os.environ.get("COMPUTE_HOST", "0.0.0.0"), port=int(os.environ.get("COMPUTE_PORT", "8090")),
        access_log=False, timeout_graceful_shutdown=35)
