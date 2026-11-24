# LabPilot documentation

LabPilot reads a reference (A) and a subject (B), explains why their results diverge and
proposes the next experiment. These pages hold the design, the decisions with their reasons,
every measurement, and the rules of the project.

**Start here:** [current status](status/current.md) · [product overview](product/overview.md) ·
[the whole tree](SUMMARY.md)

## The folders

| folder | what is in it |
|---|---|
| [status/](status/current.md) | where the project stands, what is next, the branches, the history |
| [rules/](rules/sessions-and-commits.md) | how we work: [sessions and commits](rules/sessions-and-commits.md), [teaching](rules/teaching-and-communication.md), [modularization](rules/modularization.md), [sources and network](rules/sources-and-network.md), [traps](rules/traps.md) |
| [product/](product/overview.md) | the product, [the UI](product/ui.md), [the memory budget](product/memory-budget.md), [the build plan](product/build-plan.md), [risks](product/open-risks.md), [out of scope](product/out-of-scope.md) |
| [development/](development/environment.md) | [environment](development/environment.md), [code style and tests](development/code-style-and-tests.md), [mutation testing](development/mutation-testing.md), [layers](development/architecture-layers.md), [CI](development/ci-and-smoke-tests.md), [git](development/git-and-dependencies.md) |
| [architecture/](architecture/stack.md) | the stack |
| [agent/](agent/design.md) | the first agent design of Step 2 (2026-08), with later notes |
| [llm/](llm/chains.md) | the three chains, gateways, quotas, limits, [failure rules](llm/failure-rules-and-limits.md), accounts |
| [retrieval/](retrieval/design.md) | retrieval design and [chunking](retrieval/chunking.md) |
| [prompts/](prompts/comparison-template.md) | the comparison template and citations |
| [step0/](step0/slices-1-to-4.md), [step1/](step1/plan.md), [step2/](step2/00-plan.md), [step3/](step3/daily-chain-update.md), [step4/](step4/fine-tuning.md) | the work, step by step and slice by slice |
| [reference/](reference/section-map.md) | generated: [section map](reference/section-map.md), [decisions](reference/decisions.md), [measurements](reference/measurements.md); and [the sample pair](reference/sample-pair.md) |
| [slice8/](slice8/RESULTS.md), [slice8v2/](slice8v2/DECISIONS.md), [slice8v3/](slice8v3/DECISIONS.md), [step2/slice1/](step2/slice1/RESULTS.md) | the measurement reports |
| [archive/](archive/README.md) | the longer, older text of Steps 0 and 1, and retired rules |

## How to read a page

Pages keep the words and the dates of the day they were written. When a later result
changed something, the newest dated note wins. Where two pages disagree, this order wins:
[current status](status/current.md), then the newer section number, then the older one.

## How to change the docs

One truth: each fact is on one page. The rules are in the repository's
[CLAUDE.md](../CLAUDE.md). After a change:

```bash
python -m scripts.repo.build_docs_index
python -m pytest tests/unit/test_docs.py -q
```

`SUMMARY.md` has the form that mdBook reads, so the folder can become a web site later.
