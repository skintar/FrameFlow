let project = null;
let calc = null;
let models = [];
let selectedModelId = "seedance-1-5-pro";
let jobId = null;
let pollTimer = null;
let calcTimer = null;

const $ = (sel) => document.querySelector(sel);

function rub(n) {
  const v = Number(n);
  return Number.isFinite(v) ? `${v.toFixed(2)} ₽` : "—";
}

function toast(msg, ok = false) {
  const el = $("#toast");
  el.textContent = msg;
  el.className = ok ? "toast ok" : "toast";
  el.classList.remove("hidden");
  setTimeout(() => el.classList.add("hidden"), 5000);
}

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || (await res.text()); } catch { msg = await res.text(); }
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return res.json();
}

function showStep(n) {
  document.querySelectorAll(".step").forEach((el) => el.classList.toggle("active", el.dataset.step == n));
  document.querySelectorAll(".panel").forEach((el) => el.classList.toggle("active", el.id === `step${n}`));
}

let maxProjectCharacters = 8;
let appSettings = null;

async function checkHealth() {
  const pill = $("#apiStatus");
  const onboarding = $("#onboarding");
  try {
    const h = await api("/api/health");
    if (h.provider_ok) {
      pill.textContent = `${h.provider_name} · ${h.model_count || 0} моделей`;
      pill.className = "status-pill ok";
      onboarding?.classList.add("hidden");
    } else if (h.api_key_set) {
      pill.textContent = `${h.provider_name}: ключ есть, API не отвечает`;
      pill.className = "status-pill bad";
      onboarding?.classList.remove("hidden");
    } else {
      pill.textContent = "Укажите API-ключ";
      pill.className = "status-pill bad";
      onboarding?.classList.remove("hidden");
    }

    maxProjectCharacters = h.max_project_characters || 8;
    const sel = $("#styleSelect");
    sel.innerHTML = "";
    for (const [key, label] of Object.entries(h.styles || {})) {
      const opt = document.createElement("option");
      opt.value = key;
      opt.textContent = label;
      sel.appendChild(opt);
    }
  } catch {
    pill.textContent = "FrameFlow недоступен";
    pill.className = "status-pill bad";
  }
}

function openSettings() {
  $("#settingsModal")?.classList.remove("hidden");
  loadSettingsForm();
}

function closeSettings() {
  $("#settingsModal")?.classList.add("hidden");
}

async function loadSettingsForm() {
  try {
    appSettings = await api("/api/settings");
    const sel = $("#settingsProvider");
    sel.innerHTML = "";
    for (const p of appSettings.providers || []) {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.name;
      sel.appendChild(opt);
    }
    sel.value = appSettings.active_provider || "aitunnel";
    toggleCustomFields();
    const active = (appSettings.providers || []).find((p) => p.id === sel.value);
    $("#settingsKeyHint").textContent = active?.has_key
      ? `Текущий ключ: ${active.api_key_masked} (оставьте пустым, чтобы не менять)`
      : "Вставьте ключ от выбранного сервиса";
    if (active?.id === "custom") {
      $("#settingsBaseUrl").value = active.base_url || "";
      $("#settingsModelsUrl").value = active.models_url || "";
    }
    $("#settingsApiKey").value = "";
    $("#settingsEnvPath").textContent = `Файл: ${appSettings.env_path || ".env"}`;
  } catch (err) {
    toast("Не удалось загрузить настройки: " + err.message);
  }
}

function toggleCustomFields() {
  const isCustom = $("#settingsProvider")?.value === "custom";
  $("#customProviderFields")?.classList.toggle("hidden", !isCustom);
}

