from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.candidates import router as candidates_router
from app.api.contents import router as contents_router
from app.api.generation import router as generation_router
from app.api.health import router as health_router
from app.api.jobs import router as jobs_router
from app.api.pipelines import router as pipelines_router
from app.api.products import router as products_router
from app.core.logging import setup_logging
from app.harness.pipeline import create_scheduler

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    scheduler = create_scheduler()
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Shopping SNS Auto Operation", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api/v1")
app.include_router(pipelines_router, prefix="/api/v1")
app.include_router(products_router, prefix="/api/v1")
app.include_router(candidates_router, prefix="/api/v1")
app.include_router(contents_router, prefix="/api/v1")
app.include_router(generation_router, prefix="/api/v1")
app.include_router(jobs_router, prefix="/api/v1")

_ERROR_CODES = {
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
}


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    code = _ERROR_CODES.get(exc.status_code, "INTERNAL")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": code, "message": str(exc.detail)}},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "VALIDATION_ERROR", "message": "Validation error"}},
    )
