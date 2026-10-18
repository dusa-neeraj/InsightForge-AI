from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from config import settings

OVERHEAD_BYTES = 64 * 1024  # multipart boundaries and form fields


class UploadSizeLimit:
    """Refuses oversized uploads from the Content-Length header, before the body is read."""

    def __init__(self, app: ASGIApp, path: str = "/upload"):
        self.app = app
        self.path = path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] == "POST" and scope["path"] == self.path:
            length = dict(scope["headers"]).get(b"content-length")
            if length is None:
                response = JSONResponse({"error": "The Content-Length header is required."}, status_code=411)
                return await response(scope, receive, send)
            if not length.isdigit():
                response = JSONResponse({"error": "Invalid Content-Length header."}, status_code=400)
                return await response(scope, receive, send)
            if int(length) > settings.max_upload_bytes + OVERHEAD_BYTES:
                response = JSONResponse(
                    {"error": f"File is too large. Maximum size is {settings.max_upload_mb} MB."},
                    status_code=413,
                )
                return await response(scope, receive, send)
        await self.app(scope, receive, send)