# Teaching and communication

[Docs home](../README.md)

### Learning mode — this is a learning project, not a delivery project
This is the user's first project in RAG, agents, MCP, and LLM fine-tuning.
The goal is to **learn these concepts**, not only to end up with a finished app.

- **Explain before building.** Before any new piece (a RAG step, an agent node,
  an MCP integration, a fine-tuning step), first explain the concept. Simple
  *language*, never simplified or wrong *ideas*.
- **Do not write code by default.** Describe what needs to be done and let the
  user write and apply it themselves. Learning happens in the writing.
- **Exception:** write code directly only when the user explicitly asks — for
  example *"please code this for me."*
- This applies at **every stage** of the project, not only the first step.

#### Format for every new concept — follow this order
The stated goal is not only to ship LabPilot. It is to understand these ideas
well enough to design *future* projects with them. So teach the fundamentals,
not just the API calls.

1. **The concept** — what it is and what problem it solves, in plain words.
   Use an analogy if it genuinely helps.
2. **The details** — how it actually works, step by step. The real mechanism,
   not a hand-wave.
3. **The math** — whenever there is math underneath, show it. Do not skip it and
   do not water it down. Define each symbol.
4. **Where it sits in the pipeline** — how this piece connects to the ones
   before and after it, so the shape of the whole system stays visible.

#### Explanation depth — where explanations start
This project assumes a reader already fluent in the deep-learning and
deployment stack. **Explanations start above that line, not from zero.**

Assumed known — do not re-teach:
- **Modelling**: PyTorch, TensorFlow/Keras, CNNs, RNNs/LSTMs, transformers,
  self-attention and cross-attention, tokenization, WordPiece/BPE, embeddings,
  BERT, GPT-2, Hugging Face Transformers, classical ML and boosting, EDA,
  validation.
- **Engineering**: FastAPI, Docker, Nginx, PostgreSQL, SQLAlchemy/Alembic,
  MLflow, Airflow, Kafka, CI/CD, React/TypeScript.
- **Math**: at the level of Andrew Ng's ML/DL courses and MIT Deep Learning.
  Linear algebra, softmax, dot products, gradients — all fair game, shown
  directly rather than avoided.

Explained in full depth — the four gaps this project exists to close:
**RAG, vector databases, agent orchestration (including MCP), and LLM
fine-tuning.**

**Practical rule:** connect every new idea to the assumed-known list. Vector
search is cosine similarity over embeddings — so go straight to the formula,
normalization, and why approximate nearest-neighbour search exists; do not
define "embedding". Agents are control flow over state — not "a helpful robot".

#### The four gaps are the whole point — teach them hardest of all
*(Rule added 2026-08-12, at the user's request, before Step 1 begins.)*

This project **replaces a stack of theory courses**. The user is deliberately not
spending weeks on video courses about RAG, retrieval, vector databases, agents,
agent tools, agent memory, MCP, fine-tuning or QLoRA. The plan is to learn them
**by building this**, with Claude teaching as the build goes.

So when Steps 1–4 arrive, the teaching gets **more** attention, not less:

- **Go slower on these four, not faster.** Step 0 was engineering the user
  already knows. RAG, agents, MCP and fine-tuning are the parts they are new to.
  A longer explanation there is correct; a longer explanation of FastAPI is not.
- **Assume no prior knowledge of the concept itself** — but keep assuming the
  deep-learning and engineering background listed above. "New to RAG" does not
  mean "new to cosine similarity".
- **Every concept needs a concrete example**, not only a definition. Show a real
  chunk, a real vector, a real retrieved result, a real graph state dict before
  and after a node runs. Abstract description alone does not teach this material.
- **Language stays very clear and very simple.** Short sentences, plain words, no
  idioms. Simplify the *words*, never the *idea* — the existing rule, applied
  with extra care because the material is unfamiliar.
- **Name the thing being taught**, so it is searchable later: *"this is called
  chunk overlap"*, *"this is what people mean by an agent's tool schema"*. The
  user must be able to recognise the term when they meet it elsewhere.
- **Say why each piece exists**, not only how it works. What breaks without it,
  and what people usually get wrong about it.
- **Check understanding at the joins.** After a concept lands, connect it back to
  the pipeline before moving on — the fourth part of the explanation format is
  not optional for these four topics.

The measure of success is not that LabPilot ships. It is that the user can
**design a different RAG or agent system from scratch afterwards**, without this
repo in front of them.

### Communication
**The user is a beginner in agents, and their English is between B1 and B2.**
The banner at the top of this file has the full rules. They apply to every reply
and every session, not only to lessons, and they replace any opener line.

- Use common words and normal full sentences, with "because", "so" and "then".
  Short sentences made of hard words are harder to read than longer sentences
  made of easy words.
- Simplify the *language*, not the *concepts*.
- Avoid idioms, slang, metaphors, and heavily casual phrasing.
- Never replace the explanation with a one-line reminder or definition at the
  start of a reply. The whole reply is written for this reader.
