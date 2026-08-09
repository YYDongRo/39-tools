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
) -> Path:
    """Export one local trace directory as a portable diagnostic zip.

    The archive contains every regular file below ``source_dir`` and a small
    manifest. Paths are relative POSIX paths; absolute paths and symlinks are
    rejected. By default, bundles are written to a sibling ``bundles``
    directory so the archive cannot include itself.
    """

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
    files = _collect_files(source)
    if not files:
        raise BundleExportError("trace directory contains no regular files")

    target = _reserve_target(output, timestamp)
    temporary_path: Path | None = None
    try:
        manifest = _manifest_for(target.name, timestamp, source, files)
        with NamedTemporaryFile(
            mode="wb",
            dir=output,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            with ZipFile(temporary_file, "w", compression=ZIP_DEFLATED) as archive:
                for path, relative in files:
                    if path.is_symlink() or not path.is_file():
                        raise BundleExportError(
                            f"trace file changed during export: {relative}"
                        )
                    archive.write(path, arcname=relative)
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
    files: list[tuple[Path, str]],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "bundle_name": bundle_name,
        "created_at": timestamp.isoformat().replace("+00:00", "Z"),
        "source_kind": (
            "evaluation" if (source / "evaluation.json").is_file() else "session"
        ),
        "file_count": len(files),
        "files": [
            {
                "path": relative,
                "size": path.stat().st_size,
            }
            for path, relative in files
        ],
        "privacy_note": (
            "This bundle copies local trace evidence. Review task text, "
            "arguments, URLs, and screenshots before sharing."
        ),
    }


__all__ = [
    "BundleExportError",
    "export_diagnostic_bundle",
    "next_bundle_path",
]
