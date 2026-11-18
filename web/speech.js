(() => {
  const $ = (id) => document.getElementById(id);
  const els = {set:$("speech-set"), question:$("speech-question"), preview:$("speech-question-preview"), size:$("speech-size"), audio:$("speech-audio"), transcribe:$("speech-transcribe"), transcribeStatus:$("speech-transcribe-status"), transcript:$("speech-transcript"), model:$("speech-model"), testModel:$("speech-test-model"), modelStatus:$("speech-model-status"), runName:$("speech-run-name"), run:$("speech-run"), runStatus:$("speech-run-status"), output:$("speech-output")};
  let items = [], models = [], modelPassed = false, activeRun = null, pollTimer = null;
  let currentAudio = null, recorder = null, micStream = null, audioChunks = [], recordTimer = null;
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  async function api(path, options={}) {
    const r = await fetch("/api"+path, options);
    let body; try { body = await r.json(); } catch { body = {}; }
    if (!r.ok) throw new Error(body.detail || r.statusText || "Request failed");
    return body;
  }
  const selectedItem = () => items.find((x) => String(x.id) === els.question.value);
  function refreshButtons() {
    els.transcribe.disabled = !(selectedItem() && currentAudio);
    els.testModel.disabled = !els.model.value;
    els.run.disabled = !(selectedItem() && els.transcript.value.trim() && modelPassed) || Boolean(activeRun && ["queued","running"].includes(activeRun.status));
  }
  function showQuestion() {
    const item = selectedItem();
    if (!item) { els.preview.textContent = "Choose a starter set and question."; refreshButtons(); return; }
    const text = item.roman || item.native;
    els.preview.innerHTML = `<b>Speak this question only</b><p>${esc(text?.question)}</p><small>Correct answer: ${esc(item.gold || "not set")} · ${esc(item.lang)}</small>`;
    refreshButtons();
  }
  async function loadSets() {
    try {
      const sets = await api("/samples");
      els.set.innerHTML = '<option value="">Choose a starter set</option>'+sets.map((s) => `<option value="${esc(s.id)}">${esc(s.title)} (${s.n} questions)</option>`).join("");
    } catch(e) { els.set.innerHTML = '<option value="">Could not load starter sets</option>'; els.transcribeStatus.textContent=e.message; }
  }
  async function loadSet(id) {
    items=[]; els.question.innerHTML='<option value="">Loading questions…</option>'; els.question.disabled=true; showQuestion();
    if (!id) return;
    try {
      const data=await api(`/samples/${encodeURIComponent(id)}`); items=data.items;
      els.question.innerHTML=items.map((it,i)=>`<option value="${esc(it.id)}">Question ${i+1}: ${esc((it.roman||it.native)?.question?.slice(0,72))}</option>`).join("");
      els.question.disabled=false; els.transcript.value=""; showQuestion();
    } catch(e) { els.question.innerHTML='<option value="">Could not load questions</option>'; els.transcribeStatus.textContent=e.message; }
  }
  async function loadModels() {
    try {
      const data=await api("/models"); models=data.saved;
      els.model.innerHTML='<option value="">Choose a saved and tested model</option>'+models.map((m)=>`<option value="${esc(m.id)}">${esc(m.label)} — ${esc(m.kind==="hf"?m.hf_id:m.model)}</option>`).join("");
      if (!models.length) els.modelStatus.textContent="Save a model in Test lab first.";
    } catch(e) { els.modelStatus.textContent=e.message; }
  }
  els.set.addEventListener("change",()=>loadSet(els.set.value));
  els.question.addEventListener("change",()=>{els.transcript.value=""; showQuestion();});
  els.audio.addEventListener("change",()=>{currentAudio=els.audio.files[0]||null; $("speech-record-status").textContent=currentAudio?`Selected ${currentAudio.name}`:"";refreshButtons();});
  $("speech-record").addEventListener("click",async()=>{
    if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder){$("speech-record-status").textContent="Microphone recording is not supported in this browser. Upload an audio clip instead.";return;}
    try{
      micStream=await navigator.mediaDevices.getUserMedia({audio:true});audioChunks=[];recorder=new MediaRecorder(micStream);
      recorder.ondataavailable=(e)=>{if(e.data.size)audioChunks.push(e.data);};
      recorder.onstop=()=>{const blob=new Blob(audioChunks,{type:recorder.mimeType||"audio/webm"});currentAudio=new File([blob],"vartani-question.webm",{type:blob.type});micStream?.getTracks().forEach((t)=>t.stop());micStream=null;$("speech-stop-record").hidden=true;$("speech-record").disabled=false;$("speech-record-status").textContent=`Recording ready (${Math.ceil(blob.size/1024)} KB).`;refreshButtons();};
      recorder.start();$("speech-record").disabled=true;$("speech-stop-record").hidden=false;$("speech-record-status").textContent="Recording… speak the question, then stop.";
      recordTimer=setTimeout(()=>{if(recorder?.state==="recording")recorder.stop();},30000);
    }catch(e){$("speech-record-status").textContent=`Microphone unavailable: ${e.message}`;micStream?.getTracks().forEach((t)=>t.stop());}
  });
  $("speech-stop-record").addEventListener("click",()=>{clearTimeout(recordTimer);if(recorder?.state==="recording")recorder.stop();});
  els.model.addEventListener("change",()=>{modelPassed=false; els.modelStatus.textContent="Test this connection before running."; refreshButtons();});
  els.transcript.addEventListener("input",refreshButtons);
  els.transcribe.addEventListener("click",async()=>{
    const file=currentAudio, item=selectedItem(); if(!file||!item)return;
    if(file.size>25*1024*1024){els.transcribeStatus.textContent="Audio must be under 25 MB.";return;}
    els.transcribe.disabled=true; els.transcribe.textContent="Downloading model if needed, then transcribing…";
    els.transcribeStatus.textContent="This runs locally. First use downloads Whisper model weights and can take a few minutes.";
    try {
      const form=new FormData(); form.append("file",file); form.append("lang",item.lang); form.append("model_size",els.size.value);
      const result=await api("/speech/transcribe",{method:"POST",body:form});
      els.transcript.value=result.text; els.transcript.disabled=false;
      els.transcribeStatus.textContent=`${result.model} · ${result.duration}s audio · language ${result.language}. Review the transcript before running.`;
    } catch(e) { els.transcribeStatus.textContent=e.message; }
    finally { els.transcribe.textContent="Transcribe audio"; refreshButtons(); }
  });
  els.testModel.addEventListener("click",async()=>{
    if(!els.model.value)return; modelPassed=false; els.testModel.disabled=true; els.testModel.textContent="Testing…"; els.modelStatus.textContent="Checking the saved connection…";
    try {
      const r=await api("/models/test",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:els.model.value})});
      if(!r.ok)throw new Error(r.error||"The model did not return an answer.");
      modelPassed=true; els.modelStatus.textContent=`Connected · answered ${r.letter} in ${r.ms} ms${r.margin_available?"":" · no confidence margins"}`;
    } catch(e) { els.modelStatus.textContent=e.message; }
    finally { els.testModel.textContent="Test model connection"; refreshButtons(); }
  });
  function renderReport(report, row) {
    const labels={roman:"Typed Roman baseline",asr:"Raw speech transcript",asr_roman:"ASR → Romanized"};
    const cards=Object.entries(labels).map(([key,label])=>{const a=report.accuracy?.[key]; const ans=row?.answers?.[key]||"—"; return `<div class="card"><small>${label}</small><h3>${ans}</h3><p class="muted">${a?`${a.acc}% accuracy · ${a.k}/${a.n} correct`:"No scored answer"}</p><p class="speech-result">${esc(row?.conditions?.[key]?.question||"")}</p></div>`;}).join("");
    els.output.innerHTML=`<h3>Speech comparison result</h3><p class="muted">This is one recorded question. Treat it as a pipeline check, not a model accuracy estimate.</p><div class="speech-grid">${cards}</div><p><a class="btn" href="/#/run/${encodeURIComponent(activeRun.id)}">Open full Vartani report</a></p>`;
  }
  async function poll() {
    if(!activeRun)return;
    try {
      const m=await api(`/runs/${activeRun.id}`); activeRun=m;
      const pct=m.total_calls?Math.round(100*m.done_calls/m.total_calls):0;
      els.runStatus.innerHTML=`<p><b class="status ${esc(m.status)}">${esc(m.status)}</b> · ${m.done_items}/${m.n_items} questions · ${m.done_calls}/${m.total_calls} calls</p><div class="speech-progress"><i style="width:${pct}%"></i></div>${m.error?`<p class="err-line">${esc(m.error)}</p>`:""}`;
      if(["queued","running"].includes(m.status)){els.run.disabled=true; els.run.textContent="Running speech check…"; pollTimer=setTimeout(poll,1000); return;}
      els.run.textContent=m.status==="done"?"Run another speech check":"Retry speech check";
      if(m.status==="done"){
        const [r, rows]=await Promise.all([api(`/runs/${m.id}/report`),api(`/runs/${m.id}/items`)]);
        renderReport(r.report,rows[0]);
      }
    } catch(e){els.runStatus.textContent=e.message;}
    refreshButtons();
  }
  els.run.addEventListener("click",async()=>{
    const item=selectedItem(); if(!item||!modelPassed)return;
    const runItem={...item,speech_text:els.transcript.value.trim()};
    els.run.disabled=true; els.run.textContent="Starting…"; els.output.innerHTML="";
    try {
      activeRun=await api("/runs",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:els.runName.value||"Speech check",items:[runItem],model_id:els.model.value,config:{native:true,variants:0,variant_mode:"habit",typo:false,bridge:false,scan:false}})});
      poll();
    } catch(e){els.runStatus.textContent=e.message;els.run.textContent="Run speech check";refreshButtons();}
  });
  loadSets(); loadModels(); refreshButtons();
})();
