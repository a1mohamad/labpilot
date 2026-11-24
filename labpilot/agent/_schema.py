"""What the tool schemas and their readers share."""


def list_schema(
    key: str, properties: dict[str, object], required: list[str]
) -> dict[str, object]:
    """A tool that answers with one list of objects, under `key`."""
    return {
        "type": "object",
        "properties": {
            key: {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            }
        },
        "required": [key],
    }


def number(value: object) -> int | None:
    # bool is an int in Python; a model that writes true is not naming a part.
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def index(value: object, below: int) -> int | None:
    """The number, when it is one of 0 .. below - 1."""
    found = number(value)
    return found if found is not None and 0 <= found < below else None


def is_located(item: object) -> bool:
    """An item with a text, a part number and a quote, each of the right type."""
    return (
        isinstance(item, dict)
        and isinstance(item.get("text"), str)
        and number(item.get("part")) is not None
        and isinstance(item.get("quote"), str)
    )
