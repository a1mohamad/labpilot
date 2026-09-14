"use strict";

// TWO DOORS. Ingest is paid ONCE per artifact; a question sends only ids.
//
// Under the old single endpoint every question re-uploaded, re-chunked and
// re-embedded both sides - about fifteen minutes per question for a large
// repository. That is why this file uploads on selection and then never sends
// a file again.
const ARTIFACTS = "/api/v1/artifacts";
const COMPARE = "/api/v1/compare";

/** What each slot currently holds, once the server has stored it. */
const stored = { A: null, B: null };

const ask = document.getElementById("ask");
const compareButton = document.getElementById("compare");
const ready = document.getElementById("ready");
const status = document.getElementById("status");
const result = document.getElementById("result");
const failure = document.getElementById("failure");

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
  slot.classList.add("busy");
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
      state.className = "state bad";
      state.textContent = `${payload.error.code}: ${payload.error.message}`;
      return;
    }

    stored[side] = payload;
    state.className = "state good";
    state.replaceChildren(...describe(payload));
  } catch (error) {
    state.className = "state bad";
    state.textContent = String(error);
  } finally {
    slot.classList.remove("busy");
    refreshReady();
  }
}

/** What came back, in the order a reader cares about. */
function describe(payload) {
  const parts = [
    tag(`${payload.chunks} chunks`),
    tag(payload.embedding_model),
    // `slow` is the EMBEDDING estimate only, never the whole answer.
    tag(`~${payload.embedding_minutes.toFixed(1)} min to embed`, payload.slow),
    tag(payload.name),
  ];

  const id = document.createElement("code");
  id.className = "artifact-id";
  id.textContent = payload.artifact_id;
  id.title = "Artifact id - what a question is asked about";
  parts.push(id);

  return parts;
}

function refreshReady() {
  const have = ["A", "B"].filter((side) => stored[side]);
  compareButton.disabled = have.length !== 2;

  if (have.length === 2) {
    ready.textContent = "Both sides are stored. Ask as many questions as you like.";
  } else if (have.length === 1) {
    // The agent asks for what it is missing, rather than failing silently.
    const missing = stored.A ? "B" : "A";
    ready.textContent = `Add side ${missing} to compare.`;
  } else {
    ready.textContent = "Add both sides to compare.";
  }
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
  compareButton.disabled = true;
  status.hidden = false;
  status.textContent =
    "Waiting on the model. A full report usually takes about a minute, and the " +
    "chain may fall through several tiers before one answers.";

  try {
    const response = await fetch(COMPARE, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        a: stored.A.artifact_id,
        b: stored.B.artifact_id,
        question,
      }),
    });
    const payload = await response.json();
    if (response.ok) showReport(payload);
    else showFailure(payload.error);
  } catch (error) {
    showFailure({ code: "network_error", message: String(error), request_id: "-" });
  } finally {
    status.hidden = true;
    refreshReady();
  }
});

function showReport(body) {
  const meta = document.getElementById("meta");
  meta.replaceChildren(
    tag(`${body.model} · tier ${body.tier}`),
    // n of m, where m is what the artifact HOLDS. On the search path these
    // differ, and saying so is the difference between "I read 25 of 8,333
    // parts" and a silent claim to have read the whole file.
    tag(coverage("A", body.chunks.A), body.chunks.A.sent < body.chunks.A.total),
    tag(coverage("B", body.chunks.B), body.chunks.B.sent < body.chunks.B.total),
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
