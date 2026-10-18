"""End-to-end manager tests of manual bill PDF uploads, replacements and removal."""
import ast
import asyncio
from pathlib import Path
from time import monotonic

import pytest

from test_document_archive import HassStub, ns as archive_ns

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "bill_tracker"
MANAGER = ROOT / "manager.py"
TREE = ast.parse(MANAGER.read_text(encoding="utf-8"))
CLASS = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "BillTrackerManager")
METHODS = [
    method for method in CLASS.body
    if isinstance(method, ast.AsyncFunctionDef) and method.name in {
        "async_receive_document_chunk", "async_upload_document", "async_delete_document",
    }
]
NAMESPACE = {
    "Any": object,
    "MAX_PDF_BYTES": 8 * 1024 * 1024,
    "monotonic": monotonic,
    "archive_pdf_bytes": archive_ns["archive_pdf_bytes"],
    "delete_archived_pdf": archive_ns["delete_archived_pdf"],
    "validate_owned_pdf_path": archive_ns["validate_owned_pdf_path"],
}
EXTRACTED = ast.Module(body=METHODS, type_ignores=[])
ast.fix_missing_locations(EXTRACTED)
exec(compile(EXTRACTED, str(MANAGER), "exec"), NAMESPACE)


class DocumentHarness:
    async_receive_document_chunk = NAMESPACE["async_receive_document_chunk"]
    async_upload_document = NAMESPACE["async_upload_document"]
    async_delete_document = NAMESPACE["async_delete_document"]

    def __init__(self, root):
        self.hass = HassStub(root)
        self.expenses = [{
            "id": "bill001", "category_id": "power", "paid_year": 2026,
            "paid_month": 10, "document_url": "https://example.org/bill.pdf",
            "document_path": None, "document_sha256": None, "document_error": None,
        }]
        self._document_uploads = {}
        self._category = {
            "name": "Electricity", "document_archive": {"enabled": False},
        }
        self.saved = 0
        self.fail_next_save = False

    def category(self, category_id):
        return self._category if category_id == "power" else None

    def _public_expense(self, bill):
        return dict(bill)

    async def _save_and_notify(self):
        if self.fail_next_save:
            self.fail_next_save = False
            raise RuntimeError("Simulated persistence failure")
        self.saved += 1


def run(coro):
    return asyncio.run(coro)


def test_pdf_manual_upload_replace_and_delete_are_kept_in_media(tmp_path):
    manager = DocumentHarness(tmp_path)
    first = run(manager.async_upload_document("bill001", b"%PDF-1.4\nfirst version"))
    old_path = tmp_path / first["document_path"]
    assert old_path.read_bytes() == b"%PDF-1.4\nfirst version"
    assert first["document_url"] == ""

    newer = run(manager.async_upload_document("bill001", b"%PDF-1.4\nsecond version"))
    second_path = tmp_path / newer["document_path"]
    assert second_path.read_bytes() == b"%PDF-1.4\nsecond version"
    assert not old_path.exists()
    assert second_path != old_path

    deleted = run(manager.async_delete_document("bill001"))
    assert deleted["document_path"] is None
    assert deleted["document_url"] == ""
    assert not second_path.exists()
    assert manager.saved == 3
    with pytest.raises(ValueError, match="no document"):
        run(manager.async_delete_document("bill001"))


def test_invalid_pdf_or_wrong_bill_cannot_write_or_delete(tmp_path):
    manager = DocumentHarness(tmp_path)
    for content in (b"not PDF", b"%PDF-" + b"x" * (8 * 1024 * 1024)):
        with pytest.raises(ValueError, match="Only PDF"):
            run(manager.async_upload_document("bill001", content))
    with pytest.raises(ValueError, match="Bill not found"):
        run(manager.async_upload_document("missing", b"%PDF-1.4\nvalid"))
    assert manager.saved == 0
    assert list(tmp_path.rglob("*.pdf")) == []

    foreign = tmp_path / "foreign.pdf"
    foreign.write_bytes(b"%PDF-1.4\nforeign")
    manager.expenses[0]["document_path"] = "foreign.pdf"
    with pytest.raises(ValueError, match="belong"):
        run(manager.async_delete_document("bill001"))
    assert foreign.exists()
    assert manager.expenses[0]["document_path"] == "foreign.pdf"


def test_failed_save_rolls_back_pdf_reference_and_removes_new_upload(tmp_path):
    manager = DocumentHarness(tmp_path)
    first = run(manager.async_upload_document("bill001", b"%PDF-1.4\nfirst"))
    manager.fail_next_save = True
    with pytest.raises(RuntimeError, match="persistence"):
        run(manager.async_upload_document("bill001", b"%PDF-1.4\nnext"))
    assert manager.expenses[0]["document_path"] == first["document_path"]
    assert (tmp_path / first["document_path"]).exists()
    assert len(list(tmp_path.rglob("*.pdf"))) == 1

    manager.fail_next_save = True
    with pytest.raises(RuntimeError, match="persistence"):
        run(manager.async_delete_document("bill001"))
    assert manager.expenses[0]["document_path"] == first["document_path"]
    assert (tmp_path / first["document_path"]).exists()


def test_chunked_upload_assembles_pdf_and_rejects_out_of_order_chunks(tmp_path):
    manager = DocumentHarness(tmp_path)
    pdf = b"%PDF-1.4\n" + b"x" * 200000
    first = run(manager.async_receive_document_chunk(
        "user", "bill001", "upload-1", 0, 2, len(pdf), pdf[:100000],
    ))
    assert first == {"complete": False, "received": 100000}
    done = run(manager.async_receive_document_chunk(
        "user", "bill001", "upload-1", 1, 2, len(pdf), pdf[100000:],
    ))
    assert done["complete"] is True
    assert (tmp_path / done["bill"]["document_path"]).read_bytes() == pdf
    assert manager._document_uploads == {}

    with pytest.raises(ValueError, match="Out-of-order"):
        run(manager.async_receive_document_chunk(
            "user", "bill001", "wrong-order", 1, 2, len(pdf), pdf[:100],
        ))
    assert manager._document_uploads == {}
