"""Safe, low-cardinality metadata about the process that recorded a run."""

from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
import platform


@dataclass(frozen=True)
class RuntimeContext:
    """Allowlisted runtime metadata stored with an action session.

    The model deliberately excludes environment variables, executable paths,
    hostnames, usernames, and page content. Optional dependency versions are
    ``None`` when that package is not installed.
    """

    agent_devtools_version: str
    python_version: str
    os_name: str
    os_version: str
    architecture: str
    playwright_version: str | None = None
    browser_use_version: str | None = None

    def __post_init__(self) -> None:
        required_fields = (
            "agent_devtools_version",
            "python_version",
            "os_name",
            "os_version",
            "architecture",
        )
        for field_name in required_fields:
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} cannot be empty")
        for field_name in ("playwright_version", "browser_use_version"):
            value = getattr(self, field_name)
            if value is not None and (
                not isinstance(value, str) or not value.strip()
            ):
                raise ValueError(f"{field_name} must be a non-empty string or None")


def collect_runtime_context() -> RuntimeContext:
    """Collect only stable, non-secret process metadata.

    Missing optional packages are represented as ``None``. Collection is
    intentionally best-effort so a diagnostic report can never fail because a
    metadata provider is unavailable.
    """

    return RuntimeContext(
        agent_devtools_version=_package_version("39-tools") or "unknown",
        python_version=platform.python_version() or "unknown",
        os_name=platform.system() or "unknown",
        os_version=platform.release() or "unknown",
        architecture=platform.machine() or "unknown",
        playwright_version=_package_version("playwright"),
        browser_use_version=_package_version("browser-use"),
    )


def _package_version(distribution: str) -> str | None:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return None
    except Exception:
        # Importlib metadata providers are optional diagnostics only.
        return None
