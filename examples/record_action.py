from pathlib import Path

from agent_devtools.recorder import record_action
from agent_devtools.serialization import write_action_json


def simulated_click() -> None:
    pass


def main() -> None:
    action = record_action(
        action_type="click",
        arguments={"x": 100, "y": 200},
        operation=simulated_click,
    )
    output_path = Path("trace/action.json")
    write_action_json(action, output_path)
    print(f"Trace written to {output_path}")


if __name__ == "__main__":
    main()
