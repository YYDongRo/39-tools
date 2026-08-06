from __future__ import annotations

from agent_devtools.cli import _browser_use_parser


def test_installed_cli_parser_uses_stable_command_name() -> None:
    parser = _browser_use_parser()
    args = parser.parse_args(
        ["--task", "Open the page.", "--max-steps", "4"]
    )

    assert parser.prog == "agent-devtools"
    assert args.task == "Open the page."
    assert args.max_steps == 4
