import logging
from typing import Annotated

import anthropic
from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

# request.form() yields Starlette's UploadFile; FastAPI's is a subclass it never produces.
from starlette.datastructures import UploadFile

from app import telemetry
from app.auth import require
from app.deps import get_attachment_rate_limiter, get_attachment_reader, get_triage_service
from app.models import AttachmentInfo, AttachmentReadResponse, TriageRequest, TriageSuggestion
from app.services.intake import (
    MAX_BYTES,
    MAX_FILES,
    AttachmentReader,
    InvalidAttachment,
    TicketText,
    to_attachments,
)
from app.services.ratelimit import RateLimiter
from app.services.structured import StructuredCallFailed
from app.services.triage import TriageService

router = APIRouter(prefix="/api/triage", tags=["triage"])
log = logging.getLogger(__name__)

# Room for the files plus the form's text fields and multipart framing.
MAX_BODY = MAX_FILES * MAX_BYTES + 64 * 1024


@router.post("/suggest", dependencies=[Depends(require("dispatcher"))])
def suggest(
    request: TriageRequest, svc: Annotated[TriageService, Depends(get_triage_service)]
) -> TriageSuggestion:
    return svc.suggest(request)


@router.post("/attachments", dependencies=[Depends(require("employee", "dispatcher"))])
async def read_attachments(
    request: Request,
    reader: Annotated[AttachmentReader, Depends(get_attachment_reader)],
    limiter: Annotated[RateLimiter, Depends(get_attachment_rate_limiter)],
) -> AttachmentReadResponse:
    """Read screenshots or PDFs attached to a new ticket into facts for the dispatcher to
    review. Multipart form: `files` (1-3) plus optional `short_description` and `description`.
    Files are validated by content, kept in memory for this request only, and never stored."""
    # Refuse oversized bodies before parsing, so they are never spooled.
    length = request.headers.get("content-length")
    if length is None or not length.isdigit():
        raise HTTPException(411, "Content-Length is required.")
    if int(length) > MAX_BODY:
        raise HTTPException(413, f"Attachments are limited to {MAX_FILES} files of 5 MB.")

    form = await request.form(max_files=MAX_FILES, max_fields=4)
    uploads = [f for f in form.getlist("files") if isinstance(f, UploadFile)]
    try:
        attachments = to_attachments([(u.filename or "", await u.read()) for u in uploads])
    except InvalidAttachment as e:
        raise HTTPException(422, str(e)) from None
    finally:
        await form.close()
    ticket = TicketText(
        short_description=str(form.get("short_description") or "")[:200],
        description=str(form.get("description") or "")[:4000],
    )

    limiter.check(request.client.host if request.client else "unknown")
    info = [
        AttachmentInfo(name=a.name, media_type=a.media_type, bytes=len(a.data)) for a in attachments
    ]
    try:
        result = await run_in_threadpool(reader.read, ticket, attachments)
    except anthropic.APIError as e:
        log.error("attachment read failed: %s", e)
        telemetry.emit("attachment_read", outcome="anthropic_error", files=len(info))
        raise HTTPException(503, "The AI service is unavailable right now.") from None
    except StructuredCallFailed as e:
        telemetry.emit("attachment_read", outcome="failed", files=len(info), error=str(e))
        raise HTTPException(502, "The AI couldn't read these attachments. Try again.") from None

    telemetry.emit(
        "attachment_read",
        outcome="ok",
        files=len(info),
        media_types=sorted({a.media_type for a in info}),
        total_bytes=sum(a.bytes for a in info),
        errors_found=len(result.value.error_messages),
        sensitive_kinds=result.value.sensitive_data,
        model=result.model,
        latency_s=result.latency_s,
        cost_usd=result.cost_usd,
        input_tokens=result.usage.input_tokens,
    )
    return AttachmentReadResponse(
        facts=result.value,
        files=info,
        model=result.model,
        cost_usd=result.cost_usd,
        latency_s=result.latency_s,
    )
