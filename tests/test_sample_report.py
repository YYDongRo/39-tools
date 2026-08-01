import re
import runpy
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMMITTED_SAMPLE = PROJECT_ROOT / "docs" / "sample-report"
SAMPLE_SCRIPT = runpy.run_path(
    str(PROJECT_ROOT / "examples" / "generate_sample_report.py")
)
generate_sample_report = SAMPLE_SCRIPT["generate_sample_report"]


def _files(directory: Path) -> dict[Path, bytes]:
    return {
        path.relative_to(directory): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def test_sample_report_is_deterministic_and_current(tmp_path: Path) -> None:
    output_dir = tmp_path / "sample-report"

    generate_sample_report(output_dir)
    first_generation = _files(output_dir)
    generate_sample_report(output_dir)

    assert _files(output_dir) == first_generation
    assert first_generation == _files(COMMITTED_SAMPLE)


def test_sample_report_is_sanitized_and_explains_task_failure(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "sample-report"
    generate_sample_report(output_dir)
    report = (output_dir / "report.html").read_text(encoding="utf-8")
    generated_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(output_dir.rglob("*"))
        if path.is_file()
    )

    assert '<strong class="result-title">Failed</strong>' in report
    assert '<span>Actions</span><strong>4</strong>' in report
    assert '<span>Executed</span><strong>4 succeeded</strong>' in report
    assert '<span>Action failures</span><strong>0</strong>' in report
    assert '<span>Action checks</span><strong>3 of 4 run</strong>' in report
    assert "The final click selected &#x27;USB-C Cable&#x27;." in report
    assert "product title contains &#x27;Wireless Headphones&#x27;" in report
    assert "product title is &#x27;USB-C Cable&#x27;" in report

    image_sources = re.findall(r'<img src="([^"]+)"', report)
    assert len(image_sources) == 8
    assert all(not Path(source).is_absolute() for source in image_sources)
    assert all((output_dir / source).is_file() for source in image_sources)

    forbidden_patterns = (
        r"(?i)api[_-]?key",
        r"(?i)authorization\s*:",
        r"(?i)bearer\s+[a-z0-9]",
        r"(?i)sk-[a-z0-9]",
        r"AIza[a-zA-Z0-9_-]+",
        r"file://",
        r"[A-Za-z]:\\",
        r"/(?:home|Users|mnt)/",
        r"(?:localhost|127\.0\.0\.1)",
    )
    assert all(
        re.search(pattern, generated_text) is None
        for pattern in forbidden_patterns
    )
    assert str(PROJECT_ROOT) not in generated_text

    urls = re.findall(r"https?://[^&<\s]+", report)
    assert urls
    assert all(url.startswith("https://shop.example.test") for url in urls)
