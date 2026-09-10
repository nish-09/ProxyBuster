import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import admin, attendance, auth, professor, students, ws
from app.core.config import get_settings
from app.core.rate_limit import limiter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("proxybusters")

settings = get_settings()

# debug=False (the default) means Starlette never renders a traceback into the HTTP
# response body for an unhandled exception — only the generic 500 handler below runs.
# Kept explicit here so a future change to this line is a deliberate, reviewable diff.
app = FastAPI(title="Proxy Busters API", version="0.1.0", debug=False)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(attendance.router, prefix="/api")
app.include_router(students.router, prefix="/api")
app.include_router(professor.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(ws.router, prefix="/api")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Log the full exception server-side (Render captures stdout/stderr) but return only a
    # generic message to the client — never the exception text, which could echo back
    # internal details (query fragments, file paths, etc.) that shouldn't reach a browser.
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    # FastAPI's default HTTPException handler already returns {"detail": ...} without a
    # stack trace; this override exists only so 4xx responses go through the same
    # structured-logging path as 5xxs for consistency, at a quieter log level.
    logger.info("HTTP %s on %s %s: %s", exc.status_code, request.method, request.url.path, exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.info("422 validation error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.get("/health")
def health():
    return {"status": "ok"}
