# Mutation testing

[Docs home](../README.md)

### Mutation testing — Claude's standing job, and it runs unasked

*Added 2026-08-28, at the user's request, and the reason is worth stating
plainly: **Claude writes the tests in this project.** So the user cannot be the
one who remembers to check whether those tests are real. The obligation sits
with whoever wrote the test, and that is Claude.*

This is the same shape as
[the network precondition](../rules/sources-and-network.md#network-precondition--check-the-exit-isp-before-any-llm-work):
Claude performs the check and reports the result; the user should never have to
ask for it.

**The rule, deliberately narrow:**

> **Whenever a test is written that pins an *invariant* — a rule that must
> always hold, not one example — break the thing it guards,
> run the suite, read WHICH test fired, then undo. Report the result before the
> commit. Never for ordinary tests: one happy path, one failure branch, a
> parametrized value list — those need no mutation.**

**The procedure, five steps:**

```
0. COMMIT FIRST, or copy the file aside      <- see the warning below
1. edit the source to break EXACTLY what the test guards   (one line)
2. run the suite
3. read which test failed - not merely that one did
4. git checkout -- <file>            (undo, always)
5. report the outcome in the message that delivers the test
```

> **Step 0 was learned by losing work, 2026-08-29.** `git checkout -- <file>`
> restores the file to the last **commit**, not to the state before the
> mutation. Mutating a file whose changes are **uncommitted** therefore deletes
> them. It silently wiped a finished `LOADERS` wiring in `chunker.py` and
> `sources/defaults.py`; only re-reading `git status` found it. **Commit before
> mutating, or the undo step is a delete step.**

**Three outcomes, and two of them are bugs:**

| Result | Verdict |
|---|---|
| the new test failed | ✅ real. Keep it |
| **nothing failed** | ❌ **the test is fake.** Fix it, then re-mutate |
| **something else failed, the new one never fires alone** | ❌ **the new test is dead.** Delete it |

**The evidence this is not optional.** Three self-fulfilling tests were found in
a single day (2026-08-17), all the same shape — an assertion whose input was
computed from the value under test, so it could never fail:

```python
huge = b"x = 1\n" * (MAX_UPLOAD_BYTES // 3)  # raise the limit, payload grows
over = b"x" * (MAX_REQUEST_BODY_BYTES + 1)  # same bug, hours later
```

**Reading the tests caught none of them. Mutating the source caught all three.**
And the rule *"a threshold test needs a literal on one side"* was written into
this file **and violated again within hours** — which is exactly why a written
rule is not enough and a performed check is.

**Step 3 is the one people skip.** *"A mutation was caught"* is not the check;
*"which test caught it"* is. That question deleted
`test_nothing_imports_the_entry_layer`, which could never fail on its own
because the layer rule always fired first — a comforting green line that tested
nothing.

**Do not reach for `mutmut` or `cosmic-ray`.** Automated mutation testing
mutates everything and is slow over 400+ tests on an
[8GB machine](environment.md#hardware-limits--important). The targeted manual version costs
seconds, because the invariant that was just written is already known.

#### The `mutation-test` skill — WRITTEN 2026-09-03

`.claude/skills/mutation-test/SKILL.md`, 157 lines. It holds the procedure
above, the three verdicts, both self-fulfilling-test traps, and all five slice 3
cases. Its `description` triggers on writing an invariant — a threshold, a
registry, a layering rule, a security guard, or any test name containing
*never / every / only / no* — and explicitly **excludes** ordinary tests.

**It is a project skill, not a personal one**, so it lives in the repository and
travels with the code — committed as `17db968`.

**A skill is read at session start.** So writing it does not arm it in the same
session — the rule below is what binds until the next session begins.

The checklist above becomes a **skill** (`SKILL.md`): written once, fired every
time a new invariant is written. A skill is *reusable instructions loaded on
demand*; this file is 5,000 lines and always loaded, which makes any single rule
inside it easy to skim past. **The gain is not new ability — it is a rule that
does not get skipped.**

**Write it after slice 3, not before.** Slice 3 produces new invariants (the
token cap moving onto `embed_text`, the notebook and PDF splitters), so its
content comes from real cases rather than a guess — the same rule this project
already applies to `base.py`: *extract the abstraction after the second case
exists.*

**And skills stay out of LabPilot itself.** They are a Claude-platform feature,
while the chain runs on Google, Mistral, OpenRouter and Cloudflare — the same
provider-neutrality argument that rejected the Claude Agent SDK. The Step 2
[capability library](../agent/design.md#the-capability-library) is already this idea implemented
across providers, with one deliberate difference: **our planner chooses in
code**, because *"never burn a generation call to decide how to spend generation
calls."*