async function saveSettings() {
  try {
    const body = {
      active_provider: $("#settingsProvider").value,
      api_key: $("#settingsApiKey").value,
      base_url: $("#settingsBaseUrl")?.value,
      models_url: $("#settingsModelsUrl")?.value,
    };
    appSettings = await api("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    toast("Настройки сохранены", true);
    closeSettings();
    await checkHealth();
    await loadModels(true);
  } catch (err) {
    toast("Ошибка: " + err.message);
  }
}

async function testApiConnection() {
  try {
    await saveSettings();
    const h = await api("/api/health");
    if (h.provider_ok) toast("Подключение успешно!", true);
    else toast("Ключ сохранён, но API не отвечает — проверьте URL и ключ");
  } catch (err) {
    toast("Ошибка: " + err.message);
  }
}

function renderModelGrid() {
  const grid = $("#modelGrid");
  grid.innerHTML = "";
  $("#modelCountBadge").textContent = models.length;

  if (!models.length) {
    grid.innerHTML = '<div class="model-skeleton">Модели не загружены. Нажми «↻ Модели»</div>';
    return;
  }

  for (const m of models) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = `model-card${m.id === selectedModelId ? " selected" : ""}`;
    card.dataset.modelId = m.id;
    const chainTag = m.supports_chain
      ? '<span class="tag chain">цепочка</span>'
      : '<span class="tag">без цепочки</span>';
    const tierTag = m.tier === "premium" ? '<span class="tag premium">premium</span>' : "";
    card.innerHTML = `
      <div class="name">${m.label}</div>
      <div class="provider">${m.provider || ""}</div>
      <div class="price">от ${rub(m.min_cost_rub)} · ${m.min_duration}–${m.max_duration}с</div>
      <div class="tags">${chainTag}${tierTag}</div>`;
    card.addEventListener("click", () => selectModel(m.id));
    grid.appendChild(card);
  }
}

let calcDrive = "clip"; // clip | total

function setDurationOptions(m) {
  const sel = $("#clipSeconds");
  const prev = parseInt(sel.value, 10) || 4;
  sel.innerHTML = "";
  const durations = m?.durations?.length ? m.durations : [4, 5, 6, 7, 8];
  for (const d of durations) {
    const opt = document.createElement("option");
    opt.value = d;
    opt.textContent = `${d} сек`;
    sel.appendChild(opt);
  }
  const pick = durations.includes(prev) ? prev : durations[0];
  sel.value = pick;
  $("#clipSecondsVal").textContent = `${pick} сек`;
  $("#durationHint").textContent = `доступно: ${durations.join(", ")} сек`;
}

function selectModel(id) {
  selectedModelId = id;
  $("#modelSelect").value = id;
  document.querySelectorAll(".model-card").forEach((c) => {
    c.classList.toggle("selected", c.dataset.modelId === id);
  });
  const m = models.find((x) => x.id === id);
  if (m) {
    setDurationOptions(m);
    $("#clipsHint").textContent = m.supports_chain
      ? "Клип #1 — с нуля. Далее — продолжение с последнего кадра."
      : "Модель без цепочки — каждый клип генерируется отдельно.";
  }
  updateSizeOptions();
  scheduleCalc();
}

function updateSizeOptions() {
  const m = models.find((x) => x.id === selectedModelId);
  const sizeSel = $("#sizeSelect");
  sizeSel.innerHTML = "";
  const sizes = m?.sizes?.length ? m.sizes : ["480x480"];
  const cheap = m?.cheapest_size;
  for (const s of sizes) {
    const opt = document.createElement("option");
    opt.value = s;
    opt.textContent = s === cheap ? `${s} ★ дешевле` : s;
    sizeSel.appendChild(opt);
  }
  sizeSel.value = cheap && sizes.includes(cheap) ? cheap : sizes[0];
}

function scheduleCalc() {
  clearTimeout(calcTimer);
  calcTimer = setTimeout(updateCalc, 250);
}

