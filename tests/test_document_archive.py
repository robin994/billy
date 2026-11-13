"""Security and media path tests for the optional PDF archive (no HA required)."""
import asyncio
import ast
import hashlib
import os
from pathlib import Path
import re
import unicodedata
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
    "category_folder", "_is_archive_layout", "archive_maintenance_plan", "apply_archive_maintenance",
    "rollback_archive_maintenance",
}
FUNCTIONS = [
    item for item in TREE.body
    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name in NAMES
]
ns = {
    "re": re, "Path": Path, "os": os, "urlsplit": urlsplit, "uuid4": uuid4,
    "hashlib": hashlib, "MAX_PDF_BYTES": 8 * 1024 * 1024,
    "unicodedata": unicodedata,
    "_PART": re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}$"),
    "_OWNED_PDF": re.compile(r"^([a-zA-Z0-9][a-zA-Z0-9._-]{0,79})-([a-f0-9]{12})\.pdf$"),
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


def test_archive_reconciliation_moves_and_trashes_only_owned_pdfs(tmp_path):
    hass = HassStub(tmp_path)
    category = {"id": "electricity", "name": "Elettricità", "document_archive": {}}
    bill = {"id": "bill001", "category_id": "electricity", "paid_year": 2026,
            "paid_month": 11}
    old = "billy/documents/2026/10/Elettricit/bill001-abcdef123456.pdf"
    orphan = "billy/documents/2026/10/Elettricit/gone-abcdef123456.pdf"
    foreign = "billy/documents/2026/10/Elettricit/manual.pdf"
    for relative in (old, orphan, foreign):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"%PDF-1.4\ntest")
    bill["document_path"] = old
    plan = ns["archive_maintenance_plan"](hass, [bill], [category])
    assert plan["moves"] == [{"bill_id": "bill001", "from": old,
                              "to": "billy/documents/2026/11/Elettricita/bill001-abcdef123456.pdf"}]
    assert plan["orphans"] == [{"path": orphan}]
    completed = ns["apply_archive_maintenance"](hass, plan)
    assert len(completed) == 2
    assert (tmp_path / plan["moves"][0]["to"]).is_file()
    assert (tmp_path / foreign).is_file()
    assert not (tmp_path / orphan).exists()
    assert any("/trash/" in new for _, new in completed)
    ns["rollback_archive_maintenance"](hass, completed)
    assert (tmp_path / old).is_file() and (tmp_path / orphan).is_file()


def test_archive_reconciliation_reports_missing_and_ignores_symlinks(tmp_path):
    hass = HassStub(tmp_path)
    category = {"id": "power", "name": "Electricity", "document_archive": {}}
    missing = "billy/documents/2026/10/Electricity/bill001-abcdef123456.pdf"
    bill = {"id": "bill001", "category_id": "power", "paid_year": 2026,
            "paid_month": 10, "document_path": missing}
    plan = ns["archive_maintenance_plan"](hass, [bill], [category])
    assert plan["missing"] == [{"bill_id": "bill001", "path": missing}]
    assert not plan["moves"] and not plan["orphans"]


def test_archive_reconciliation_rejects_references_outside_configured_roots(tmp_path):
    hass = HassStub(tmp_path)
    category = {"id": "power", "name": "Electricity", "document_archive": {}}
    foreign = "other-app/2026/10/Electricity/bill001-abcdef123456.pdf"
    target = tmp_path / foreign
    target.parent.mkdir(parents=True)
    target.write_bytes(b"%PDF-1.4\nforeign")
    bill = {"id": "bill001", "category_id": "power", "paid_year": 2026,
            "paid_month": 11, "document_path": foreign}
    plan = ns["archive_maintenance_plan"](hass, [bill], [category])
    assert plan["conflicts"] == [{"path": foreign, "reason": "outside_archive_layout"}]
    assert not plan["moves"] and not plan["orphans"]
    assert target.is_file()


def test_archive_reconciliation_rejects_in_media_symlinked_bill_folder(tmp_path):
    hass = HassStub(tmp_path)
    category = {"id": "power", "name": "Electricity", "document_archive": {}}
    real = tmp_path / "other-app"
    real.mkdir()
    (real / "bill001-abcdef123456.pdf").write_bytes(b"%PDF-1.4\nforeign")
    parent = tmp_path / "billy/documents/2026/10"
    parent.mkdir(parents=True)
    (parent / "Electricity").symlink_to(real, target_is_directory=True)
    bill = {"id": "bill001", "category_id": "power", "paid_year": 2026,
            "paid_month": 11,
            "document_path": "billy/documents/2026/10/Electricity/bill001-abcdef123456.pdf"}
    plan = ns["archive_maintenance_plan"](hass, [bill], [category])
    assert plan["conflicts"][0]["reason"] == "outside_archive_layout"
    assert not plan["moves"] and not plan["orphans"]
    assert (real / "bill001-abcdef123456.pdf").is_file()
