from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZipFile

import pytest

from agent_devtools.bundle import (
    BundleExportError,
    export_diagnostic_bundle,
    next_bundle_path,
)


FIXED_TIME = datetime(2026, 8, 9, 12, 34, 56, tzinfo=UTC)


def _write_trace(path: Path, *, evaluation: bool = False) -> None:
    path.mkdir(parents=True)
    (path / "report.html").write_text("<h1>Agent DevTools</h1>", encoding="utf-8")
    (path / "session.json").write_text(
        '{"report_path": "report.html"}\n',
        encoding="utf-8",
    )
    (path / "screenshots").mkdir()
    (path / "screenshots" / "after.svg").write_text(
        "<svg xmlns='http://www.w3.org/2000/svg'/>",
        encoding="utf-8",
    )
    if evaluation:
        (path / "evaluation.json").write_text(
            '{"schema_version": 1}\n',
            encoding="utf-8",
        )


def test_next_bundle_path_uses_utc_date_and_daily_sequence(tmp_path: Path) -> None:
    output = tmp_path / "bundles"
    output.mkdir()
    (output / "agent-devtools-20260809-test001.zip").touch()
    (output / "agent-devtools-20260809-test002.zip").touch()
    (output / "agent-devtools-20260808-test099.zip").touch()
    (output / "unrelated.zip").touch()

    assert next_bundle_path(output, created_at=FIXED_TIME).name == (
        "agent-devtools-20260809-test003.zip"
    )
    assert next_bundle_path(
        output,
        created_at=datetime(2026, 8, 10, tzinfo=UTC),
    ).name == "agent-devtools-20260810-test001.zip"


def test_next_bundle_path_rejects_naive_timestamp(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        next_bundle_path(tmp_path, created_at=datetime(2026, 8, 9))


def test_export_bundle_contains_relative_files_and_manifest(tmp_path: Path) -> None:
    source = tmp_path / "trace" / "run-001"
    output = tmp_path / "bundles"
    _write_trace(source)

    bundle = export_diagnostic_bundle(
        source,
        output,
        created_at=FIXED_TIME,
    )

    assert bundle.name == "agent-devtools-20260809-test001.zip"
    with ZipFile(bundle) as archive:
        names = archive.namelist()
        assert names == [
            "report.html",
            "screenshots/after.svg",
            "session.json",
            "manifest.json",
        ]
        manifest = json.loads(archive.read("manifest.json"))

    assert manifest["schema_version"] == 1
    assert manifest["bundle_name"] == bundle.name
    assert manifest["source_kind"] == "session"
    assert manifest["file_count"] == 3
    assert all(
        not Path(item["path"]).is_absolute() and ".." not in Path(item["path"]).parts
        for item in manifest["files"]
    )
    assert str(source) not in json.dumps(manifest)
    assert "Review task text" in manifest["privacy_note"]


def test_export_bundle_increments_without_overwriting(tmp_path: Path) -> None:
    source = tmp_path / "trace"
    output = tmp_path / "bundles"
    _write_trace(source)

    first = export_diagnostic_bundle(source, output, created_at=FIXED_TIME)
    second = export_diagnostic_bundle(source, output, created_at=FIXED_TIME)

    assert first.name.endswith("test001.zip")
    assert second.name.endswith("test002.zip")
    assert first.read_bytes() != b""
    assert second.read_bytes() != b""


def test_evaluation_bundle_manifest_identifies_evaluation(tmp_path: Path) -> None:
    source = tmp_path / "evaluation"
    _write_trace(source, evaluation=True)

    bundle = export_diagnostic_bundle(source, created_at=FIXED_TIME)

    with ZipFile(bundle) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["source_kind"] == "evaluation"


def test_export_bundle_rejects_output_inside_source(tmp_path: Path) -> None:
    source = tmp_path / "trace"
    _write_trace(source)

    with pytest.raises(BundleExportError, match="outside"):
        export_diagnostic_bundle(
            source,
            source / "bundles",
            created_at=FIXED_TIME,
        )


def test_export_bundle_rejects_root_manifest_collision(tmp_path: Path) -> None:
    source = tmp_path / "trace"
    _write_trace(source)
    (source / "manifest.json").write_text("{}", encoding="utf-8")

    with pytest.raises(BundleExportError, match="manifest.json"):
        export_diagnostic_bundle(source, created_at=FIXED_TIME)
