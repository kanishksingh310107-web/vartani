(() => {
  let runId = null;
  let rows = [];
  let approved = new Set();
  let index = 0;
  let requesting = false;
  let dataset = items;
  let previewedUpload = false;
  const validRun = (id) => /^[a-f0-9]{10}$/.test(id);
  const message = (text) => { $("fix-dataset-message").textContent = text; };

  function buttons() {
    $("fix-preview-upload").disabled = requesting || !items.length;
    $("fix-preview-run").hidden = !runId;
    $("fix-preview-run").disabled = requesting;
  }

  function useRun(id) {
    if (validRun(id)) runId = id;
    buttons();
  }
  useRun(new URLSearchParams(location.search).get("fix_run") || "");
  if (runId) message("Review the questions used in this run, or upload another dataset.");
  $("guided-results").addEventListener("click", (event) => {
    const link = event.target.closest("[data-fix-run]");
    if (!link) return;
    useRun(link.dataset.fixRun);
    const url = new URL(location.href);
    url.searchParams.set("fix_run", runId);
    history.replaceState({}, "", url);
    message("Preview your loaded dataset or the questions from the recommended model’s run.");
  });

  window.addEventListener("guided-input-change", () => {
    if (items !== dataset) {
      dataset = items;
      if (previewedUpload) {
        rows = [];
        approved.clear();
        $("fix-review").hidden = true;
      }
      if (!requesting) message("Preview your loaded dataset to review the changes.");
    }
    buttons();
  });

  function fields(row, title, suffix = "") {
    return `<h4>${title}</h4><pre>${esc(row["passage" + suffix])}</pre>
      <p><b>${esc(row["question" + suffix])}</b></p><ol type="A">
      ${row["options" + suffix].map((v) => `<li>${esc(v)}</li>`).join("")}</ol>`;
  }

  function render() {
    const record = rows[index];
    if (!record) return;
    const { original, draft, reason } = record;
    const language = names[original.lang] || original.lang;
    $("fix-position").textContent = `${index + 1} / ${rows.length} · ${language} · Key ${original.answer || "unscored"}`;
    $("fix-prev").disabled = index === 0;
    $("fix-next").disabled = index === rows.length - 1;
    $("fix-jump").value = index + 1;
    $("fix-jump").max = rows.length;
    $("fix-original").innerHTML = fields(original, "Original input", original.question_roman ? "_roman" : "");
    $("fix-draft").innerHTML = draft ? fields(draft, "Proposed native text") : `<p>${esc(reason)}</p>`;
    $("fix-approve").disabled = !draft;
    $("fix-approve").checked = approved.has(index);
    $("fix-approval-count").textContent = `${approved.size} approved. All other rows use their original text.`;
    $("fix-export").disabled = !approved.size;
  }

  async function preview(fromRun) {
    if (requesting) return;
    const selectedDataset = items;
    requesting = true;
    buttons();
    $("fix-review").hidden = true;
    message("Preparing a local conversion preview…");
    try {
      const result = fromRun ? await api(`/runs/${runId}/fix-preview`)
        : await api("/guided/fix-preview", { method: "POST", body: { items: selectedDataset } });
      if (!fromRun && items !== selectedDataset) return message("The loaded dataset changed. Preview it again.");
      rows = result;
      previewedUpload = !fromRun;
      index = 0;
      approved = new Set();
      const count = rows.filter((row) => row.draft).length;
      message(`${count} of ${rows.length} questions have a proposed conversion to review.`);
      $("fix-review").hidden = false;
      render();
    } catch (error) { message(error.message); }
    finally { requesting = false; buttons(); }
  }

  $("fix-preview-upload").addEventListener("click", () => preview(false));
  $("fix-preview-run").addEventListener("click", () => preview(true));
  $("fix-prev").addEventListener("click", () => { index--; render(); });
  $("fix-next").addEventListener("click", () => { index++; render(); });
  $("fix-jump").addEventListener("change", () => {
    const number = Number($("fix-jump").value);
    if (Number.isInteger(number) && number > 0 && number <= rows.length) index = number - 1;
    render();
  });
  $("fix-approve").addEventListener("change", () => {
    if ($("fix-approve").checked && rows[index]?.draft) approved.add(index);
    else approved.delete(index);
    render();
  });
  $("fix-export").addEventListener("click", () => {
    if (!approved.size) return;
    const content = rows.map(({ original, draft }, i) => JSON.stringify(approved.has(i) ? draft : original)).join("\n") + "\n";
    const url = URL.createObjectURL(new Blob([content], { type: "application/x-ndjson;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "vartani-reviewed-conversion.jsonl";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  buttons();
})();
