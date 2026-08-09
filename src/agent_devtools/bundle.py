"""Portable local diagnostic bundle export."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile
from zipfile import ZIP_DEFLATED, ZipFile


class BundleExportError(RuntimeError):
    """Raised when a trace cannot be exported safely."""


_BUNDLE_NAME = re.compile(
    r"^agent-devtools-(?P<date>\d{8})-test(?P<sequence>\d+)\.zip$"
)
_SCREENSHOT_SUFFIXES = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"}
_TEXT_SUFFIXES = {".csv", ".html", ".htm", ".json", ".log", ".md", ".txt"}
_SENSITIVE_FIELD_NAMES = {
    "accesstoken",
    "apikey",
    "authtoken",
    "authorization",
    "clientsecret",
    "cookie",
    "credential",
    "password",
    "privatekey",
    "refreshtoken",
    "secret",
    "token",
}
_REDACTED = "[REDACTED]"
_PATH_RE = re.compile(
    r"(?:[A-Za-z]:[\\/]|/home/|/mnt/|/tmp/|/Users/|/var/tmp/)[^<>\s\"']+"
)
_TEXT_REPLACEMENTS = (
    (
        re.compile(
            r"(?i)\b(?:sk-[A-Za-z0-9_-]{8,}|AIza[A-Za-z0-9_-]{20,}|"
            r"gh[pousr]_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{10,})\b"
        ),
        _REDACTED,
    ),
    (
        re.compile(r"(?i)\bBearer\s+[^\s<>\"']+"),
        "Bearer " + _REDACTED,
    ),
    (
        re.compile(
            r"(?i)([?&](?:access_token|api_key|auth|code|key|password|"
            r"secret|token)=)(?!\[REDACTED\])[^&#\s\"']+"
        ),
        r"\1" + _REDACTED,
    ),
    (
        re.compile(
            r"(?i)\b(password|passwd|access_token|api_key|authorization|"
            r"cookie|secret|token)\s*([:=])\s*(?!\[REDACTED\])"
            r"([^\s,;\]}\"'<>]+)"
        ),
        r"\1\2" + _REDACTED,
    ),
    (_PATH_RE, "[PATH]"),
)
_IMAGE_TAG_RE = re.compile(
    r"<img\b[^>]*\bsrc\s*=\s*([\"'])(?P<src>.*?)\1[^>]*>",
    flags=re.IGNORECASE | re.DOTALL,
)
_BODY_TAG_RE = re.compile(r"<body\b[^>]*>", flags=re.IGNORECASE)
_REDACTION_NOTICE = (
    '<div style="padding:12px;border:1px solid #d97706;'
    'background:#fffbeb;color:#92400e;font:14px sans-serif;">'
    "Screenshots were omitted from this redacted bundle."
    "</div>"
)


def next_bundle_path(
    output_dir: str | Path,
    *,
    created_at: datetime | None = None,
) -> Path:
    """Return the next dated diagnostic bundle path without creating it.

    Names use the UTC date and a one-based sequence for that date, for example
    ``agent-devtools-20260809-test001.zip``.
    """

    timestamp = _normalise_timestamp(created_at)
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    if not directory.is_dir():
        raise BundleExportError(f"bundle output is not a directory: {directory}")

    date_text = timestamp.strftime("%Y%m%d")
    highest = 0
    for candidate in directory.iterdir():
        if not candidate.is_file():
            continue
        match = _BUNDLE_NAME.fullmatch(candidate.name)
        if match is not None and match.group("date") == date_text:
            highest = max(highest, int(match.group("sequence")))

    return directory / f"agent-devtools-{date_text}-test{highest + 1:03d}.zip"


def export_diagnostic_bundle(
    source_dir: str | Path,
    output_dir: str | Path | None = None,
    *,
    created_at: datetime | None = None,
    redact: bool = False,
) -> Path:
    """Export one local trace directory as a portable diagnostic zip.

    The archive contains every regular file below ``source_dir`` and a small
    manifest. Paths are relative POSIX paths; absolute paths and symlinks are
    rejected. By default, bundles are written to a sibling ``bundles``
    directory so the archive cannot include itself. With ``redact=True``,
    common secret-shaped text is replaced and image files are omitted.
    """

    if not isinstance(redact, bool):
        raise TypeError("redact must be a boolean")

    source_input = Path(source_dir)
    if source_input.is_symlink():
        raise BundleExportError("source directory must not be a symlink")
    source = source_input.resolve()
    if not source.is_dir():
        raise BundleExportError(f"trace directory does not exist: {source}")

    output = (
        Path(output_dir)
        if output_dir is not None
        else source.parent / "bundles"
    ).resolve()
    if output == source or output.is_relative_to(source):
        raise BundleExportError(
            "bundle output must be outside the trace directory"
        )
    output.mkdir(parents=True, exist_ok=True)
    if not output.is_dir():
        raise BundleExportError(f"bundle output is not a directory: {output}")

    timestamp = _normalise_timestamp(created_at)
    entries, omitted_files, redaction_count = _prepare_files(
        source,
        redact=redact,
    )
    if not entries and not omitted_files:
        raise BundleExportError("trace directory contains no regular files")

    target = _reserve_target(output, timestamp)
    temporary_path: Path | None = None
    try:
        manifest = _manifest_for(
            target.name,
            timestamp,
            source,
            entries,
            redact=redact,
            omitted_files=omitted_files,
            redaction_count=redaction_count,
        )
        with NamedTemporaryFile(
            mode="wb",
            dir=output,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            with ZipFile(temporary_file, "w", compression=ZIP_DEFLATED) as archive:
                for path, relative, content in entries:
                    if content is None:
                        if path.is_symlink() or not path.is_file():
                            raise BundleExportError(
                                f"trace file changed during export: {relative}"
                            )
                        archive.write(path, arcname=relative)
                    else:
                        archive.writestr(relative, content)
                archive.writestr(
                    "manifest.json",
                    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                )
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        os.replace(temporary_path, target)
        temporary_path = None
        return target
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _normalise_timestamp(created_at: datetime | None) -> datetime:
    timestamp = datetime.now(UTC) if created_at is None else created_at
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("created_at must be timezone-aware")
    return timestamp.astimezone(UTC)


def _prepare_files(
    source: Path,
    *,
    redact: bool,
) -> tuple[list[tuple[Path, str, bytes | None]], list[str], int]:
    files = _collect_files(source)
    omitted_files = [
        relative
        for _, relative in files
        if redact and _is_screenshot_file(relative)
    ]
    omitted_set = set(omitted_files)
    entries: list[tuple[Path, str, bytes | None]] = []
    redaction_count = 0

    for path, relative in files:
        if relative in omitted_set:
            continue
        if not redact:
            entries.append((path, relative, None))
            continue
        content, replacements = _redact_file(
            path,
            relative,
            omitted_set,
        )
        entries.append((path, relative, content))
        redaction_count += replacements

    return entries, omitted_files, redaction_count


def _is_screenshot_file(relative: str) -> bool:
    path = PurePosixPath(relative)
    return path.suffix.casefold() in _SCREENSHOT_SUFFIXES or any(
        part.casefold() in {"screenshot", "screenshots"}
        for part in path.parts
    )


def _redact_file(
    path: Path,
    relative: str,
    omitted_files: set[str],
) -> tuple[bytes, int]:
    raw = path.read_bytes()
    if path.suffix.casefold() not in _TEXT_SUFFIXES:
        return raw, 0

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw, 0

    replacements = 0
    if path.suffix.casefold() == ".json":
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            text, replacements = _redact_text(text)
        else:
            value, replacements = _redact_json(value)
            text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    else:
        text, replacements = _redact_text(text)

    if path.suffix.casefold() in {".html", ".htm"} and omitted_files:
        text = _replace_omitted_images(text, omitted_files)
        text = _add_redaction_notice(text)
    return text.encode("utf-8"), replacements


def _redact_json(value: object) -> tuple[object, int]:
    if isinstance(value, dict):
        redacted: dict[object, object] = {}
        replacements = 0
        for key, item in value.items():
            if isinstance(key, str) and _is_sensitive_field(key):
                redacted[key] = _REDACTED
                replacements += 1
                continue
            redacted_item, item_replacements = _redact_json(item)
            redacted[key] = redacted_item
            replacements += item_replacements
        return redacted, replacements
    if isinstance(value, list):
        items: list[object] = []
        replacements = 0
        for item in value:
            redacted_item, item_replacements = _redact_json(item)
            items.append(redacted_item)
            replacements += item_replacements
        return items, replacements
    if isinstance(value, str):
        return _redact_text(value)
    return value, 0


def _is_sensitive_field(value: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", value.casefold())
    return normalized in _SENSITIVE_FIELD_NAMES


def _redact_text(value: str) -> tuple[str, int]:
    replacements = 0
    for pattern, replacement in _TEXT_REPLACEMENTS:
        value, count = pattern.subn(replacement, value)
        replacements += count
    return value, replacements


def _normalise_reference(value: str) -> str:
    reference = value.split("?", 1)[0].split("#", 1)[0]
    reference = reference.replace("\\", "/")
    while reference.startswith("./"):
        reference = reference[2:]
    return reference


def _replace_omitted_images(value: str, omitted_files: set[str]) -> str:
    def replace(match: re.Match[str]) -> str:
        source = _normalise_reference(match.group("src"))
        if source not in omitted_files:
            return match.group(0)
        return (
            '<div style="padding:12px;border:1px dashed #9ca3af;'
            'color:#6b7280;font:14px sans-serif;">'
            "Screenshot omitted from redacted bundle."
            "</div>"
        )

    return _IMAGE_TAG_RE.sub(replace, value)


def _add_redaction_notice(value: str) -> str:
    if _BODY_TAG_RE.search(value):
        return _BODY_TAG_RE.sub(
            lambda match: match.group(0) + _REDACTION_NOTICE,
            value,
            count=1,
        )
    return _REDACTION_NOTICE + value


def _collect_files(source: Path) -> list[tuple[Path, str]]:
    files: list[tuple[Path, str]] = []
    for path in sorted(source.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise BundleExportError(
                "trace directory contains an unsupported symlink: "
                f"{path.relative_to(source).as_posix()}"
            )
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        archive_name = relative.as_posix()
        _validate_archive_path(archive_name)
        if archive_name == "manifest.json":
            raise BundleExportError(
                "trace directory cannot contain a root manifest.json"
            )
        files.append((path, archive_name))
    return files


def _validate_archive_path(value: str) -> None:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in value
    ):
        raise BundleExportError(f"unsafe trace path: {value!r}")


def _reserve_target(output: Path, timestamp: datetime) -> Path:
    while True:
        target = next_bundle_path(output, created_at=timestamp)
        try:
            descriptor = os.open(
                target,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            )
        except FileExistsError:
            continue
        os.close(descriptor)
        return target


def _manifest_for(
    bundle_name: str,
    timestamp: datetime,
    source: Path,
    entries: list[tuple[Path, str, bytes | None]],
    *,
    redact: bool,
    omitted_files: list[str],
    redaction_count: int,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "bundle_name": bundle_name,
        "created_at": timestamp.isoformat().replace("+00:00", "Z"),
        "source_kind": (
            "evaluation" if (source / "evaluation.json").is_file() else "session"
        ),
        "file_count": len(entries),
        "files": [
            {
                "path": relative,
                "size": (
                    len(content)
                    if content is not None
                    else path.stat().st_size
                ),
            }
            for path, relative, content in entries
        ],
        "redaction": {
            "enabled": redact,
            "replacement_count": redaction_count,
            "omitted_files": omitted_files,
        },
        "privacy_note": (
            "This redacted bundle replaces common secret-shaped text and "
            "omits image files. Review the remaining task text, arguments, "
            "and URLs before sharing."
            if redact
            else "This bundle copies local trace evidence. Review task text, "
            "arguments, URLs, and screenshots before sharing."
        ),
    }


__all__ = [
    "BundleExportError",
    "export_diagnostic_bundle",
    "next_bundle_path",
]
