"""Optional PDF archive for Billy bills.

Only an explicitly configured source hostname may be fetched. Files are kept
under Home Assistant's media directory, including mounted network shares.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
from urllib.parse import urlsplit
from uuid import uuid4

from aiohttp import ClientTimeout
from homeassistant.helpers.aiohttp_client import async_get_clientsession

MAX_PDF_BYTES = 8 * 1024 * 1024
_PART = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}$")


def normalize_archive_config(value: object) -> dict:
    """Validate settings used for both local and HA-mounted network media."""
    data = value if isinstance(value, dict) else {}
    subpath = str(data.get("subpath") or "billy/documents").strip().strip("/")
    parts = subpath.split("/")
    if not parts or any(
        part in ("", ".", "..") or not _PART.fullmatch(part) for part in parts
    ):
        raise ValueError("Archive path must be relative to media and contain safe folder names")
    host = str(data.get("source_host") or "").strip().lower()
    if host:
        parsed = urlsplit(f"//{host}")
        if (
            not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path
            or parsed.query
            or parsed.fragment
            or any(ch.isspace() for ch in host)
        ):
            raise ValueError("Invalid archive source hostname")
    return {
        "enabled": bool(data.get("enabled", False)),
        "subpath": subpath,
        "source_host": host,
    }


def allowed_document_url(url: str, source_host: str) -> str:
    """Only fetch from a hostname explicitly approved in archive settings."""
    parsed = urlsplit(str(url).strip())
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
        or not source_host
        or parsed.netloc.lower() != source_host.lower()
    ):
        raise ValueError("Document URL host is not allowed for automatic download")
    return parsed.geturl()


def media_root(hass) -> Path:
    """Use HA's local media source rather than public /config/www."""
    configured = getattr(hass.config, "media_dirs", {}) or {}
    return Path(configured.get("local") or hass.config.path("media")).resolve()


def safe_archive_path(hass, relative: str) -> Path:
    root = media_root(hass)
    parts = str(relative or "").split("/")
    if any(part in ("", ".", "..") or not _PART.fullmatch(part) for part in parts):
        raise ValueError("Invalid archived document path")
    candidate = root.joinpath(*parts).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("Archived document is outside the media directory")
    return candidate


def _store_pdf(hass, relative: str, content: bytes) -> None:
    target = safe_archive_path(hass, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as output:
            os.chmod(temporary, 0o600)
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


async def archive_pdf(hass, bill: dict, category: dict) -> tuple[str, str]:
    """Download a bounded PDF and store it in year/month/type order."""
    config = normalize_archive_config(category.get("document_archive"))
    if not config["enabled"]:
        raise ValueError("Document archiving is disabled for this bill type")
    url = allowed_document_url(bill.get("document_url", ""), config["source_host"])
    session = async_get_clientsession(hass)
    async with session.get(
        url, allow_redirects=False, timeout=ClientTimeout(total=35)
    ) as response:
        if response.status != 200:
            raise ValueError(f"Document download failed (HTTP {response.status})")
        if int(response.headers.get("Content-Length", 0) or 0) > MAX_PDF_BYTES:
            raise ValueError("Document exceeds the 8 MiB archive limit")
        chunks = []
        size = 0
        async for chunk in response.content.iter_chunked(64 * 1024):
            size += len(chunk)
            if size > MAX_PDF_BYTES:
                raise ValueError("Document exceeds the 8 MiB archive limit")
            chunks.append(chunk)
    return await archive_pdf_bytes(hass, bill, category, b"".join(chunks))


async def archive_pdf_bytes(
    hass, bill: dict, category: dict, content: bytes, *, manual: bool = False
) -> tuple[str, str]:
    """Archive a fetched or explicitly uploaded PDF without another download."""
    config = normalize_archive_config(category.get("document_archive"))
    if not config["enabled"] and not manual:
        raise ValueError("Document archiving is disabled for this bill type")
    if len(content) > MAX_PDF_BYTES:
        raise ValueError("Document exceeds the 8 MiB archive limit")
    if not content.startswith(b"%PDF-"):
        raise ValueError("Document is not a PDF")
    checksum = hashlib.sha256(content).hexdigest()
    year = int(bill["paid_year"])
    month = int(bill["paid_month"])
    # A stable ID prevents two bills with the same vendor/month overwriting.
    category_slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(category["name"])).strip("-")[:60] or "other"
    filename = f"{bill['id']}-{checksum[:12]}.pdf"
    relative = f"{config['subpath']}/{year:04d}/{month:02d}/{category_slug}/{filename}"
    await hass.async_add_executor_job(_store_pdf, hass, relative, content)
    return relative, checksum


def validate_owned_pdf_path(hass, relative: str, expense_id: str) -> Path:
    """A backup must not turn a bill's file reference into arbitrary media deletion."""
    target = safe_archive_path(hass, relative)
    name = target.name
    if (
        not name.startswith(f"{expense_id}-") or not name.endswith(".pdf")
        or not re.fullmatch(r"[a-f0-9]{12}", name[len(expense_id) + 1:-4])
    ):
        raise ValueError("Document path does not belong to this bill")
    return target


def _delete_archived_pdf(hass, relative: str, expense_id: str) -> None:
    """Only unlink a Billy-generated PDF belonging to this exact bill."""
    validate_owned_pdf_path(hass, relative, expense_id).unlink(missing_ok=True)


async def delete_archived_pdf(hass, relative: str, expense_id: str) -> None:
    await hass.async_add_executor_job(_delete_archived_pdf, hass, relative, expense_id)


async def read_pdf(hass, relative: str) -> bytes:
    """Read only a previously recorded archive path, within a bounded size."""
    path = safe_archive_path(hass, relative)

    def _read() -> bytes:
        if not path.is_file() or path.stat().st_size > MAX_PDF_BYTES:
            raise ValueError("Archived document missing or too large")
        data = path.read_bytes()
        if not data.startswith(b"%PDF-"):
            raise ValueError("Archived document is not a PDF")
        return data

    return await hass.async_add_executor_job(_read)
