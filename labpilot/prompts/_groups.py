from collections.abc import Sequence

from labpilot.tokens import estimate_tokens


def groups_of(parts: Sequence[str], target: int) -> list[list[int]]:
    """The parts, in order, cut into groups of about `target` tokens.

    The number of groups is the total divided by the target, rounded, and every
    group gets about the same share, so 4,300 tokens become two groups of about
    2,150 and not one of 2,000 and one of 300. A part is never cut.
    """
    sizes = [estimate_tokens(part) for part in parts]
    total = sum(sizes)
    count = min(len(parts), max(1, round(total / target)))
    share = total / count if count else 0

    groups: list[list[int]] = []
    current: list[int] = []
    used = 0
    for index, size in enumerate(sizes):
        current.append(index)
        used += size
        if len(groups) < count - 1 and used >= share * (len(groups) + 1):
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups
