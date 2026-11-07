from collections.abc import Sequence

from labpilot.tokens import estimate_tokens


def groups_of(
    parts: Sequence[str], target: int, *, files: Sequence[str] | None = None
) -> list[list[int]]:
    """The parts, in order, cut into groups of about `target` tokens.

    The number of groups is the total divided by the target, rounded, and every
    group gets about the same share, so 4,300 tokens become two groups of about
    2,150 and not one of 2,000 and one of 300. A part is never cut.

    With `files` (the file of each part, in the same order), a cut that falls
    inside a file moves to the start or the end of that file, whichever is
    nearer, when the whole file fits in one group, so a small file is never
    split between two calls. A bigger file is cut between its parts, as before.
    """
    sizes = [estimate_tokens(part) for part in parts]
    total = sum(sizes)
    count = min(len(parts), max(1, round(total / target)))
    share = total / count if count else 0

    cuts: list[int] = []
    used = 0
    for index, size in enumerate(sizes):
        used += size
        if len(cuts) < count - 1 and used >= share * (len(cuts) + 1):
            cuts.append(index)
    if files is not None:
        moved = {_to_file_edge(cut, sizes, files, target) for cut in cuts}
        cuts = sorted(cut for cut in moved if 0 <= cut < len(parts) - 1)

    groups: list[list[int]] = []
    start = 0
    for cut in cuts:
        groups.append(list(range(start, cut + 1)))
        start = cut + 1
    if start < len(parts):
        groups.append(list(range(start, len(parts))))
    return groups


def _to_file_edge(
    cut: int, sizes: Sequence[int], files: Sequence[str], target: int
) -> int:
    # A group ends after part `cut`. When that is inside a file, end it just
    # before the file or at its last part, whichever moves fewer tokens.
    if cut + 1 >= len(files) or files[cut] != files[cut + 1]:
        return cut
    first = cut
    while first > 0 and files[first - 1] == files[cut]:
        first -= 1
    last = cut + 1
    while last + 1 < len(files) and files[last + 1] == files[cut]:
        last += 1
    if sum(sizes[first : last + 1]) > target:
        return cut
    before = first - 1
    after = last
    if before < 0:
        return after
    if after >= len(files) - 1:
        return before
    moved_on = sum(sizes[first : cut + 1])
    moved_back = sum(sizes[cut + 1 : last + 1])
    return before if moved_on <= moved_back else after


def whole_files(parts: Sequence[str], files: Sequence[str], limit: int) -> list[int]:
    """The parts of the files that fit in `limit` tokens, whole files only.

    The files are taken in their order. A file that does not fit is skipped and
    the next one is tried, so a smaller file can still fit. When nothing was
    taken and the first file alone is bigger than the limit, its first parts up
    to the limit are taken, so a file is never read for nothing.
    """
    sizes = [estimate_tokens(part) for part in parts]
    runs: list[list[int]] = []
    for index, name in enumerate(files):
        if runs and files[runs[-1][0]] == name:
            runs[-1].append(index)
        else:
            runs.append([index])

    taken: list[int] = []
    spent = 0
    for run in runs:
        cost = sum(sizes[i] for i in run)
        if spent + cost <= limit:
            taken += run
            spent += cost
    if taken or not runs:
        return taken
    for index in runs[0]:
        if spent + sizes[index] > limit:
            break
        taken.append(index)
        spent += sizes[index]
    return taken
