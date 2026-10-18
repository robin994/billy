"""Security and media path tests for the optional PDF archive (no HA required)."""
import asyncio
import ast
import hashlib
import os
from pathlib import Path
import re
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import uuid4

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "custom_components" / "bill_tracker" / "document_archive.py"
TREE = ast.parse(SOURCE.read_text(encoding="utf-8"))
NAMES = {
    "normalize_archive_config", "allowed_document_url", "media_root",
    "safe_archive_path", "_store_pdf", "archive_pdf_bytes",
    "validate_owned_pdf_path", "_delete_archived_pdf", "delete_archived_pdf",
}
FUNCTIONS = [
    item for item in TREE.body
    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name in NAMES
]
ns = {
    "re": re, "Path": Path, "os": os, "urlsplit": urlsplit, "uuid4": uuid4,
    "hashlib": hashlib, "MAX_PDF_BYTES": 8 * 1024 * 1024,
    "_PART": re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}$"),
}
MODULE = ast.Module(body=FUNCTIONS, type_ignores=[])
ast.fix_missing_locations(MODULE)
exec(compile(MODULE, str(SOURCE), "exec"), ns)


class HassStub:
    def __init__(self, root):
        self.config = SimpleNamespace(media_dirs={"local": str(root)})

    async def async_add_executor_job(self, callback, *args):
        return callback(*args)


def test_archive_config_rejects_traversal_and_bad_host():
    normalize = ns["normalize_archive_config"]
    assert normalize(None)["enabled"] is False
    assert normalize({"enabled": True, "subpath": "billy/2026", "source_host": "server.local:8080"}) == {
        "enabled": True, "subpath": "billy/2026", "source_host": "server.local:8080",
    }
    for path in ["../../outside", "billy/../outside", "/../outside", "billy//outside", "billy/some folder"]:
        with pytest.raises(ValueError):
            normalize({"subpath": path})
    for host in ["example.org/path", "user:pass@example.org", "example.org?x=y"]:
        with pytest.raises(ValueError):
            normalize({"source_host": host})


def test_download_url_requires_exact_preapproved_host_and_suppresses_credentials():
    check = ns["allowed_document_url"]
    assert check("https://paperless.local:8000/api/doc.pdf", "paperless.local:8000") == (
        "https://paperless.local:8000/api/doc.pdf"
    )
    for url in [
        "https://other.local/api/pdf",
        "https://paperless.local.evil.tld/api/pdf",
        "file:///etc/passwd",
        "https://admin:secret@paperless.local:8000/document",
        "https://paperless.local:8001/document",
    ]:
        with pytest.raises(ValueError):
            check(url, "paperless.local:8000")


def test_archiving_pdf_writes_ordered_media_path_without_overwrite_collisions(tmp_path):
    hass = HassStub(tmp_path)
    category = {"name": "Electricity & Gas", "document_archive": {
        "enabled": True, "subpath": "billy/documents", "source_host": "",
    }}
    bill = {"paid_year": 2026, "paid_month": 10, "id": "bill001"}
    content = b"%PDF-1.4\n" + b"sample PDF bytes"
    relative, sha = asyncio.run(ns["archive_pdf_bytes"](hass, bill, category, content))
    assert relative.startswith("billy/documents/2026/10/Electricity-Gas/bill001-")
    assert relative.endswith(".pdf")
    assert sha == hashlib.sha256(content).hexdigest()
    assert (tmp_path / relative).read_bytes() == content
    assert len(list(tmp_path.rglob("*.tmp"))) == 0
    with pytest.raises(ValueError, match="not a PDF"):
        asyncio.run(ns["archive_pdf_bytes"](hass, bill, category, b"fake"))
    with pytest.raises(ValueError, match="8 MiB"):
        asyncio.run(ns["archive_pdf_bytes"](
            hass, bill, category, b"%PDF-" + b"x" * (8 * 1024 * 1024)
        ))


def test_file_paths_cannot_escape_media_via_dot_segments_or_symlinks(tmp_path):
    hass = HassStub(tmp_path / "media")
    (tmp_path / "media").mkdir()
    (tmp_path / "private").mkdir()
    resolver = ns["safe_archive_path"]
    with pytest.raises(ValueError):
        resolver(hass, "billy/../private.pdf")
    with pytest.raises(ValueError):
        resolver(hass, "billy//private.pdf")
    (tmp_path / "media" / "symlink").symlink_to(tmp_path / "private", target_is_directory=True)
    with pytest.raises(ValueError, match="outside"):
        resolver(hass, "symlink/private.pdf")


def test_manual_upload_works_without_automatic_archive_and_can_be_removed(tmp_path):
    hass = HassStub(tmp_path)
    bill = {"paid_year": 2026, "paid_month": 10, "id": "bill001"}
    category = {"name": "Gas", "document_archive": {"enabled": False}}
    content = b"%PDF-1.4\nmanual"
    with pytest.raises(ValueError, match="disabled"):
        asyncio.run(ns["archive_pdf_bytes"](hass, bill, category, content))
    relative, sha = asyncio.run(ns["archive_pdf_bytes"](
        hass, bill, category, content, manual=True,
    ))
    assert sha == hashlib.sha256(content).hexdigest()
    assert (tmp_path / relative).read_bytes() == content
    with pytest.raises(ValueError, match="belong"):
        asyncio.run(ns["delete_archived_pdf"](hass, relative, "another-bill"))
    assert (tmp_path / relative).exists()
    asyncio.run(ns["delete_archived_pdf"](hass, relative, "bill001"))
    assert not (tmp_path / relative).exists()


def test_document_delete_cannot_target_non_billy_files(tmp_path):
    hass = HassStub(tmp_path)
    other = tmp_path / "private.pdf"
    other.write_bytes(b"%PDF-1.4\nprivate")
    with pytest.raises(ValueError, match="belong"):
        asyncio.run(ns["delete_archived_pdf"](hass, "private.pdf", "bill001"))
    assert other.exists()
