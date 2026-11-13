from labpilot.agent.errors import PlanError
from labpilot.agent.plan import Plan, Query
from labpilot.agent.plan_check import allowed_steps
from labpilot.ingest import Side

PLAN_TOOL_NAME = "make_plan"


def plan_schema(sides: tuple[Side, ...]) -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "steps": {
                "type": "array",
                "items": {"type": "string", "enum": list(allowed_steps(sides))},
            },
            "queries": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "side": {"type": "string", "enum": list(sides)},
                        "text": {"type": "string"},
                    },
                    "required": ["side", "text"],
                },
            },
            "ask": {"type": "string"},
            "about": {"type": "string", "enum": ["A", "B", "both"]},
            "files": {"type": "boolean"},
            "fresh": {"type": "boolean"},
        },
        "required": ["steps", "queries"],
    }


def read_plan(arguments: dict[str, object]) -> Plan:
    steps = arguments.get("steps")
    queries = arguments.get("queries")
    if not isinstance(steps, list) or not all(isinstance(s, str) for s in steps):
        raise PlanError(f"'steps' must be a list of text, got {type(steps).__name__}")
    if not isinstance(queries, list):
        raise PlanError(f"'queries' must be a list, got {type(queries).__name__}")

    made: list[Query] = []
    for item in queries:
        if not (
            isinstance(item, dict)
            and isinstance(item.get("side"), str)
            and isinstance(item.get("text"), str)
        ):
            raise PlanError("every query needs a 'side' and a 'text', both text")
        made.append(Query(item["side"], item["text"]))

    ask = arguments.get("ask", "")
    if ask is None:
        ask = ""
    if not isinstance(ask, str):
        raise PlanError(f"'ask' must be text, got {type(ask).__name__}")

    about = arguments.get("about", "both")
    if about is None:
        about = "both"
    if not isinstance(about, str):
        raise PlanError(f"'about' must be text, got {type(about).__name__}")

    flags: list[bool] = []
    for name, default in (("files", True), ("fresh", False)):
        flag = arguments.get(name, default)
        if flag is None:
            flag = default
        if not isinstance(flag, bool):
            raise PlanError(f"'{name!r}' must be a boolean, got {type(flag).__name__}")
        flags.append(flag)

    return Plan(
        steps=tuple(steps),
        queries=tuple(made),
        ask=" ".join(ask.split()),
        about=about,
        files=flags[0],
        fresh=flags[1],
    )
