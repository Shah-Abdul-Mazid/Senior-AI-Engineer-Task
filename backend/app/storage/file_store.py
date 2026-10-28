"""File storage — saves uploads to disk, validates type & size."""
import os
import uuid
import aiofiles
from pathlib import Path
from fastapi import UploadFile, HTTPException, status
from app.core.config import settings


def get_upload_dir() -> Path:
    """Returns the unified absolute upload directory."""
    custom_dir = os.environ.get("UPLOAD_DIR")
    if custom_dir:
        p = Path(custom_dir)
        if p.is_absolute():
            return p

    # Find project root (Senior AI Engineer Task)
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        candidate = parent / "uploads"
        if candidate.exists() and candidate.is_dir() and parent.name == "Senior AI Engineer Task":
            return candidate

    # Fallback to backend/uploads
    fallback = Path(__file__).resolve().parents[2] / "uploads"
    return fallback


UPLOAD_DIR = get_upload_dir()
MAX_BYTES = settings.MAX_FILE_SIZE_MB * 1024 * 1024


def ensure_upload_dir() -> None:
    """Create upload directory if it doesn't exist."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def get_file_extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def validate_file(filename: str, size: int) -> str:
    """Validate file extension and size. Returns cleaned extension."""
    ext = get_file_extension(filename)
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File type '.{ext}' is not supported. Allowed: {settings.ALLOWED_EXTENSIONS}",
        )
    if size > MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Max size: {settings.MAX_FILE_SIZE_MB} MB",
        )
    return ext


async def save_upload(file: UploadFile) -> tuple[str, str, int]:
    """
    Persist an uploaded file to disk.

    Returns:
        (stored_filename, absolute_file_path, file_size_bytes)
    """
    ensure_upload_dir()

    content = await file.read()
    file_size = len(content)
    ext = validate_file(file.filename or "unknown", file_size)

    stored_name = f"{uuid.uuid4().hex}.{ext}"
    file_path = UPLOAD_DIR / stored_name

    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    return stored_name, str(file_path.resolve()), file_size


def delete_file(file_path: str) -> None:
    """Remove a stored file from disk (used on soft-delete)."""
    try:
        path = Path(file_path)
        if path.exists():
            path.unlink()
    except OSError:
        pass
