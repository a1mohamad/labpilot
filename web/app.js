"use strict";

// TWO DOORS. Ingest is paid ONCE per artifact; a question sends only ids.
//
// Under the old single endpoint every question re-uploaded, re-chunked and
// re-embedded both sides - about fifteen minutes per question for a large
// repository. That is why this file uploads on selection and then never sends
// a file again.
const ARTIFACTS = "/api/v1/artifacts";
const COMPARE = "/api/v1/compare";
/** The chat this page is in. The server makes the id on the first answer. */
const THREAD_KEY = "labpilot.thread";
/** What each slot currently holds, once the server has stored it. */
const stored = { A: null, B: null };

const ask = document.getElementById("ask");
const compareButton = document.getElementById("compare");
const ready = document.getElementById("ready");
const status = document.getElementById("status");
const result = document.getElementById("result");
const failure = document.getElementById("failure");
const questionBox = document.getElementById("question");

// The question box is prefilled and EDITABLE, never a placeholder: this text is
// also the retrieval query. What it says follows how many sides are stored, and
// it stops following the moment the person types. Version 2 (version 1 was one
// fixed sentence that only made sense for two files).
const DEFAULT_QUESTION = [
  "Ask a question, or add files to compare.",
  "Summarize this and find likely bugs.",
  "Compare these and explain why the results diverge.",
];
let questionTouched = false;
questionBox.addEventListener("input", () => {
  questionTouched = true;
});
/** True while a question is on its way, so it cannot be sent twice. */
let waiting = false;

for (const slot of document.querySelectorAll(".slot")) {
  wireSlot(slot);
}
refreshReady();

function wireSlot(slot) {
  const side = slot.dataset.side;
  const drop = slot.querySelector("[data-drop]");
  const file = slot.querySelector("[data-file]");

  file.addEventListener("change", () => {
    if (file.files.length) upload(slot, side, { file: file.files[0] });
  });

  // Drag and drop, which costs a few lines and is what people expect.
  for (const name of ["dragenter", "dragover"]) {
    drop.addEventListener(name, (event) => {
      event.preventDefault();
      drop.classList.add("over");
    });
  }
  for (const name of ["dragleave", "drop"]) {
    drop.addEventListener(name, () => drop.classList.remove("over"));
  }
  drop.addEventListener("drop", (event) => {
    event.preventDefault();
    const dropped = event.dataTransfer.files[0];
    if (dropped) upload(slot, side, { file: dropped });
  });

  slot.querySelector("[data-url-form]").addEventListener("submit", (event) => {
    event.preventDefault();
    const url = slot.querySelector("[data-url]").value.trim();
    if (url) upload(slot, side, { url });
  });
}

/** POST /artifacts for one side - a file, a .zip, or a git URL. */
async function upload(slot, side, source) {
  const state = slot.querySelector("[data-state]");
  const label = source.url || source.file.name;

  stored[side] = null;
  refreshReady();
  slot.dataset.status = "working";
  state.className = "state working";
  state.textContent = `Reading ${label}…`;

  const body = new FormData();
  body.append("side", side);
  if (source.url) body.append("url", source.url);
  else body.append("file", source.file, source.file.name);

  try {
    const response = await fetch(ARTIFACTS, { method: "POST", body });
    const payload = await response.json();

    if (!response.ok) {
      slot.dataset.status = "error";
      state.className = "state bad";
      state.textContent = `${payload.error.code}: ${payload.error.message}`;
      return;
    }

    stored[side] = payload;
    slot.dataset.status = "ready";
    state.className = "state good";
    state.replaceChildren(...describe(payload));
  } catch (error) {
    slot.dataset.status = "error";
    state.className = "state bad";
    state.textContent = String(error);
  } finally {
    refreshReady();
  }
}

/** What came back, in the order a reader cares about. */
function describe(payload) {
  const parts = [
    tag(`${payload.chunks} chunks`),
    tag(payload.embedding_model),
    // `slow` is the EMBEDDING estimate only, never the whole answer.
    tag(`~${payload.ingest_minutes.toFixed(1)} min to ingest`, payload.slow),
    tag(payload.name),
  ];

  const id = document.createElement("code");
  id.className = "artifact-id";
  id.textContent = payload.artifact_id;
  id.title = "Artifact id - what a question is asked about";
  parts.push(id);

  return parts;
}

