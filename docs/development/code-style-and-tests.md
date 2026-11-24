# Code style and tests

[Docs home](../README.md)

## Conventions

### Code style — write it the way a senior engineer would
Every piece of code in this repo should look like production code written by
someone experienced, not like a tutorial snippet. Concretely:

**Choose OOP or plain functions deliberately — never by habit.**
Both are used in this project. Pick per case, and be able to say why.

| Use a **class** when | Use a **plain function** when |
|---|---|
| State and behaviour belong together (config a method set shares) | The output depends only on the arguments — a pure transformation |
| Several variants share one interface and are swapped at runtime (the chain's providers) | There is one way to do it and no state to carry |
| The object is a value worth naming (`LLMResult`, `Attempt`) — use a frozen `@dataclass` | A helper is small, private, and used in one place |

Rules that override the table:
- **Never create an abstract base class with only one implementation.** Write
  the second one first, see where they actually differ, then extract the base.
  Abstraction invented before the second case is almost always the wrong shape.
- **A class with one method and no state is a function.** Write the function.
- **Do not use a class purely to group functions.** That is what a module is.

**The rest of the bar:**
- Full type hints on every public function, method, and dataclass field.
- Value objects are `@dataclass(frozen=True, slots=True)`; mutable default
  values never appear in a signature.
- Keyword-only arguments (`*` or `kw_only=True`) for anything with more than
  two parameters — call sites must be readable without checking the definition.
- One error vocabulary per layer. Wrap foreign exceptions in our own type and
  keep the cause with `raise ... from exc`.
- **A caller's bug and a provider's failure are different exceptions.** An empty
  prompt is `ValueError` and must crash; a dead endpoint is `LLMError` and must
  be caught by the fallback loop. Never let one hide the other.
- Never log or `repr` a secret. Store the *name* of the env var, read the value
  at call time.
- Private helpers get a leading underscore. Public names carry no underscore and
  are the file's real interface.
- No dead code, no commented-out code, no `TODO` without a follow-up decision.

**Docstrings and inline comments are added in a separate later pass**, with the
documentation skill — not while the logic is being written. So code is drafted
**raw**: names, types, and structure carry the meaning on their own. If a raw
function is unreadable without a comment, the fix is a better name or a smaller
function, not a comment. When the doc pass runs, docstrings say *why*, not
*what* — the signature already says what.

**Claude posts code in the chat; the user types it into the file.** Do not write
project source files directly unless asked to. Learning happens in the typing.

### Tests and error handling — written with the code, never after
Both are part of "done". A feature is not finished when it returns the right
answer once; it is finished when its failures are handled and its behaviour is
pinned by tests. Both land in the **same commit** as the code they cover.

**The standard is sufficient, not maximal.** Bad test suites fail in two
opposite ways, and both are rejected here:

| Too little | Too much |
|---|---|
| Only the happy path | A test per line, restating the implementation |
| Bare `except Exception: pass` | A `try` around code that cannot fail |
| Errors that lose the cause | Five tests for one behaviour with different values |
| A crash with no context | Mocks so deep the test proves nothing about reality |

**Rules for error handling:**
- Handle a failure only where you can *do* something about it. Otherwise let it
  travel up to a layer that can.
- Every `except` either recovers, or re-raises as this layer's own error type
  with `from exc`. Never swallow.
- Error messages name the source and carry the provider's own words. `HTTP 400`
  alone is not a message.
- Distinguish *their* failure from *our* bug — see the `LLMError` vs
  `ValueError` rule above.

**Rules for tests:**
- One test asserts one behaviour, and its name says which: `test_<what>_<when>`.
- Cover: the happy path, each distinct **failure branch** written in the code,
  and the **contract** with the outside world (the exact request shape sent).
- Do not test the language or the standard library. A frozen dataclass being
  frozen is not our behaviour.
- Use `pytest.mark.parametrize` when several inputs exercise the *same* branch;
  write separate tests when the branches differ.
- **Unit tests never touch the network.** Mock at the HTTP boundary, not at our
  own function boundary — mocking our own code makes the test prove nothing.
- **Smoke tests do touch the network, and never run by default.** Mark them
  `@pytest.mark.smoke` and require an opt-in flag. OpenRouter's free pool is
  ~50 requests/day; a test suite must not spend it.
- Test layers arrive when the layer they test arrives: unit now, API tests with
  FastAPI, integration tests with retrieval, end-to-end at Step 3. Do not write
  a test for a layer that does not exist yet.

**Review pass:** after a section is finished, re-read its tests and error paths
once and ask only *"which real failure is still unprotected?"* Add what is
genuinely missing. Do not add tests to raise a number.
