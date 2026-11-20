(() => {
  let ids = [];
  let running = false;
  let pendingPlan = null;
  let revision = 0;

  const note = (message) => { $("guided-message").textContent = message; };
  const chosenModels = () => {
    const checked = new Set([...document.querySelectorAll("[data-model]:checked")].map((x) => x.dataset.model));
    const distinct = new Set();
    return savedModels.filter((model) => {
      if (checked.size && !checked.has(model.id)) return false;
      const identity = JSON.stringify([model.kind, (model.base_url || "").replace(/\/+$/, ""), model.model, model.hf_id]);
      if (distinct.has(identity)) return false;
      distinct.add(identity);
      return true;
    }).map((model) => model.id);
  };

  function updateInputs() {
    revision++;
    pendingPlan = null;
    const groq = $("guided-mode").value === "groq";
    $("guided-credential").hidden = !groq;
    $("guided-saved-note").hidden = groq;
    $("guided-plan").disabled = running || scoredCount() < 2;
    $("guided-start").hidden = true;
    if (!running) note(scoredCount() < 2 ? "Load at least two questions with correct answers." : "Preview the test before starting it.");
  }

  const scoredCount = () => items.filter((item) => ["A", "B", "C", "D"].includes(item.gold)).length;
  window.addEventListener("guided-input-change", updateInputs);
  for (const field of ["guided-mode", "guided-limit"]) $(field).addEventListener("change", updateInputs);
  $("guided-plan").addEventListener("click", async () => {
    const stamp = ++revision;
    const groq = $("guided-mode").value === "groq";
    const modelIds = groq ? [] : chosenModels();
    if (!groq && modelIds.length < 2) return note("Connect at least two different models in the Test lab, or use one Groq key above.");
    if (!groq && modelIds.length > 3 && document.querySelector("[data-model]:checked")) return note("Choose two or three saved models.");
    const body = { items, limit: Number($("guided-limit").value) };
    $("guided-plan").disabled = true;
    $("guided-start").hidden = true;
    note("Preparing matching questions and counting requests…");
    try {
      const plan = await api("/guided/plan", { method: "POST", body });
      if (stamp !== revision) return;
      const count = groq ? 2 : Math.min(modelIds.length, 3);
      pendingPlan = { ...body, ...(groq ? {} : { model_ids: modelIds.slice(0, 3) }) };
      const destinations = groq ? "Questions are sent to Groq." : "Questions are sent to the selected model endpoints.";
      const modelNames = groq ? "GPT-OSS 20B and 120B" : modelIds.slice(0, 3).map((id) => savedModels.find((m) => m.id === id)?.label || id).join(", ");
      const downloads = !groq && modelIds.slice(0, 3).some((id) => savedModels.some((m) => m.id === id && m.kind === "hf"))
        ? " Selected Hugging Face models may download weights when first used." : "";
      note(`${plan.questions} of ${plan.available} scored questions on ${modelNames}. About ${plan.calls_per_model * count} model requests before retries. ${destinations} Provider usage charges may apply.${downloads}`);
      $("guided-start").hidden = false;
    } catch (e) { if (stamp === revision) note(e.message); }
    finally { if (stamp === revision) $("guided-plan").disabled = false; }
  });

  $("guided-start").addEventListener("click", async () => {
    if (running || !pendingPlan) return;
    const body = { ...pendingPlan };
    if ($("guided-mode").value === "groq") {
      body.groq_key = $("guided-key").value.trim();
      if (!body.groq_key) return note("Enter a Groq API key to start the comparison.");
    }
    running = true;
    updateInputs();
    note("Starting model runs…");
    try {
      const started = await api("/guided/start", { method: "POST", body });
      $("guided-key").value = "";
      ids = started.ids;
      const url = new URL(location.href);
      url.searchParams.delete("runs");
      url.searchParams.set("guided", ids.join(","));
      history.replaceState({}, "", url);
      $("guided-stop").disabled = false;
      $("guided-stop").hidden = false;
      refresh();
    } catch (e) {
      running = false;
      updateInputs();
      note(e.message);
    }
  });

  $("guided-stop").addEventListener("click", async () => {
    $("guided-stop").disabled = true;
    try {
      await Promise.all(ids.map((id) => api(`/runs/${id}/cancel`, { method: "POST", body: {} })));
      note("Stopping after requests already in progress finish…");
    } catch (e) { $("guided-stop").disabled = false; note(e.message); }
  });

  const show = (v, unit = "%") => v == null ? "—" : `${v}${unit}`;
  const leaders = (data, ids) => ids.map((id) => esc(data.entries.find((e) => e.id === id)?.label)).join(" and ");

  function render(data) {
    const complete = data.entries.filter((e) => e.scores);
    const conversion = data.entries.find((e) => data.converted_leaders.includes(e.id) && e.scores.improved);
    const raw = leaders(data, data.raw_leaders);
    let summary = "";
    if (data.finished) {
      if (!raw) summary = "<p>A recommendation needs at least two fully scored model runs. Check the individual reports for failures and try again.</p>";
      else {
        summary = `<h4>${data.raw_leaders.length > 1 ? "Best without conversion (tie)" : "Best without conversion"} · ${raw}</h4>
          <p>${data.plan.questions} scored questions. ${data.plan.questions < 30 ? "This is a small trial. Check the result on a larger, separate question set before adopting it." : "Confirm the choice on a separate question set before adopting it."}</p>`;
        if (complete.length < data.entries.length) summary += "<p>Ranking covers only the models that finished.</p>";
        if (data.conversion_beats_raw && conversion) {
          const score = conversion.scores;
          summary += `<h4>Best workflow to trial · ${leaders(data, data.converted_leaders)} with conversion</h4>
            <p>For ${esc(conversion.label)}, conversion moved the score from ${score.raw_score}% to ${score.converted_score}%. It corrected ${score.fixed} input cases and worsened ${score.harmed}. <a href="#fix-input">Try the same converter on your input</a>. Review the converted text before sending it to the model.</p>`;
        } else {
          summary += "<p><b>Next step.</b> Keep Roman input with the top model for this trial. The tested conversion did not improve on the best raw score. Collect real spelling failures and check them on a fresh set before changing your input flow.</p>";
        }
        if (complete.every((e) => Math.max(e.scores.raw_score, e.scores.converted_score) <= 25)) {
          summary += "<p><b>Low accuracy across the trial.</b> Every workflow scored at or below the 25% benchmark for random guessing on four options. Try other models or check the question set before choosing a workflow.</p>";
        }
      }
    }
    $("guided-results").hidden = false;
    $("guided-results").innerHTML = `${summary}<div class="scroll"><table>
      <thead><tr><th>Model</th><th>Progress</th><th>Original Roman</th><th>Changed spelling</th><th>Raw score</th><th>Converted score</th><th>Detailed report</th></tr></thead>
      <tbody>${data.entries.map(({ id, label, status, done, total, scores, detail }) => `<tr><td>${esc(label)}</td><td>${esc(status)} · ${done}/${total}${detail ? `<small class="table-sub">${esc(detail)}</small>` : ""}</td>
        <td>${show(scores?.roman_accuracy)}</td><td>${show(scores?.respelling_accuracy)}</td>
        <td>${show(scores?.raw_score)}</td><td>${show(scores?.converted_score)}${scores ? `<small class="table-sub">${scores.gain > 0 ? "+" : ""}${scores.gain} pts · ${scores.fixed} corrected · ${scores.harmed} worsened</small>` : ""}</td>
        <td><a href="/#/run/${encodeURIComponent(id)}">Open report</a></td></tr>`).join("")}</tbody></table></div>
      <p class="muted">Each question has equal weight. The raw score includes its original Roman text and any distinct generated respellings. The converted score uses those same inputs after conversion. Missing model answers count as incorrect. ${data.plan.with_changed_spelling} questions had changed spellings. ${data.plan.generated_roman} used Roman text generated by Vartani.</p>
      ${complete.filter((e) => e.scores.examples.length).map((e) => `<details class="fingerprint-details"><summary>${esc(e.label)} · before and after examples</summary>
        ${e.scores.examples.map((x) => `<div class="case-example"><b>${x.helped ? "Corrected" : "Worsened"}</b> · ${esc(names[x.lang])} · answer ${esc(x.before_answer || "none")} → ${esc(x.after_answer || "none")} · key ${esc(x.gold)}
          <p>${esc(x.before.question)}<br />${esc(x.after.question)}</p>
          <details><summary>Show passage and options</summary><p>${esc(x.before.passage)}<br />${esc(x.after.passage)}</p><ol type="A">${x.before.options.map((option, i) => `<li>${esc(option)} → ${esc(x.after.options[i])}</li>`).join("")}</ol></details></div>`).join("")}
        </details>`).join("")}`;
  }

  async function refresh() {
    try {
      const data = await api(`/guided/results?ids=${encodeURIComponent(ids.join(","))}`);
      render(data);
      if (!data.finished) return setTimeout(refresh, 1700);
      running = false;
      $("guided-stop").hidden = true;
      updateInputs();
      note("Comparison finished.");
    } catch (e) {
      running = false;
      $("guided-stop").hidden = true;
      updateInputs();
      note(`${e.message} Reload this page to reconnect to the results.`);
    }
  }

  $("fix-convert").addEventListener("click", async () => {
    const text = $("fix-text").value.trim();
    $("fix-output").value = "";
    if (!text) { $("fix-message").textContent = "Enter Roman text to convert."; return; }
    $("fix-convert").disabled = true;
    try {
      const out = await api("/bridge", { method: "POST", body: { text, lang: $("fix-language").value } });
      $("fix-output").value = out.native;
      $("fix-message").textContent = "Review the converted text, then copy it into the tool where you use your model.";
    } catch (e) { $("fix-message").textContent = e.message; }
    finally { $("fix-convert").disabled = false; }
  });

  const remembered = new URLSearchParams(location.search).get("guided")?.split(",");
  if (remembered?.length >= 2 && remembered.every((id) => /^[a-f0-9]{10}$/.test(id))) {
    ids = remembered;
    running = true;
    $("guided-stop").hidden = false;
    refresh();
  }
  updateInputs();
})();