async function updateCalc() {
  if (!selectedModelId) return;
  const clip_count = parseInt($("#clipCount").value, 10) || 1;
  const clip_seconds = parseInt($("#clipSeconds").value, 10) || 4;
  const size = $("#sizeSelect").value;

  $("#clipSecondsVal").textContent = `${clip_seconds} сек`;

  const params = new URLSearchParams({
    model: selectedModelId,
    size,
    clip_count: String(clip_count),
    clip_seconds: String(clip_seconds),
    drive: calcDrive,
  });
  if (calcDrive === "total") {
    params.set("target_total_seconds", String(parseFloat($("#targetTotal").value) || 0));
  }

  try {
    calc = await api(`/api/calc?${params}`);
    $("#clipCount").value = calc.clip_count;

    // Синхронизируем UI без «отката» слайдера
    if (calcDrive === "clip") {
      $("#targetTotal").value = calc.total_seconds;
      if (String(calc.effective_clip_seconds) !== $("#clipSeconds").value) {
        $("#clipSeconds").value = calc.effective_clip_seconds;
      }
    } else {
      $("#clipSeconds").value = calc.effective_clip_seconds;
      $("#targetTotal").value = calc.total_seconds;
    }
    $("#clipSecondsVal").textContent = `${calc.effective_clip_seconds} сек`;

    $("#totalLabel").textContent = calc.total_label;
    $("#effectiveSecLabel").textContent = `${calc.effective_clip_seconds} сек/клип`;
    $("#costClipLabel").textContent = rub(calc.cost_per_clip_rub);
    $("#ppsLabel").textContent = rub(calc.price_per_second_rub);
    $("#costTotalLabel").textContent = rub(calc.total_cost_rub);

    const chainBadge = $("#chainBadge");
    if (calc.supports_chain) {
      chainBadge.textContent = "цепочка кадров";
      chainBadge.className = "badge ok";
    } else {
      chainBadge.textContent = "без цепочки";
      chainBadge.className = "badge warn";
    }

    const warn = $("#calcWarning");
    if (calc.warning) {
      warn.textContent = calc.warning;
      warn.classList.remove("hidden");
    } else {
      warn.classList.add("hidden");
    }
  } catch (err) {
    toast("Ошибка расчёта: " + err.message);
  }
}

async function loadModels(force = false) {
  const grid = $("#modelGrid");
  grid.innerHTML = '<div class="model-skeleton">Загрузка моделей...</div>';
  try {
    const data = await api(`/api/models${force ? "?refresh=true" : ""}`);
    models = data.models || [];
    if (!models.length) throw new Error("Пустой список моделей");
    if (!models.find((m) => m.id === selectedModelId)) {
      selectedModelId = models[0].id;
    }
    $("#modelSelect").value = selectedModelId;
    renderModelGrid();
    selectModel(selectedModelId);
  } catch (err) {
    grid.innerHTML = `<div class="model-skeleton">Ошибка: ${err.message}</div>`;
    toast("Не удалось загрузить модели: " + err.message);
  }
}

async function openProject(projectId) {
  try {
    const res = await api(`/api/projects/${projectId}`);
    project = res.project;
    calc = res.calc;
    selectedModelId = project.model || selectedModelId;
    $("#modelSelect").value = selectedModelId;
    $("#projectTitle").value = project.title || "Мой проект";
    if (project.style) $("#styleSelect").value = project.style;
    renderClips();
    showStep(2);
    toast(`Проект открыт — ${project.clips.length} клипов, тексты на месте`, true);
  } catch (err) {
    toast("Не удалось открыть: " + err.message);
  }
}

async function loadRecentProjects() {
  const box = $("#recentProjects");
  try {
    const data = await api("/api/projects/list");
    const items = data.projects || [];
    if (!items.length) {
      box.innerHTML = '<div class="muted">Пока нет проектов</div>';
      return;
    }
    box.innerHTML = '<div class="muted small" style="margin-bottom:6px">Нажми на проект — откроются все промпты</div>';
    for (const p of items) {
      const el = document.createElement("button");
      el.type = "button";
      el.className = "recent-item";
      el.innerHTML = `<strong>${p.title}</strong>${p.clips_done}/${p.clip_count} клипов · ${p.model || ""}`;
      el.addEventListener("click", () => openProject(p.project_id));
      box.appendChild(el);
    }
  } catch {
    box.innerHTML = '<div class="muted">—</div>';
  }
}

let saveTimer = null;

function schedulePromptSave() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(savePromptsQuietly, 1200);
}

async function savePromptsQuietly() {
  if (!project?.clips) return;
  syncPromptsFromUI();
  try {
    project = (await api(`/api/projects/${project.project_id}/clips`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        clips: project.clips.map((c) => ({
          index: c.index,
          prompt: c.prompt || "",
          reference_paths: c.reference_paths || [],
        })),
      }),
    })).project;
  } catch {
    /* тихо — при генерации всё равно сохранится */
  }
}

function syncPromptsFromUI() {
  if (!project?.clips) return;
  for (const clip of project.clips) {
    const ta = document.querySelector(`textarea[data-clip="${clip.index}"]`);
    if (ta) clip.prompt = ta.value;
  }
}

function applyServerProject(serverProject) {
  const prompts = {};
  if (project?.clips) {
    syncPromptsFromUI();
    for (const c of project.clips) prompts[c.index] = c.prompt;
  }
  project = serverProject;
  for (const clip of project.clips) {
    if (prompts[clip.index] !== undefined) clip.prompt = prompts[clip.index];
  }
}

