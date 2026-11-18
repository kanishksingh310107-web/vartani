(() => {
  const addHuggingFaceTokenField = (form) => {
    if (!window.vartaniTokenFetchPatched) {
      const originalFetch = window.fetch.bind(window);
      window.fetch = (input, init = {}) => {
        const url = typeof input === "string" ? input : input?.url || "";
        if (url.endsWith("/api/models") && init.method === "POST" && init.body) {
          const token = document.querySelector("[data-hf-token='true']")?.value?.trim();
          if (token) {
            try { init = { ...init, body: JSON.stringify({ ...JSON.parse(init.body), hf_token: token }) }; }
            catch { /* send the original request if it is not JSON */ }
          }
        }
        return originalFetch(input, init);
      };
      window.vartaniTokenFetchPatched = true;
    }
    if (form.querySelector("[data-hf-token='true']")) return;
    const repo = [...form.querySelectorAll("label")].find((label) => label.textContent.includes("Hugging Face model ID"));
    if (!repo) return;
    const label = document.createElement("label");
    label.textContent = "Hugging Face read token (private or gated models only)";
    const input = document.createElement("input");
    input.type = "password";
    input.autocomplete = "new-password";
    input.placeholder = "Leave blank to keep a saved token";
    input.dataset.hfToken = "true";
    label.appendChild(input);
    repo.insertAdjacentElement("afterend", label);
  };
  const addLink = () => {
    const links = document.querySelector(".links");
    if (!links || links.querySelector('[data-feature-link="true"]')) return;
    const a = document.createElement("a");
    a.href = "/features.html";
    a.textContent = "Compare & ship";
    a.dataset.featureLink = "true";
    links.appendChild(a);
  };
  const addSpeechLink = () => {
    const links = document.querySelector(".links");
    if (!links || links.querySelector('[data-speech-link="true"]')) return;
    const a = document.createElement("a");
    a.href = "/speech.html";
    a.textContent = "Speech check";
    a.dataset.speechLink = "true";
    links.appendChild(a);
  };
  const explainRunButton = () => {
    const runbar = document.querySelector(".runbar");
    const button = runbar?.querySelector("button.btn.primary");
    if (!runbar || !button) return;
    let note = runbar.parentElement.querySelector("[data-run-hint='true']");
    const modelCard = [...document.querySelectorAll(".card")].find((card) => card.querySelector("h3")?.textContent.includes("Model to test"));
    const failed = modelCard?.querySelector(".err-line");
    const selected = document.querySelector(".saved-row.on")?.textContent || "";
    // React already owns the Run button's readiness state. Do not add a second
    // DOM-based lock here: closing a successful test message used to leave the
    // button disabled even though the model had passed and was selected.
    if (!button.disabled) { note?.remove(); return; }
    if (!note) {
      note = document.createElement("p");
      note.dataset.runHint = "true";
      note.className = "muted";
      runbar.insertAdjacentElement("afterend", note);
    }
    const plan = runbar.querySelector(".plan")?.textContent || "";
    if (/choose a test set/i.test(plan)) {
      const message = "Run test is locked because no questions are loaded. In step 1, click a starter set or upload a CSV / JSONL file.";
      if (note.textContent !== message) note.textContent = message;
      return;
    }
    const message = failed
      ? "The last model connection test failed. Fix the message above, then click Save and test connection again."
      : !selected
        ? "Choose or add a model above, then click “select & test” or “Save and test connection”."
        : "The model is not selected for this page yet. Click “select & test” beside it, then try Run test again.";
    if (note.textContent !== message) note.textContent = message;
  };
  const explainModelLoad = () => {
    const form = [...document.querySelectorAll(".form")].find((node) =>
      [...node.querySelectorAll("button")].some((button) => button.textContent.includes("Save and test connection"))
    );
    if (!form) return;
    addHuggingFaceTokenField(form);
    let note = form.querySelector("[data-model-load-hint='true']");
    if (!note) {
      note = document.createElement("small");
      note.dataset.modelLoadHint = "true";
      note.className = "muted";
      form.appendChild(note);
    }
    const isHuggingFace = [...form.querySelectorAll("label")].some((label) => label.textContent.includes("Hugging Face model ID"));
    const gatedHint = [...form.querySelectorAll("p.muted")].find((item) => item.textContent.includes("Gated model:"));
    if (gatedHint) gatedHint.textContent = "This model is access-restricted. Accept its terms and wait for approval on Hugging Face, then use a read token above. Choose public Qwen2.5-3B-Instruct to continue without approval.";
    const message = isHuggingFace
      ? "Missing Hugging Face model files download on first test. For gated models, accept the terms and wait for approval, then add a read token above. If you do not have access, use public Qwen2.5-3B-Instruct."
      : "Save and test sends a small question to this model. Local model servers must be running; hosted models need a valid API key.";
    if (note.textContent !== message) note.textContent = message;
    const button = [...form.querySelectorAll("button")].find((item) => item.textContent.includes("Testing…"));
    if (button) button.textContent = "Loading model and testing…";
  };
  const refresh = () => { addLink(); addSpeechLink(); explainRunButton(); explainModelLoad(); };
  new MutationObserver(refresh).observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ["disabled", "class"] });
  refresh();
})();
