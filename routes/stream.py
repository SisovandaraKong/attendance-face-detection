"""
routes/stream.py
─────────────────────────────────────────────────────────────
MJPEG webcam stream endpoint.

The browser's <img src="/stream"> tag keeps this connection open
permanently and receives a continuous JPEG-over-HTTP stream.
─────────────────────────────────────────────────────────────
"""

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter()


@router.get("/stream", tags=["stream"])
async def video_stream(request: Request) -> StreamingResponse:
    """
    Serve the live webcam feed as a multipart MJPEG stream.

    The FaceService instance is retrieved from app.state so it is
    never re-instantiated per request.
    """
    face_service = request.app.state.face_service
    return StreamingResponse(
        face_service.generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