function maxStoredCharacters() {
  const m = models.find((x) => x.id === (project?.model || selectedModelId));
  return m?.max_project_characters || maxProjectCharacters;
}

function maxRefsForModel() {
  return maxStoredCharacters();
}

function basename(p) {
  return String(p || "").split(/[/\\]/).pop() || "";
}

function refMediaUrl(projectId, relPath) {
  return `/media/${projectId}/${String(relPath).replace(/\\/g, "/")}`;
}

function currentModelSupportsRefs() {
  const m = models.find((x) => x.id === (project?.model || selectedModelId));
  return Boolean(m?.supports_refs);
}

function renderRefThumb(container, { url, name, onDelete }) {
  const wrap = document.createElement("div");
  wrap.className = "ref-thumb-wrap";
  const img = document.createElement("img");
  img.className = "ref-thumb";
  img.src = url;
  img.alt = name || "";
  img.title = name || "";
  wrap.appendChild(img);
  if (onDelete) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "ref-del";
    btn.textContent = "×";
    btn.title = "Удалить";
    btn.addEventListener("click", onDelete);
    wrap.appendChild(btn);
  }
  container.appendChild(wrap);
}

function renderGlobalCharacters() {
  const box = $("#globalCharacters");
  if (!box || !project) return;
  box.innerHTML = "";
  const chars = project.global_characters || [];
  if (!chars.length) {
    box.innerHTML = '<span class="muted small">Нет персонажей — добавь фото героев (можно 3 и больше)</span>';
    return;
  }
  if (chars.length > 2) {
    const note = document.createElement("p");
    note.className = "muted small collage-note";
    note.textContent = `${chars.length} персонажа → при генерации клипа #1 склеятся в один коллаж (лимит API — 2 слота)`;
    box.appendChild(note);
  }
  for (const rel of chars) {
    const name = basename(rel);
    renderRefThumb(box, {
      url: refMediaUrl(project.project_id, rel),
      name,
      onDelete: async () => {
        try {
          const res = await api(`/api/projects/${project.project_id}/characters/${encodeURIComponent(name)}`, {
            method: "DELETE",
          });
          applyServerProject(res.project);
          renderClips();
          toast("Персонаж удалён", true);
        } catch (err) {
          toast("Ошибка: " + err.message);
        }
      },
    });
  }
}

function renderClips() {
  syncPromptsFromUI();
  const container = $("#clipsContainer");
  container.innerHTML = "";
  $("#clipCountBadge").textContent = project.clips.length;
  const supportsRefs = currentModelSupportsRefs();
  const m = models.find((x) => x.id === project.model);

  for (const clip of project.clips) {
    const card = document.createElement("div");
    card.className = "clip-card";
    const chainHint = clip.index === 1
      ? "С нуля"
      : m?.supports_chain
        ? `Продолжение с кадра #${String(clip.index - 1).padStart(3, "0")}`
        : "Отдельная генерация";
    const refsHint = supportsRefs ? " · + персонажи" : "";
    card.innerHTML = `
      <div class="clip-header">
        <div class="clip-num">#${String(clip.index).padStart(3, "0")}</div>
        <div class="clip-hint">${chainHint}${refsHint}</div>
      </div>
      <label class="field"><span>Промпт</span>
        <textarea data-clip="${clip.index}" class="clip-prompt" placeholder="Опиши сцену...">${clip.prompt || ""}</textarea>
      </label>
      <div class="field refs-field" data-refs-field="${clip.index}">
        <span>Персонажи клипа</span>
        <div class="refs" id="refs-${clip.index}"></div>
        ${supportsRefs ? `
        <label class="ref-upload${(clip.reference_paths || []).length >= maxRefsForModel() ? " disabled" : ""}">+ Фото
          <input type="file" accept="image/*" hidden data-upload="${clip.index}" ${(clip.reference_paths || []).length >= maxRefsForModel() ? "disabled" : ""} />
        </label>` : `<p class="muted small">Модель не поддерживает референсы</p>`}
      </div>`;
    container.appendChild(card);

    const refsEl = card.querySelector(`#refs-${clip.index}`);
    const globalSet = new Set(project.global_characters || []);
    for (const rel of clip.reference_paths || []) {
      const name = basename(rel);
      const isGlobal = globalSet.has(rel);
      renderRefThumb(refsEl, {
        url: refMediaUrl(project.project_id, rel),
        name: isGlobal ? `${name} (общий)` : name,
        onDelete: supportsRefs
          ? async () => {
              try {
                const res = await api(
                  `/api/projects/${project.project_id}/clips/${clip.index}/refs/${encodeURIComponent(name)}`,
                  { method: "DELETE" },
                );
                applyServerProject(res.project);
                renderClips();
              } catch (err) {
                toast("Ошибка: " + err.message);
              }
            }
          : null,
      });
    }

    const uploadInput = card.querySelector(`input[data-upload="${clip.index}"]`);
    if (uploadInput) {
      uploadInput.addEventListener("change", async (e) => {
        const file = e.target.files?.[0];
        e.target.value = "";
        if (!file) return;
        try {
          const fd = new FormData();
          fd.append("file", file);
          await api(`/api/projects/${project.project_id}/clips/${clip.index}/refs`, {
            method: "POST",
            body: fd,
          });
          applyServerProject((await api(`/api/projects/${project.project_id}`)).project);
          renderClips();
        } catch (err) {
          toast("Ошибка загрузки: " + err.message);
        }
      });
    }
  }

  renderGlobalCharacters();
  const applyBtn = $("#btnApplyCharsAll");
  const globalUpload = $("#globalCharUpload");
  const maxRefs = maxRefsForModel();
  if (applyBtn) {
    applyBtn.disabled = !(project.global_characters || []).length;
  }
  if (globalUpload) {
    const atLimit = (project.global_characters || []).length >= maxRefs;
    globalUpload.disabled = atLimit;
    globalUpload.closest("label")?.classList.toggle("disabled", atLimit);
  }
}

