from __future__ import annotations

import threading
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

import pytest

from agent_devtools.browser_use import (
    evaluate_browser_use_agent,
    observe_browser_use_agent,
)


browser_use = pytest.importorskip("browser_use")
Agent = browser_use.Agent
Browser = browser_use.Browser
JudgementResult = pytest.importorskip(
    "browser_use.agent.views"
).JudgementResult
ChatInvokeCompletion = pytest.importorskip(
    "browser_use.llm.views"
).ChatInvokeCompletion


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


@contextmanager
def local_page() -> Iterator[str]:
    directory = Path(__file__).resolve().parents[2] / "examples"
    handler = partial(QuietHandler, directory=directory)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield (
            f"http://127.0.0.1:{server.server_port}/"
            "gemini_browser_agent.html"
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class DeterministicModel:
    _verified_api_keys = True
    model = "deterministic-browser-use-test"
    provider = "local-test"
    name = model

    def __init__(self, target_url: str) -> None:
        self.target_url = target_url
        self.action_calls = 0

    @property
    def model_name(self) -> str:
        return self.model

    async def ainvoke(
        self,
        messages: list[object],
        output_format: type[object] | None = None,
        **kwargs: object,
    ) -> object:
        if output_format is JudgementResult:
            completion = JudgementResult(
                verdict=True,
                reasoning="The requested local page is open.",
                failure_reason=None,
                impossible_task=False,
                reached_captcha=False,
            )
        elif output_format is not None:
            self.action_calls += 1
            action = (
                {"navigate": {"url": self.target_url, "new_tab": False}}
                if self.action_calls == 1
                else {
                    "done": {
                        "text": "Opened the local page.",
                        "success": True,
                        "files_to_display": [],
                    }
                }
            )
            completion = output_format.model_validate(
                {
                    "evaluation_previous_goal": "The previous step is valid.",
                    "memory": "Open the requested local page.",
                    "next_goal": "Open the local page.",
                    "action": [action],
                }
            )
        else:
            completion = "ok"
        return ChatInvokeCompletion(
            completion=completion,
            usage=None,
            stop_reason="stop",
        )


def test_real_browser_use_agent_records_initial_navigation(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        with local_page() as target_url:
            task = f"Open the local page at {target_url}"
            model = DeterministicModel(target_url)
            browser = Browser(
                headless=True,
                chromium_sandbox=False,
                allowed_domains=["127.0.0.1"],
            )
            raw_agent = Agent(
                task=task,
                llm=model,
                judge_llm=model,
                browser=browser,
                use_judge=True,
                enable_planning=False,
                message_compaction=False,
                generate_gif=False,
            )
            agent = observe_browser_use_agent(raw_agent, task, tmp_path)
            try:
                await agent.run(max_steps=3)
            finally:
                await browser.stop()

        assert raw_agent.directly_open_url is False
        assert raw_agent.initial_actions is None
        assert raw_agent.settings.max_actions_per_step == 1
        assert agent.last_session is not None
        assert agent.last_session.action_count == 1
        action = agent.last_session.actions[0]
        assert action.action_type == "navigate"
        assert action.screenshot_before is not None
        assert action.screenshot_after is not None
        assert agent.last_session.verification is not None
        assert agent.last_session.verification.passed is True
        assert agent.last_report_path is not None
        assert agent.last_report_path.is_file()

    import asyncio

    asyncio.run(run())


def test_real_browser_use_evaluation_uses_fresh_numbered_runs(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        with local_page() as target_url:
            task = f"Open the local page at {target_url}"
            agents: list[object] = []

            def create_agent(factory_task: str) -> object:
                assert factory_task == task
                model = DeterministicModel(target_url)
                agent = Agent(
                    task=task,
                    llm=model,
                    judge_llm=model,
                    browser=Browser(
                        headless=True,
                        chromium_sandbox=False,
                        allowed_domains=["127.0.0.1"],
                    ),
                    use_judge=True,
                    enable_planning=False,
                    message_compaction=False,
                    generate_gif=False,
                )
                agents.append(agent)
                return agent

            evaluation = await evaluate_browser_use_agent(
                agent_factory=create_agent,
                task=task,
                runs=2,
                max_steps=3,
                output_root=tmp_path,
            )

        assert evaluation.passed_count == 2
        assert len({id(agent) for agent in agents}) == 2
        assert tuple(run.trace_directory.as_posix() for run in evaluation.runs) == (
            "runs/001",
            "runs/002",
        )
        for run in evaluation.runs:
            trace_dir = evaluation.output_dir / run.trace_directory
            assert (trace_dir / "session.json").is_file()
            assert (trace_dir / "report.html").is_file()
        assert (evaluation.output_dir / "evaluation.json").is_file()
        assert evaluation.report_path.is_file()

    import asyncio

    asyncio.run(run())
