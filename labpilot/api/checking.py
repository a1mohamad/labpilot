import logging
from collections.abc import Callable, Sequence
from functools import partial

from labpilot.agent import (
    CHECK_TOOL_NAME,
    CheckError,
    Claim,
    Finding,
    check_schema,
    read_finding,
)
from labpilot.ingest import Chunk
from labpilot.llm import AllFreeTiersExhausted, LLMClient, LLMResult, Tool
from labpilot.prompts import (
    CHECK_MAX_TOKENS,
    CHECK_VERSION,
    build_check_prompt,
)

logger = logging.getLogger(__name__)

TOOL_DESCRIPTION = "Say whether the other file does what the claim says."


def _check_problem(
    result: LLMResult, *, claim: Claim, sources: Sequence[str], texts: Sequence[str]
) -> str | None:
    if result.arguments is None:
        return "no arguments"
    try:
        read_finding(result.arguments, claim, sources, texts)
    except CheckError as exc:
        return str(exc)
    return None


def make_checker(
    client: LLMClient,
    facts: Callable[[Sequence[Chunk]], str] | None = None,
    expand: Callable[[Sequence[Chunk]], tuple[Chunk, ...]] | None = None,
) -> Callable[[Claim, tuple[Chunk, ...]], Finding]:
    def check(claim: Claim, chunks: tuple[Chunk, ...]) -> Finding:
        # Go to definition: the parts that SET what the found parts only use.
        if expand is not None:
            chunks = expand(chunks)
        # The same rule as the claims: the model names a part by its NUMBER and
        # the code looks up the place.
        texts = [f"{chunk.header}\n{chunk.text}" for chunk in chunks]
        sources = [chunk.header or chunk.source for chunk in chunks]
        tool = Tool(
            name=CHECK_TOOL_NAME,
            description=TOOL_DESCRIPTION,
            parameters=check_schema(),
        )

        try:
            result = client.generate(
                build_check_prompt(
                    claim.text,
                    claim.source,
                    texts,
                    facts(chunks) if facts is not None else "",
                ),
                max_tokens=CHECK_MAX_TOKENS,
                tool=tool,
                problem_with=partial(
                    _check_problem, claim=claim, sources=sources, texts=texts
                ),
            )
        except AllFreeTiersExhausted as exc:
            raise CheckError(f"no tier could check it ({len(exc.attempts)})") from exc
        if result.arguments is None:
            raise CheckError(f"{result.model} gave no arguments")

        finding = read_finding(result.arguments, claim, sources, texts, chunks)
        logger.info(
            "check v%d by %s (tier %s): %s",
            CHECK_VERSION,
            result.model,
            result.tier,
            finding.verdict,
        )
        return finding

    return check