async function collectClipsFromUI() {
  const clips = project.clips.map((c) => {
    const ta = document.querySelector(`textarea[data-clip="${c.index}"]`);
    return { index: c.index, prompt: ta?.value?.trim() || "", reference_paths: c.reference_paths || [] };
  });
  project = (await api(`/api/projects/${project.project_id}/clips`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ clips }),
  })).project;
}

function formatElapsed(iso) {
  if (!iso) return "0:00";
  const sec = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  return `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;
}

function renderGeneration(status) {
  const list = $("#generationList");
  list.innerHTML = "";
  let done = 0;
  for (const clip of status.clips) {
    done += clip.state === "done" ? 1 : 0;
    const item = document.createElement("div");
    item.className = "gen-item";
    const cost = clip.cost_rub != null ? ` · ${rub(clip.cost_rub)}` : "";
    const media = clip.video_url ? `<video controls src="${clip.video_url}?t=${Date.now()}"></video>` : "";
    item.innerHTML = `
      <div class="num">#${String(clip.index).padStart(3, "0")}</div>
      <div><div class="gen-status ${clip.state}">${clip.message || clip.state}${cost}</div>${media}</div>`;
    list.appendChild(item);
  }

  $("#progressFill").style.width = `${status.clips.length ? Math.round((done / status.clips.length) * 100) : 0}%`;
  const elapsed = formatElapsed(status.started_at);
  $("#progressText").textContent =
    status.status === "running" ? `Клип #${String(status.current_clip).padStart(3, "0")} (${done}/${status.clips.length}, ${elapsed})` :
    status.status === "done" ? `Готово! ${done} клипов · ${rub(status.total_cost_rub)}` :
    status.status === "error" ? `Ошибка: ${status.error}` : status.status;
  $("#costText").textContent = status.total_cost_rub > 0 ? `Списано: ${rub(status.total_cost_rub)}` : "";

  const finalWrap = $("#finalVideoWrap");
  if (status.final_video_url) {
    finalWrap.classList.remove("hidden");
    $("#finalVideo").src = status.final_video_url + "?t=" + Date.now();
  }
}

async function pollJob() {
  if (!jobId) return;
  try {
    const status = await api(`/api/jobs/${jobId}`);
    renderGeneration(status);
    if (status.status === "running" || status.status === "queued") {
      pollTimer = setTimeout(pollJob, 3000);
    } else {
      $("#btnCancel").disabled = true;
      if (status.status === "done") toast("Генерация завершена!", true);
    }
  } catch (err) {
    toast("Ошибка опроса: " + err.message);
    pollTimer = setTimeout(pollJob, 5000);
  }
}

