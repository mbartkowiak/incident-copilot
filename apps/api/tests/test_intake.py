import base64
import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.deps import get_attachment_rate_limiter, get_attachment_reader
from app.main import create_app
from app.services.intake import (
    MAX_BYTES,
    AttachmentReader,
    InvalidAttachment,
    TicketText,
    content_blocks,
    sniff,
    to_attachments,
)
from app.services.ratelimit import RateLimiter
from tests.test_agent import ScriptedClient, final

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
PDF = b"%PDF-1.7\n" + b"\x00" * 32
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 32

FACTS: dict[str, Any] = {
    "attachment_summary": "Handheld screen showing a WMS host-unreachable error.",
    "error_messages": ["Host not reachable"],
    "device_or_asset": "HH-MEM-015",
    "application": "WMS Mobile",
    "site": "Memphis DC",
    "scope": "single user",
    "first_seen": "05:42",
    "suggested_short_description": "Handheld HH-MEM-015 can't reach WMS host",
    "description_addendum": "Screen shows 'Host not reachable'; Wi-Fi certificate expired.",
    "sensitive_data": [],
}


@pytest.mark.parametrize(
    ("data", "expected"),
    [(PNG, "image/png"), (JPEG, "image/jpeg"), (PDF, "application/pdf"), (WEBP, "image/webp"),
     (b"GIF89a....", "image/gif"), (b"MZ\x90\x00 exe", None), (b"<svg></svg>", None)],
)  # fmt: skip
def test_file_type_comes_from_content(data: bytes, expected: str | None) -> None:
    assert sniff(data) == expected


@pytest.mark.parametrize(
    ("files", "message"),
    [
        ([], "at least one"),
        ([("a.png", PNG)] * 4, "at most 3"),
        ([("empty.png", b"")], "empty"),
        ([("big.png", PNG + b"\x00" * MAX_BYTES)], "larger than 5 MB"),
        ([("evil.png", b"MZ\x90\x00")], "isn't a PNG"),  # renamed executable
    ],
)
def test_invalid_uploads_are_refused(files: list[tuple[str, bytes]], message: str) -> None:
    with pytest.raises(InvalidAttachment, match=message):
        to_attachments(files)


def test_blocks_put_files_before_the_ticket_text() -> None:
    attachments = to_attachments([("screen.png", PNG), ("notice.pdf", PDF)])

    blocks = content_blocks(TicketText("Scanner down", ""), attachments)

    assert [b["type"] for b in blocks] == ["image", "document", "text"]
    assert blocks[0]["source"]["media_type"] == "image/png"
    assert base64.b64decode(blocks[1]["source"]["data"]) == PDF
    assert "Attachments: screen.png, notice.pdf" in blocks[2]["text"]
    assert "Ticket description: (none yet)" in blocks[2]["text"]


@pytest.fixture
def claude() -> ScriptedClient:
    return ScriptedClient(final(json.dumps(FACTS)))


@pytest.fixture
def client(claude: ScriptedClient) -> Iterator[TestClient]:
    app = create_app()
    limiter = RateLimiter(2, 600, 100, what="attachment reads")
    app.dependency_overrides[get_attachment_reader] = lambda: AttachmentReader(claude, "m")
    app.dependency_overrides[get_attachment_rate_limiter] = lambda: limiter
    yield TestClient(app)


def test_attachments_are_read_into_facts(client: TestClient, claude: ScriptedClient) -> None:
    response = client.post(
        "/api/triage/attachments",
        files=[("files", ("screen.png", PNG, "image/png"))],
        data={"short_description": "Scanner not syncing"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["facts"]["device_or_asset"] == "HH-MEM-015"
    assert body["files"] == [{"name": "screen.png", "media_type": "image/png", "bytes": len(PNG)}]
    sent = claude.calls[0]
    assert sent["output_config"]["format"]["schema"]["properties"]["site"]["enum"][-1] == ""
    assert sent["messages"][0]["content"][-1]["text"].startswith("Attachments: screen.png")


def test_declared_type_is_ignored(client: TestClient, claude: ScriptedClient) -> None:
    response = client.post(
        "/api/triage/attachments",
        files=[("files", ("notice.png", PDF, "image/png"))],  # a PDF claiming to be a PNG
    )

    assert response.status_code == 200
    assert response.json()["files"][0]["media_type"] == "application/pdf"
    assert claude.calls[0]["messages"][0]["content"][0]["type"] == "document"


def test_bad_uploads_never_reach_the_model(client: TestClient, claude: ScriptedClient) -> None:
    bad = client.post("/api/triage/attachments", files=[("files", ("x.png", b"MZ", "image/png"))])
    none = client.post("/api/triage/attachments", data={"short_description": "no files"})

    assert bad.status_code == 422
    assert "isn't a PNG" in bad.json()["detail"]
    assert none.status_code == 422
    assert claude.calls == []


def test_oversized_bodies_are_refused_before_parsing(client: TestClient) -> None:
    response = client.post(
        "/api/triage/attachments",
        content=b"x",
        headers={"content-type": "multipart/form-data; boundary=b", "content-length": "99999999"},
    )

    assert response.status_code == 413


def test_model_facts_are_validated(claude: ScriptedClient) -> None:
    app = create_app()
    bad = ScriptedClient(final(json.dumps(FACTS | {"site": "Mars Base"})))
    app.dependency_overrides[get_attachment_reader] = lambda: AttachmentReader(bad, "m")
    app.dependency_overrides[get_attachment_rate_limiter] = lambda: RateLimiter(5, 600, 100)

    response = TestClient(app).post(
        "/api/triage/attachments", files=[("files", ("s.png", PNG, "image/png"))]
    )

    assert response.status_code == 502


def test_reads_are_rate_limited(client: TestClient) -> None:
    for _ in range(2):
        ok = client.post("/api/triage/attachments", files=[("files", ("s.png", PNG, "image/png"))])
        assert ok.status_code == 200
    limited = client.post("/api/triage/attachments", files=[("files", ("s.png", PNG, "image/png"))])

    assert limited.status_code == 429
    assert "attachment reads" in limited.json()["detail"]
