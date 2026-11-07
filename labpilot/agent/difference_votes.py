from collections.abc import Mapping, Sequence
from dataclasses import replace

from labpilot.agent.difference import DIFFERS, SILENT, Difference
from labpilot.agent.difference_schema import FALSE, REAL, SAME

# One audit answer: the vote it belongs to, and for each fact number the
# verdict and the Difference (for "differs" and "missing").
AuditAnswer = tuple[int, Mapping[int, tuple[str, Difference | None]]]
# What the judges said about one finding: (verdict, relation) for each vote.
JudgeVotes = Mapping[int, Sequence[tuple[str, str]]]


def audit_findings(answers: Sequence[AuditAnswer], count: int) -> list[Difference]:
    """The facts B breaks, each once, in the order of the facts.

    Inside one vote, "same" in any group of B wins: the rule may be done in
    another part. Across votes, one vote that flags a fact is enough, because a
    missed difference costs more than a doubtful one the judge removes.
    """
    found: list[Difference] = []
    votes = sorted({vote for vote, _ in answers})
    for n in range(count):
        for vote in votes:
            said = [got[n] for v, got in answers if v == vote and n in got]
            if any(verdict == SAME for verdict, _ in said):
                continue
            differences = [d for _, d in said if d is not None]
            if differences:
                found.append(differences[0])
                break
    return found


def judged_findings(
    findings: Sequence[Difference], votes: JudgeVotes
) -> list[Difference]:
    """The findings the judges keep, with their kind and doubt set.

    A finding stays when one vote says "real". All "false", all "minor" and
    "minor + false" go. "Real + false" stays as unclear. A finding no vote
    answered stays as it is. When every vote says B does what A states, it is
    not a difference. A scan item the judges say A states otherwise becomes
    "differs".
    """
    kept: list[Difference] = []
    for n, found in enumerate(findings):
        said = votes.get(n, ())
        if not said:
            kept.append(found)
            continue
        verdicts = {verdict for verdict, _ in said}
        relations = {relation for _, relation in said}
        if REAL not in verdicts or relations == {SAME}:
            continue
        kind = DIFFERS if found.kind == SILENT and DIFFERS in relations else found.kind
        kept.append(replace(found, kind=kind, unclear=FALSE in verdicts))
    return kept


def merged_findings(
    findings: Sequence[Difference], groups: Sequence[Sequence[int]]
) -> list[Difference]:
    """Each point once: the first finding of a group stays, the others go."""
    dropped = {n for group in groups for n in sorted(group)[1:]}
    return [found for n, found in enumerate(findings) if n not in dropped]
