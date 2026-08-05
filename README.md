# labpilot
Agent-based tool that compares a research paper against its code (or two codebases), explains why their results diverge, and proposes the next experiment. Built with LangGraph agents, RAG over Supabase/pgvector, a swappable multi-provider LLM fallback chain, and QLoRA fine-tuning via Unsloth. Flags mismatched pairs instead of forcing a comparison.
