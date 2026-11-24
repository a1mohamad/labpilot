# Fine-tuning plan

[Docs home](../README.md)

## Fine-Tuning Plan

- **Method**: QLoRA via Unsloth. Full fine-tuning is infeasible on free-tier
  hardware at any model size considered here.
- **Try first**: Gemma-4-26B-A4B (MoE, 25.2B total / ~3.8B active) — the
  stronger target, ~13–16GB in 4-bit.
- **Fall back to**: Gemma-4-E4B if the 26B proves too tight on Kaggle's 16GB
  GPU. E4B fits comfortably and is the safe option.
- *Risk note (unresolved)*: the 26B-first ordering is the ambitious choice.
  Loading it in 4-bit plausibly fits 16GB, but QLoRA training adds activations,
  gradients, and optimizer state on top — it may OOM. **Test with a tiny toy run
  early**; if it OOMs, drop to E4B rather than fighting it.
  **Escape hatch:** Lightning AI gives **~2 hours on an A100 40GB — once, not
  monthly** (5 one-time credits; corrected 2026-08-09). Use it to check whether
  the 26B trains *at all*, separately from whether it fits Kaggle's 16GB. Two
  hours is very little and does not come back — do not spend any of it exploring
  the interface. Start a **CPU** Studio first, install and prepare everything,
  then switch that same Studio to the A100 only when the code is ready to run.
  See [Lightning AI credit maths](../llm/platform-accounts.md#lightning-ai--read-the-credit-maths-before-using-it).
- **Ruled out**: Gemma-4-31B dense (does not fit a single free-tier GPU;
  multi-GPU is fragile and not worth it for a ~150–300 example dataset) and
  Kimi K3 (2.8T params, needs datacenter-scale infrastructure).
- Also comparing **Qwen3-4B** against the Gemma candidates.
- **Gemma 4 is also served free on the Google API** — noted 2026-08-11 while
  verifying the Gemini slugs: `gemma-4-31b-it` and `gemma-4-26b-a4b-it` both
  appear in `GET /v1beta/models` on the free key. This does **not** change the
  plan — fine-tuning downloads weights from Hugging Face and the like-for-like
  comparison runs on Modal, neither of which touches Google.
  **This became critical on 2026-08-11**: Cerebras was going to serve the
  evaluation baseline and is now dead (`402`, card required). **Google is now the
  only free place to run `gemma-4-26b-a4b-it`**, the actual fine-tune target, as
  a baseline. Losing that Google account would cost the evaluation as well as
  **six** generator tiers.
- **Evaluation**: fine-tuned model vs. base model, and vs. `gemma-4-31b`.
  **Run the baseline on Google** — *changed 2026-08-11; the earlier plan said
  Cerebras, which now requires a card.* **The quota is better than the old note
  claimed, for this job specifically:** `gemma-4-26b-a4b-it` and `gemma-4-31b-it`
  each allow **14,400 requests/day** (measured 2026-08-16), so a few hundred
  evaluation prompts cost nothing. The 16K input limit that blocks Gemma from
  serving *reports* does not bite here — evaluation prompts are short.
  OpenRouter's ~50/day could not do this at all. Run
  the fine-tuned model on Modal or ZeroGPU. Where a like-for-like comparison
  matters, run both the fine-tuned model *and* the base model on Modal, on the
  same GPU with the same settings, so differences come from the fine-tuning and
  not the hardware.
- **Dataset**: ~150–300 examples, built from ~100 existing notebooks across
  projects, Kaggle competition write-ups, real papers where they genuinely
  exist, and notebook-vs-notebook pairs (one side rewritten as a paper-style
  paragraph).
- **Dataset shape — corrected 2026-08-13. Each example must be built by running
  the retriever, not from whole documents.** Fine-tuning teaches *behaviour*
  (format, citation habit, saying "not specified"), not *facts* — 200 examples
  cannot install knowledge, and RAG is what supplies knowledge. So an example is:

  ```
  prompt_i  = instructions + retrieved chunks with [source] tags + the question
  answer_i  = the ideal divergence report, with correct citations
  ```

  Train on whole documents and the model learns that the answer is **always
  fully present** — then hallucinates the moment retrieval returns partial
  context. The failure is called **train–serve skew**, and the fix is called
  **RAFT** (Retrieval-Augmented Fine-Tuning).

  **Include ~20% deliberately weak examples** — irrelevant chunks, or no correct
  chunk at all — whose target answer is honest: *"The retrieved code does not
  show a learning-rate schedule, so this cannot be verified."* This is how
  honesty is trained; a model never shown that case always invents something. It
  serves the partial-correspondence and missing-detail edge cases directly.

  Retrieval runs during **dataset construction only**. The training loop sees
  frozen strings and never touches a database.

  **This is a second, harder reason fine-tuning is last:** the dataset cannot
  exist until the retriever does. Step 4 depends on Steps 1–3 having run, not
  merely on them being understood.
- **Platform**: Kaggle Notebooks (free, ~30 GPU-hrs/week). Checkpoint the LoRA
  adapter regularly to survive session limits; resume across sessions rather
  than restarting.
- **Saving**: push LoRA adapters (small) to Hugging Face Hub during iteration;
  merge into a full model only at final deployment.

### Serving the fine-tuned model — demo only

**The live app always uses the hosted fallback chain.** It must keep working
whether or not the fine-tuned model is running. The fine-tuned model is a
portfolio artifact, never part of the live reasoning path.

Two serving paths, both free and both verified 2026-08-08:

**Primary — Hugging Face Space on ZeroGPU.** Permanent `*.hf.space` URL, works
without the user being present. This replaces the earlier Kaggle-tunnel plan.
- ZeroGPU allocates a shared GPU only *during* a decorated function call, then
  takes it back. The "large" slice is ~48GB VRAM — enough for the 26B MoE in
  4-bit, and far more than E4B needs.
- **Gradio SDK only.** Docker and CPU Basic Spaces now require a paid plan;
  Static Spaces are free but have no server, so they cannot run a model.
  A FastAPI server therefore cannot be written directly on a Space — but Gradio
  runs *on* FastAPI and exposes an HTTP API automatically, so the endpoint is
  still callable from code (`gradio_client` or the `/api/predict` route).
- Free accounts: max 2 ZeroGPU Spaces, account must be >30 days old with a
  verified email. Daily quota is measured in **GPU-seconds and is small**; a
  call reserves the full requested `duration` up front, so set a realistic small
  value rather than leaving the default.
- **Known unknown, test early:** Unsloth alters CUDA behaviour and ZeroGPU
  allocates the GPU unusually. For *serving*, prefer plain `transformers` +
  `peft` to load base + adapter, and keep Unsloth for *training* only. Also note
  the model cannot simply be loaded once at startup — the GPU only exists inside
  the decorated function. This is the most common place people get stuck.

**Secondary — Modal, "Custom weights".** Gives a real HTTPS endpoint on a
container you define, so a FastAPI-shaped API is possible exactly as originally
planned, on a GPU large enough for the 26B.
- Everything on Modal is billed from the $30 Starter credit — dedicated
  infrastructure by GPU-second, shared infrastructure by token.
- **The $30 now has exactly one job.** *(Settled 2026-08-11 — Modal was removed
  from the generator chain.)* It serves the fine-tuned model demo, which is the
  job nothing free can do. The old conflict between "backstop the chain" and
  "serve the demo" no longer exists, and the chain never spends credit.
- **Never point development or bulk testing at Modal.** Use llm7.io or a
  low-tier free provider as the development workhorse instead.
- **Unverified:** whether the $30 renews monthly. Check the balance in early
  September 2026 before planning around it — and check it again once tier 6 has
  actually been exercised.
- Always confirm the app has scaled back to zero after testing.

**Considered and rejected for serving — Lightning AI.** *(Reason corrected
2026-08-09.)*

The earlier reason written here — "a Studio is a development machine, not a
host" — was **wrong**. Lightning's own free-tier feature table ticks *"Deploy
no-code model endpoints"* and *"Deploy full control model endpoints"*, and their
inference product (LitServe, containers as autoscaling APIs) is built exactly
for this. It **can** host a fine-tuned model with a real endpoint.

The real reason it is rejected is **arithmetic, not capability**: there is no
recurring free GPU allowance. 5 one-time credits ≈ **~2 hours on an A100**. A
served endpoint bills for every hour it is *up*, so the demo would die within a
day and never come back — and the credits never refill.

ZeroGPU wins because it bills nothing while idle: the GPU is only attached
*during* a call. That is the property serving needs, and Lightning's Studio
credits do not have it.

Lightning stays a **one-shot training escape hatch** only.

**Fallback — Kaggle notebook + Cloudflare Tunnel.** Still works for recording a
demo video with 2×T4. Non-permanent URL, 12h sessions, and Kaggle's AUP forbids
"server farming" — acceptable for a short recorded demo, never as a hosted
service. Do not point the deployed website at it.

**The portfolio artifact** is: LoRA adapter on the Hugging Face Hub + training
notebook + evaluation results + the live ZeroGPU Space (and a recorded video).

