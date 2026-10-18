import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from config import settings
from routes import chat, datasets, insights, lifecycle, preview, reports, sql, upload
from services import cleanup
from utils.errors import DatasetError
from utils.upload_limit import UploadSizeLimit

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

settings.upload_dir.mkdir(parents=True, exist_ok=True)
CLEANUP_INTERVAL_SECONDS = 3600


async def _cleanup_loop() -> None:
    while True:
        try:
            removed = await asyncio.to_thread(cleanup.remove_expired)
            if removed:
                logger.info("Removed %d expired dataset(s)", removed)
        except Exception:
            logger.exception("Dataset cleanup failed")
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_cleanup_loop())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title=settings.app_name, version="0.3.0", lifespan=lifespan)

# Middleware added last is outermost. CORS must be outermost, so even 413 and 429
# responses carry CORS headers and the browser can show their messages.
app.add_middleware(UploadSizeLimit)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins_list,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.exception_handler(DatasetError)
async def dataset_error_handler(request: Request, exc: DatasetError):
    return JSONResponse(
        status_code=exc.status_code, content={"error": exc.message}, headers=exc.headers
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    # Only the field and the message are returned. What the client sent is never echoed back.
    details = [
        {
            "field": ".".join(str(part) for part in item["loc"] if part not in ("body", "query", "path")),
            "message": item["msg"].removeprefix("Value error, "),
        }
        for item in exc.errors()
    ]
    summary = "; ".join(
        f"{d['field']}: {d['message']}" if d["field"] else d["message"] for d in details
    ) or "Invalid request."
    return JSONResponse(status_code=422, content={"error": summary, "details": details})


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    messages = {404: "Not found.", 405: "That method is not allowed here."}
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": messages.get(exc.status_code, "The request could not be completed.")},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error")
    return JSONResponse(
        status_code=500, content={"error": "Something went wrong on the server."}
    )


@app.get("/")
def home():
    return {"status": "running"}


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(upload.router)
app.include_router(datasets.router)
app.include_router(preview.router)
app.include_router(insights.router)
app.include_router(chat.router)
app.include_router(sql.router)
app.include_router(reports.router)
app.include_router(lifecycle.router)