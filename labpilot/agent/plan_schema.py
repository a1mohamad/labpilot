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

    return Plan(steps=tuple(steps), queries=tuple(made))
