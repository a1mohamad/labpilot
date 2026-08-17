"use strict";

const ENDPOINT = "/api/v1/compare";

const form = document.getElementById("compare");
const status = document.getElementById("status");
const result = document.getElementById("result");
const failure = document.getElementById("failure");

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const question = form.question.value.trim();
  if (!question) {
    // Never send empty: the question is also the retrieval query.
    show(failure, { code: "invalid_question", message: "Ask something.", request_id: "-" });
    return;
  }

  hide(result);
  hide(failure);
  form.querySelector("button").disabled = true;
  status.hidden = false;
  status.textContent =
    "Waiting on the model. A full report usually takes about a minute, and the " +
    "chain may fall through several tiers before one answers.";

  try {
    const response = await fetch(ENDPOINT, { method: "POST", body: new FormData(form) });
    const body = await response.json();
    response.ok ? showReport(body) : show(failure, body.error);
  } catch (error) {
    show(failure, {
      code: "network_error",
      message: String(error),
      request_id: "-",
    });
  } finally {
    form.querySelector("button").disabled = false;
    status.hidden = true;
  }
});

function showReport(body) {
  const meta = document.getElementById("meta");
  meta.replaceChildren(
    tag(`${body.model} · tier ${body.tier}`),
    tag(`A: ${body.chunks.A.sent}/${body.chunks.A.total} chunks`),
    tag(`B: ${body.chunks.B.sent}/${body.chunks.B.total} chunks`),
    // MAX_TOKENS means the report was cut and looks complete otherwise.
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

function show(section, error) {
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

  section.hidden = false;
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
