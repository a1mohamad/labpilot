# Open risks

[Docs home](../README.md)

## Open Risks / Revisit Before or During the Build

*(flagged during planning — not yet resolved)*

- **Timeline is tight**: first exposure to RAG + agents + MCP + fine-tuning all
  at once. One month may be optimistic — consider extending if the
  walking-skeleton step reveals the core approach needs real rework, not just
  deepening.
- ~~**MCP could be a stretch goal** rather than a hard week-4 deliverable — it is
  the least essential of the four skill gaps to the core product story.~~
  **Partly resolved 2026-08-11:** MCP now has a concrete justification — search +
  fetch exposed as an MCP server for the web-search capability, extensible later
  to a linter or package-index lookup. See
  [Web search](../agent/design.md#web-search--step-25-opt-in-and-where-mcp-finally-fits).
  It remains *scheduled* late (Step 2.5), but it is no longer purposeless.
- **Dataset construction is tedious and should not wait for week 4** — start it
  in parallel with week 1, since it does not depend on the agent/RAG system.
- **Risk sequencing**: fine-tuning is the least-familiar skill and is scheduled
  last. Consider a small early de-risking experiment (tiny toy fine-tune) before
  committing the full week-4 timeline.
- **Research can substitute for building.** Searching feels productive and
  produces visible output, but only writing code moves the project. If a session
  ends with more browser tabs than commits, that is the signal.
- **Free tiers change constantly.** Every number in this file was true on
  2026-08-08. Re-check against official pages before depending on any of them.

