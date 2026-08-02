import re
import runpy
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMMITTED_SAMPLE = PROJECT_ROOT / "docs" / "sample-evaluation"
SAMPLE_SCRIPT = runpy.run_path(
    str(PROJECT_ROOT / "examples" / "generate_sample_evaluation.py")
)
generate_sample_evaluation = SAMPLE_SCRIPT["generate_sample_evaluation"]


def _files(directory: Path) -> dict[Path, bytes]:
    return {
        path.relative_to(directory): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def test_sample_evaluation_is_deterministic_and_current(tmp_path: Path) -> None:
    output_dir = tmp_path / "sample-evaluation"

    generate_sample_evaluation(output_dir)
    first_generation = _files(output_dir)
    generate_sample_evaluation(output_dir)

    assert _files(output_dir) == first_generation
    assert first_generation == _files(COMMITTED_SAMPLE)


def test_sample_evaluation_is_sanitized_and_explains_stability(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "sample-evaluation"
    generate_sample_evaluation(output_dir)
    report = (output_dir / "report.html").read_text(encoding="utf-8")
    generated_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(output_dir.rglob("*"))
        if path.is_file()
    )

    assert "Passed: 3" in report
    assert "Failed: 2" in report
    assert "Unverified: 1" in report
    assert "Errored: 0" in report
    assert "50.0%" in report
    assert "Runs 2, 5" in report
    assert "action arguments differed" in report
    assert 'href="runs/001/report.html"' in report
    for run_number in range(1, 7):
        trace_dir = output_dir / "runs" / f"{run_number:03d}"
        assert (trace_dir / "session.json").is_file()
        assert (trace_dir / "report.html").is_file()
        run_report = (trace_dir / "report.html").read_text(encoding="utf-8")
        for source in re.findall(r'<img src="([^"]+)"', run_report):
            assert not Path(source).is_absolute()
            assert ".." not in Path(source).parts
            assert (trace_dir / source).is_file()

    image_sources = re.findall(r'<img src="([^"]+)"', generated_text)
    assert image_sources
    assert all(not Path(source).is_absolute() for source in image_sources)
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
    urls = re.findall(r"https?://[^&<\s\"']+", generated_text)
    assert urls
    assert all(
        url.startswith("https://shop.example.test")
        or url == "http://www.w3.org/2000/svg"
        for url in urls
    )
