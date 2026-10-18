"""Document Tool: extract clean text from a supplier PDF.

Primary extractor is PyMuPDF; pypdf is used as a fallback. The tool raises
``DocumentError`` for files that are not PDFs, are encrypted, or contain no
extractable text (e.g. scanned images), so the UI can show a clear validation
message before any LLM call is made.
"""
from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass

MIN_TEXT_CHARS = 200          # below this the PDF is treated as unreadable / scanned
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_PROMPT_CHARS = 60_000     # protects the LLM context window


class DocumentError(ValueError):
    """Raised when a PDF cannot be used for evaluation."""


@dataclass(frozen=True)
class ExtractedDocument:
    file_name: str
    text: str
    pages: int
    sha256: str
    truncated: bool
    extractor: str

    @property
    def chars(self) -> int:
        return len(self.text)


def _clean(text: str) -> str:
    text = text.replace(" ", " ").replace("•", "-")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_pymupdf(data: bytes) -> tuple[str, int]:
    import pymupdf as fitz

    with fitz.open(stream=data, filetype="pdf") as doc:
        if doc.needs_pass:
            raise DocumentError("PDF is password protected.")
        parts = [f"[Page {i + 1}]\n{page.get_text('text')}" for i, page in enumerate(doc)]
        return "\n".join(parts), doc.page_count


def _extract_pypdf(data: bytes) -> tuple[str, int]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        raise DocumentError("PDF is password protected.")
    parts = [f"[Page {i + 1}]\n{p.extract_text() or ''}" for i, p in enumerate(reader.pages)]
    return "\n".join(parts), len(reader.pages)


def extract_text(data: bytes, file_name: str = "document.pdf") -> ExtractedDocument:
    if not data:
        raise DocumentError(f"{file_name}: file is empty.")
    if len(data) > MAX_FILE_BYTES:
        raise DocumentError(f"{file_name}: file exceeds {MAX_FILE_BYTES // (1024 * 1024)} MB.")
    if not data.lstrip()[:5].startswith(b"%PDF"):
        raise DocumentError(f"{file_name}: not a valid PDF file.")

    errors: list[str] = []
    for name, fn in (("pymupdf", _extract_pymupdf), ("pypdf", _extract_pypdf)):
        try:
            raw, pages = fn(data)
        except DocumentError as exc:
            raise DocumentError(f"{file_name}: {exc}") from exc
        except Exception as exc:  # corrupted file or library error -> try fallback
            errors.append(f"{name}: {exc}")
            continue
        text = _clean(raw)
        body = re.sub(r"\[Page \d+\]", "", text).strip()
        if len(body) < MIN_TEXT_CHARS:
            raise DocumentError(
                f"{file_name}: only {len(body)} characters of text found - the PDF may be scanned or empty "
                "(OCR is not supported).")
        truncated = len(text) > MAX_PROMPT_CHARS
        return ExtractedDocument(file_name=file_name, text=text[:MAX_PROMPT_CHARS], pages=pages,
                                 sha256=hashlib.sha256(data).hexdigest(), truncated=truncated,
                                 extractor=name)
    raise DocumentError(f"{file_name}: could not read PDF ({'; '.join(errors)}).")
