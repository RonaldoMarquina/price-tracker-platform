"""Main entrypoint for Price Tracker Platform Backend API."""

import uuid

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.exceptions import AppException
from app.core.middleware import RequestIDMiddleware

_docs_enabled = settings.DOCS_ENABLED and settings.ENVIRONMENT.lower() not in ("production", "prod")

app = FastAPI(
    title="Price Tracker Platform API",
    description="API REST para consultar el catálogo e historial de precios de componentes de PC.",
    version="0.1.0",
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)

origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestIDMiddleware)


def _get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", str(uuid.uuid4()))


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handle custom application domain exceptions with canonical format."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": _get_request_id(request),
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle 422 validation errors with canonical format."""
    details = [
        {
            "loc": [str(x) for x in err.get("loc", [])],
            "msg": err.get("msg", ""),
            "type": err.get("type", ""),
        }
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Parámetros de solicitud inválidos.",
                "request_id": _get_request_id(request),
                "details": details,
            }
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle generic Starlette HTTP exceptions with canonical error envelope."""
    code = "HTTP_ERROR"
    if exc.status_code == 404:
        code = "NOT_FOUND"
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": code,
                "message": str(exc.detail),
                "request_id": _get_request_id(request),
            }
        },
    )


@app.get("/health", tags=["Health"])
def health_check() -> dict[str, str]:
    """Basic health check endpoint for monitoring."""
    return {
        "status": "ok",
        "service": "backend",
        "environment": settings.ENVIRONMENT,
    }


# Include API v1 router
app.include_router(api_v1_router)