$("#targetTotal").addEventListener("input", () => { calcDrive = "total"; scheduleCalc(); });
$("#clipCount").addEventListener("input", () => { calcDrive = "clip"; scheduleCalc(); });
$("#clipSeconds").addEventListener("change", () => { calcDrive = "clip"; scheduleCalc(); });
$("#sizeSelect").addEventListener("change", scheduleCalc);
$("#btnRefreshModels").addEventListener("click", () => loadModels(true));
$("#btnSettings").addEventListener("click", openSettings);
$("#btnOnboardingSettings").addEventListener("click", openSettings);
$("#btnCloseSettings").addEventListener("click", closeSettings);
$("#btnSaveSettings").addEventListener("click", saveSettings);
$("#btnTestApi").addEventListener("click", testApiConnection);
$("#settingsProvider").addEventListener("change", toggleCustomFields);
document.querySelectorAll("[data-close-settings]").forEach((el) => {
  el.addEventListener("click", closeSettings);
});

document.addEventListener("input", (e) => {
  if (e.target.matches("textarea.clip-prompt")) schedulePromptSave();
});

$("#globalCharUpload")?.addEventListener("change", async (e) => {
  const files = Array.from(e.target.files || []);
  e.target.value = "";
  if (!files.length || !project) return;
  try {
    for (const file of files) {
      const fd = new FormData();
      fd.append("file", file);
      const res = await api(`/api/projects/${project.project_id}/characters`, { method: "POST", body: fd });
      applyServerProject(res.project);
    }
    renderClips();
    toast(files.length > 1 ? `Добавлено ${files.length} персонажей` : "Персонаж добавлен", true);
  } catch (err) {
    toast("Ошибка: " + err.message);
  }
});

$("#btnApplyCharsAll")?.addEventListener("click", async () => {
  if (!project) return;
  try {
    const res = await api(`/api/projects/${project.project_id}/characters/apply-all`, { method: "POST" });
    applyServerProject(res.project);
    renderClips();
    toast("Персонажи закреплены на всех клипах", true);
  } catch (err) {
    toast("Ошибка: " + err.message);
  }
});

$("#btnToStep2").addEventListener("click", async () => {
  const btn = $("#btnToStep2");
  btn.disabled = true;
  try {
    await updateCalc();
    const fd = new FormData();
    fd.append("title", $("#projectTitle").value);
    fd.append("style", $("#styleSelect").value);
    fd.append("model", selectedModelId);
    fd.append("size", $("#sizeSelect").value);
    fd.append("clip_count", calc.clip_count);
    fd.append("clip_seconds", calc.clip_seconds);
    fd.append("target_total_seconds", calc.total_seconds);
    const res = await api("/api/projects", { method: "POST", body: fd });
    project = res.project;
    calc = res.calc;
    renderClips();
    showStep(2);
  } catch (err) {
    toast("Ошибка: " + err.message);
  } finally {
    btn.disabled = false;
  }
});

$("#btnBack1").addEventListener("click", () => showStep(1));

$("#btnToStep3").addEventListener("click", async () => {
  try {
    await collectClipsFromUI();
    const empty = project.clips.find((c) => !c.prompt);
    if (empty) return toast(`Заполни промпт для #${String(empty.index).padStart(3, "0")}`);
    showStep(3);
    $("#finalVideoWrap").classList.add("hidden");
    const res = await api(`/api/projects/${project.project_id}/generate`, { method: "POST" });
    jobId = res.job_id;
    if (res.clips_done > 0) {
      toast(
        `Продолжаем с #${String(res.clips_done + 1).padStart(3, "0")} — ${res.clips_done} клипов уже готовы`,
        true,
      );
    }
    $("#btnCancel").disabled = false;
    pollJob();
  } catch (err) {
    toast("Ошибка запуска: " + err.message);
  }
});

$("#btnCancel").addEventListener("click", async () => {
  if (jobId) await api(`/api/jobs/${jobId}/cancel`, { method: "POST" });
  $("#btnCancel").disabled = true;
});

$("#btnNewProject").addEventListener("click", () => {
  clearTimeout(pollTimer);
  jobId = null;
  project = null;
  showStep(1);
  loadRecentProjects();
});

(async function init() {
  await checkHealth();
  await loadModels();
  await loadRecentProjects();
})();