/** What can be asked, from what is stored: nothing, one side, or both. */
function refreshReady() {
  const have = ["A", "B"].filter((side) => stored[side]);
  // Any number of sides is a valid question. Only a file still being read, or a
  // question already on its way, holds the button.
  const reading = document.querySelector('.slot[data-status="working"]') !== null;
  compareButton.disabled = reading || waiting;

  if (have.length === 2) {
    ready.textContent = "Both sides are stored. Ask as many questions as you like.";
  } else if (have.length === 1) {
    // The agent says what is missing, rather than failing silently.
    const missing = stored.A ? "B" : "A";
    ready.textContent = `Ask about this one, or add side ${missing} to compare.`;
  } else {
    ready.textContent =
      "No file yet. You can still ask a question, or add files to ask about them.";
  }

  if (!questionTouched) questionBox.value = DEFAULT_QUESTION[have.length];
}

ask.addEventListener("submit", async (event) => {
  event.preventDefault();

  const question = document.getElementById("question").value.trim();
  if (!question) {
    // Never send empty: the question is also the retrieval query.
    showFailure({
      code: "invalid_question",
      message: "Ask something - this text is also the search query.",
      request_id: "-",
    });
    return;
  }

  hide(result);
  hide(failure);
  waiting = true;
  compareButton.disabled = true;
  status.hidden = false;
  document.getElementById("status-text").textContent =
    "Waiting on the model. A full report usually takes about a minute, and the " +
    "chain may fall through several tiers before one answers.";

  try {
    const response = await fetch(COMPARE, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        a: stored.A ? stored.A.artifact_id : null,
        b: stored.B ? stored.B.artifact_id : null,
        question,
        thread_id: localStorage.getItem(THREAD_KEY),
      }),
    });
    const payload = await response.json();
    if (response.ok) showReport(payload);
    else showFailure(payload.error);
  } catch (error) {
    showFailure({ code: "network_error", message: String(error), request_id: "-" });
  } finally {
    status.hidden = true;
    waiting = false;
    refreshReady();
  }
});

function showReport(body) {
  localStorage.setItem(THREAD_KEY, body.thread_id);
  const meta = document.getElementById("meta");
  meta.replaceChildren(
    tag(`${body.model} · tier ${body.tier}`),
    // n of m, where m is what the artifact HOLDS. On the search path these
    // differ, and saying so is the difference between "I read 25 of 8,333
    // parts" and a silent claim to have read the whole file. Only the sides
    // that really had a file are listed: a chat question has none.
    ...Object.entries(body.chunks).map(([side, counts]) =>
      tag(coverage(side, counts), counts.sent < counts.total)
    ),
    // MAX_TOKENS means the report was CUT and looks complete otherwise.
    tag(body.finish_reason, body.finish_reason !== "STOP")
  );

  for (const attempt of body.attempts) {
    meta.append(tag(`${attempt.model} failed`, true));
  }

  document.getElementById("answer").textContent = body.answer;

  const cited = body.citations;
  document.getElementById("citations-summary").textContent =
    `${cited.resolved} of ${cited.written} citations point at a real line`;
  document.getElementById("citations").replaceChildren(
    ...cited.resolved_list.map((one) => {
      const item = document.createElement("li");
      const where = document.createElement("code");
      where.textContent = `${one.source}:${one.line}${one.unique ? "" : " (not unique)"}`;
      item.append(where, ` ${one.text.trim()}`);
      return item;
    })
  );

  result.hidden = false;
}

function coverage(side, counts) {
  const whole = counts.sent === counts.total ? "" : " searched";
  return `${side}: ${counts.sent}/${counts.total} chunks${whole}`;
}

function showFailure(error) {
  document.getElementById("failure-code").textContent = error.code;
  document.getElementById("failure-message").textContent = error.message;
  document.getElementById("failure-id").textContent = error.request_id;
  document.getElementById("failure-attempts").replaceChildren(
    ...(error.attempts || []).map((attempt) => {
      const item = document.createElement("li");
      item.textContent = `tier ${attempt.tier} ${attempt.model}: ${attempt.error}`;
      return item;
    })
  );

  failure.hidden = false;
}

function hide(section) {
  section.hidden = true;
}

function tag(text, warn = false) {
  const span = document.createElement("span");
  span.className = warn ? "tag warn" : "tag";
  span.textContent = text;
  return span;
}
