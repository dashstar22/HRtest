/* AI 招聘简历智能筛选助手 —— 原生 JS 前端（无构建步骤） */

const $ = (id) => document.getElementById(id);

const els = {
  modeBadge: $("modeBadge"),
  seedBtn: $("seedBtn"),
  jobSelect: $("jobSelect"),
  jobTitle: $("jobTitle"),
  jobDept: $("jobDept"),
  jdText: $("jdText"),
  parseJdBtn: $("parseJdBtn"),
  parseHint: $("parseHint"),
  degree: $("degree"),
  minYears: $("minYears"),
  requiredTags: $("requiredTags"),
  requiredInput: $("requiredInput"),
  niceTags: $("niceTags"),
  niceInput: $("niceInput"),
  saveJobBtn: $("saveJobBtn"),
  dropzone: $("dropzone"),
  fileInput: $("fileInput"),
  resumeList: $("resumeList"),
  resumeCount: $("resumeCount"),
  uploadMsg: $("uploadMsg"),
  screenBtn: $("screenBtn"),
  pendingHint: $("pendingHint"),
  deleteJobBtn: $("deleteJobBtn"),
  rescreenBtn: $("rescreenBtn"),
  exportBtn: $("exportBtn"),
  verdictFilter: $("verdictFilter"),
  emptyState: $("emptyState"),
  resultTable: $("resultTable"),
  resultBody: $("resultBody"),
  statTotal: $("statTotal"),
  statScreened: $("statScreened"),
  statAdvance: $("statAdvance"),
  statHold: $("statHold"),
  statAccepted: $("statAccepted"),
  statRejected: $("statRejected"),
  statAvg: $("statAvg"),
  staleBanner: $("staleBanner"),
  staleText: $("staleText"),
  staleScreenBtn: $("staleScreenBtn"),
  searchInput: $("searchInput"),
  sortSelect: $("sortSelect"),
  onlyChanged: $("onlyChanged"),
  changeHint: $("changeHint"),
  bulkBar: $("bulkBar"),
  bulkCount: $("bulkCount"),
  bulkCancel: $("bulkCancel"),
  selectAll: $("selectAll"),
  drawer: $("drawer"),
  drawerName: $("drawerName"),
  drawerMeta: $("drawerMeta"),
  drawerScore: $("drawerScore"),
  drawerBody: $("drawerBody"),
  toast: $("toast"),
};

const state = {
  jobId: null,
  jobs: [],
  resumes: [],
  results: [],
  filter: "all",
  required: [],
  nice: [],
  busy: false,
  resumeCache: new Map(),
  query: "",
  sortMode: "score",
  onlyChanged: false,
  selected: new Set(),
  cursor: -1,
};

const VERDICT = {
  advance: { label: "建议进入人工复核", cls: "badge-green" },
  hold: { label: "暂缓考虑", cls: "badge-amber" },
};

const DECISION = {
  accepted: { label: "已采纳", cls: "badge-green" },
  rejected: { label: "已拒绝", cls: "badge-red" },
};

const FILTER_EMPTY = {
  all: "还没有筛选结果，上传简历后点击「开始 AI 筛选」。",
  advance: "当前没有建议进入复核的候选人。",
  hold: "当前没有暂缓考虑的候选人。",
};

/* ----------------------------------------------------------------- 工具 */

const escapeHtml = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]
  );

let toastTimer = null;
function toast(message, type = "") {
  els.toast.textContent = message;
  els.toast.className = `toast show ${type}`.trim();
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    els.toast.className = "toast";
  }, 3200);
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (response.status === 204) return null;
  const text = await response.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!response.ok) {
    const detail = data && data.detail ? data.detail : `请求失败（${response.status}）`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

const postJson = (path, body) =>
  api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });

const scoreTier = (score) => (score >= 80 ? "high" : score >= 60 ? "mid" : "low");
const fmtYears = (years) => (years === null || years === undefined ? "未知" : `${years} 年`);
const initial = (name) => (name || "?").trim().charAt(0).toUpperCase();
const formatTime = (iso) => {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const pad = (value) => String(value).padStart(2, "0");
  return `${date.getMonth() + 1}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
};

/* ------------------------------------------------------------- 初始化 */

async function init() {
  bindEvents();
  await loadStatus();
  await loadJobs();
  if (state.jobs.length) {
    await selectJob(state.jobs[0].id);
  } else {
    resetForm();
    renderResumes();
    renderResults();
  }
}

async function loadStatus() {
  try {
    const status = await api("/api/status");
    if (status.mode === "deepseek") {
      els.modeBadge.className = "badge badge-blue";
      els.modeBadge.textContent = `已配置 ${status.model}`;
      els.modeBadge.title = status.message;
    } else {
      els.modeBadge.className = "badge badge-amber";
      els.modeBadge.textContent = "规则模拟模式";
      els.modeBadge.title = status.message;
    }
  } catch {
    els.modeBadge.className = "badge badge-red";
    els.modeBadge.textContent = "服务未就绪";
  }
}

async function loadJobs() {
  const jobs = await api("/api/jobs");
  state.jobs = jobs;
  els.jobSelect.innerHTML =
    '<option value="">＋ 新增岗位</option>' +
    jobs
      .map(
        (job) =>
          `<option value="${escapeHtml(job.id)}">${escapeHtml(job.title)}（${job.resume_count} 份简历）</option>`
      )
      .join("");
  els.jobSelect.value = state.jobId || "";
}

async function selectJob(jobId) {
  state.resumeCache.clear();
  state.selected.clear();
  state.cursor = -1;
  state.jobId = jobId || null;

  if (!jobId) {
    resetForm();
    state.resumes = [];
    state.results = [];
    renderResumes();
    renderResults();
    els.jobSelect.value = "";
    return;
  }

  const job = state.jobs.find((item) => item.id === jobId) || (await api(`/api/jobs/${jobId}`));
  if (!job) return;

  els.jobTitle.value = job.title || "";
  els.jobDept.value = job.department || "";
  els.jdText.value = job.jd_text || "";
  els.degree.value = job.degree || "不限";
  els.minYears.value = job.min_years ?? 0;
  state.required = [...(job.required_skills || [])];
  state.nice = [...(job.nice_skills || [])];
  renderTags();
  els.parseHint.textContent = "";
  els.uploadMsg.textContent = "";

  els.jobSelect.value = jobId;
  await Promise.all([refreshResumes(), refreshResults()]);
}

function resetForm() {
  els.jobTitle.value = "";
  els.jobDept.value = "";
  els.jdText.value = "";
  els.degree.value = "本科";
  els.minYears.value = "3";
  state.required = [];
  state.nice = [];
  renderTags();
  els.parseHint.textContent = "";
  els.uploadMsg.textContent = "";
}

/* --------------------------------------------------------------- 标签 */

function addTag(list, raw) {
  const value = String(raw || "").trim().replace(/[,，、;；]$/, "");
  if (!value) return;
  if (value.length > 24) {
    toast("单个技能名称请控制在 24 个字符内", "error");
    return;
  }
  if (list.some((item) => item.toLowerCase() === value.toLowerCase())) return;
  list.push(value);
  renderTags();
}

function syncTagContainer(container, input, list) {
  [...container.querySelectorAll(".tag")].forEach((node) => node.remove());
  list.forEach((value) => {
    const tag = document.createElement("span");
    tag.className = "tag";
    const text = document.createElement("span");
    text.textContent = value;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "×";
    remove.setAttribute("aria-label", `移除 ${value}`);
    remove.addEventListener("click", () => {
      list.splice(list.indexOf(value), 1);
      renderTags();
    });
    tag.append(text, remove);
    container.insertBefore(tag, input);
  });
}

function renderTags() {
  syncTagContainer(els.requiredTags, els.requiredInput, state.required);
  syncTagContainer(els.niceTags, els.niceInput, state.nice);
}

/* ----------------------------------------------------------- 岗位表单 */

async function parseJd() {
  const jdText = els.jdText.value.trim();
  if (jdText.length < 10) {
    toast("请先粘贴完整的岗位 JD", "error");
    els.jdText.focus();
    return;
  }

  const original = els.parseJdBtn.innerHTML;
  els.parseJdBtn.disabled = true;
  els.parseJdBtn.innerHTML = '<span class="spinner" style="border-color:#c7d2fe;border-top-color:#4f46e5"></span>解析中…';
  try {
    const parsed = await postJson("/api/parse-jd", { jd_text: jdText });
    if (parsed.title && !els.jobTitle.value.trim()) els.jobTitle.value = parsed.title;
    if (parsed.department && !els.jobDept.value.trim()) els.jobDept.value = parsed.department;
    els.degree.value = parsed.degree || "不限";
    els.minYears.value = parsed.min_years ?? 0;
    if (parsed.required_skills && parsed.required_skills.length) {
      state.required = parsed.required_skills.slice();
    }
    if (parsed.nice_skills && parsed.nice_skills.length) {
      state.nice = parsed.nice_skills.slice();
    }
    renderTags();
    els.parseHint.textContent = `已识别 ${state.required.length} 项必备技能、${state.nice.length} 项加分项，可手动调整`;
  } catch (error) {
    toast(error.message, "error");
  } finally {
    els.parseJdBtn.disabled = false;
    els.parseJdBtn.innerHTML = original;
  }
}

async function saveJob() {
  const title = els.jobTitle.value.trim();
  const jdText = els.jdText.value.trim();
  if (!title) {
    toast("请填写岗位名称", "error");
    els.jobTitle.focus();
    return;
  }
  if (jdText.length < 10) {
    toast("请填写完整的岗位 JD，AI 需要它来判断匹配度", "error");
    els.jdText.focus();
    return;
  }

  const payload = {
    title,
    department: els.jobDept.value.trim(),
    jd_text: jdText,
    degree: els.degree.value,
    min_years: Number(els.minYears.value || 0),
    required_skills: state.required,
    nice_skills: state.nice,
  };

  const isUpdate = Boolean(state.jobId);
  els.saveJobBtn.disabled = true;
  els.saveJobBtn.textContent = "保存中…";
  try {
    const job = isUpdate
      ? await api(`/api/jobs/${state.jobId}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        })
      : await postJson("/api/jobs", payload);

    await loadJobs();
    await selectJob(job.id);
    toast(isUpdate ? "岗位已更新，旧结果标记为过期，人工标注会保留" : "岗位已保存，可以上传简历了", "success");
  } catch (error) {
    toast(error.message, "error");
  } finally {
    els.saveJobBtn.disabled = false;
    els.saveJobBtn.textContent = "保存岗位并继续";
  }
}

/* --------------------------------------------------------------- 简历 */

async function uploadFiles(fileList) {
  if (!state.jobId) {
    toast("请先保存岗位，再上传简历", "error");
    return;
  }
  const files = [...fileList];
  if (!files.length) return;

  const form = new FormData();
  files.forEach((file) => form.append("files", file));

  els.uploadMsg.textContent = `正在解析 ${files.length} 份简历…`;
  els.uploadMsg.className = "hint";
  try {
    const data = await api(`/api/jobs/${state.jobId}/resumes`, { method: "POST", body: form });
    const okCount = data.uploaded.length;
    const errCount = data.errors.length;
    if (okCount) {
      els.uploadMsg.className = "hint ok";
      els.uploadMsg.textContent = `已解析 ${okCount} 份简历${errCount ? `，${errCount} 份失败` : ""}`;
    } else {
      els.uploadMsg.className = "hint error";
      els.uploadMsg.textContent = "上传失败";
    }
    if (errCount) {
      const detail = data.errors.map((item) => `${item.file}：${item.message}`).join("；");
      toast(detail, "error");
    }
    await Promise.all([refreshResumes(), loadJobs()]);
  } catch (error) {
    els.uploadMsg.className = "hint error";
    els.uploadMsg.textContent = error.message;
    toast(error.message, "error");
  } finally {
    els.fileInput.value = "";
  }
}

async function refreshResumes() {
  if (!state.jobId) {
    state.resumes = [];
    renderResumes();
    return;
  }
  state.resumes = await api(`/api/jobs/${state.jobId}/resumes`);
  renderResumes();
}

function renderResumes() {
  els.statTotal.textContent = state.resumes.length;
  els.resumeCount.textContent = `${state.resumes.length} 份`;
  els.resumeList.innerHTML = state.resumes
    .map(
      (resume) => `
      <li>
        <span aria-hidden="true">📄</span>
        <span class="fname" title="${escapeHtml(resume.file_name)}">${escapeHtml(resume.name)}</span>
        <span class="fmeta">${resume.char_count} 字</span>
        <button class="del" type="button" data-resume-id="${escapeHtml(resume.id)}" title="删除">✕</button>
      </li>`
    )
    .join("");

  els.resumeList.querySelectorAll(".del").forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.stopPropagation();
      const resumeId = button.dataset.resumeId;
      const resume = state.resumes.find((item) => item.id === resumeId);
      if (!window.confirm(`确定删除「${resume ? resume.name : "该简历"}」？对应的筛选结果会一并删除。`)) {
        return;
      }
      try {
        await api(`/api/resumes/${resumeId}`, { method: "DELETE" });
        state.resumeCache.delete(resumeId);
        await Promise.all([refreshResumes(), refreshResults(), loadJobs()]);
        toast("已删除该简历");
      } catch (error) {
        toast(error.message, "error");
      }
    });
  });

  updateScreenButton();
  updatePendingHint();
}

function updatePendingHint() {
  if (!els.pendingHint) return;
  const pending = Math.max(0, state.resumes.length - state.results.length);
  if (pending > 0) {
    els.pendingHint.className = "hint center warn-text";
    els.pendingHint.textContent = `还有 ${pending} 份简历未筛选`;
  } else {
    els.pendingHint.className = "hint center";
    els.pendingHint.textContent = state.resumes.length ? "全部简历均已筛选" : "";
  }
}

/* --------------------------------------------------------------- 筛选 */

function updateScreenButton() {
  const ready = Boolean(state.jobId) && state.resumes.length > 0 && !state.busy;
  els.screenBtn.disabled = !ready;
  els.rescreenBtn.disabled = state.busy || state.results.length === 0;
  els.exportBtn.disabled = state.results.length === 0;
  if (!state.busy) els.screenBtn.textContent = "开始 AI 筛选";
}

function setBusy(busy, label = "AI 分析中…") {
  state.busy = busy;
  els.seedBtn.disabled = busy;
  els.saveJobBtn.disabled = busy;
  els.parseJdBtn.disabled = busy;
  // 筛选期间禁止删除简历 / 上传，避免结果写入时简历已不存在
  document.body.classList.toggle("busy", busy);
  els.screenBtn.innerHTML = busy ? `<span class="spinner"></span>${escapeHtml(label)}` : "开始 AI 筛选";
  updateScreenButton();
}

async function screen() {
  if (!state.jobId || !state.resumes.length) {
    toast("请先上传简历", "error");
    return;
  }
  state.selected.clear();
  state.cursor = -1;
  setBusy(true);
  try {
    const report = await postJson(`/api/jobs/${state.jobId}/screen`, { resume_ids: [] });
    await Promise.all([refreshResults(), loadJobs()]);
    if (report.failed) {
      toast(`完成 ${report.succeeded} 份，失败 ${report.failed} 份：${report.errors.join("；")}`, "error");
    } else {
      const changed = state.results.filter(hasChanged);
      const verdictChanged = changed.filter(
        (item) => item.previous_verdict && item.previous_verdict !== item.verdict
      ).length;
      const hasPrevious = state.results.some((item) => item.previous_score !== null && item.previous_score !== undefined);
      const suffix = changed.length
        ? `；${changed.length} 人结果有变化${verdictChanged ? `（${verdictChanged} 人建议变化）` : ""}`
        : hasPrevious ? "；可对比结果与上次一致" : "；首次筛选，无上次结果";
      toast(`筛选完成：${report.succeeded} 份${suffix}`, "success");
    }
    if (report.mode && report.mode.includes("降级")) {
      toast("部分简历调用大模型失败，已降级为规则引擎评分", "error");
    }
  } catch (error) {
    toast(error.message, "error");
  } finally {
    setBusy(false);
  }
}

async function refreshResults() {
  if (!state.jobId) {
    state.results = [];
    renderResults();
    return;
  }
  state.results = await api(`/api/jobs/${state.jobId}/results`);
  renderResults();
}

/* --------------------------------------------------------------- 展示 */

const hasChanged = (item) =>
  item.previous_score !== null &&
  item.previous_score !== undefined &&
  (item.previous_score !== item.score || item.previous_verdict !== item.verdict);

function visibleRows() {
  const query = state.query.trim().toLowerCase();
  let rows = state.results.filter((item) => {
    if (state.filter !== "all" && item.verdict !== state.filter) return false;
    if (state.onlyChanged && !hasChanged(item)) return false;
    if (!query) return true;
    const profile = item.profile || {};
    const haystack = [
      item.resume_name,
      item.file_name,
      item.summary,
      profile.current_title || "",
      (profile.key_skills || []).join(" "),
      item.decision_note || "",
    ]
      .join(" ")
      .toLowerCase();
    return haystack.includes(query);
  });

  const decided = (item) => (item.decision ? 1 : 0);
  switch (state.sortMode) {
    case "score_asc":
      rows = [...rows].sort((a, b) => a.score - b.score);
      break;
    case "decision":
      rows = [...rows].sort((a, b) => decided(b) - decided(a) || b.score - a.score);
      break;
    case "changed":
      rows = [...rows].sort((a, b) => Number(hasChanged(b)) - Number(hasChanged(a)) || b.score - a.score);
      break;
    default:
      rows = [...rows].sort((a, b) => b.score - a.score);
  }
  return rows;
}

function renderBulkBar() {
  const count = state.selected.size;
  els.bulkBar.hidden = count === 0;
  els.bulkCount.textContent = `已选 ${count} 项`;
}

function scrollCursorIntoView() {
  const rows = els.resultBody.querySelectorAll("tr");
  const target = rows[state.cursor];
  if (target) target.scrollIntoView({ block: "nearest" });
}

function renderResults() {
  const total = state.results.length;
  const advance = state.results.filter((item) => item.verdict === "advance").length;
  const hold = total - advance;
  const accepted = state.results.filter((item) => item.decision === "accepted").length;
  const rejected = state.results.filter((item) => item.decision === "rejected").length;
  const avg = total ? Math.round((state.results.reduce((sum, item) => sum + item.score, 0) / total) * 10) / 10 : 0;
  const staleCount = state.results.filter((item) => item.stale).length;

  els.statTotal.textContent = state.resumes.length;
  els.statScreened.textContent = total;
  els.statAdvance.textContent = advance;
  els.statHold.textContent = hold;
  els.statAccepted.textContent = accepted;
  els.statRejected.textContent = rejected;
  els.statAvg.textContent = avg;

  els.staleBanner.hidden = staleCount === 0;
  if (staleCount > 0) {
    els.staleText.textContent = `岗位条件已更新，${staleCount} 条结果仍基于旧条件；人工标注会保留，建议重新筛选。`;
  }

  const changedCount = state.results.filter(hasChanged).length;
  els.changeHint.textContent = changedCount
    ? `${changedCount} 人与上次筛选不同`
    : total
      ? state.results.some((item) => item.previous_score !== null && item.previous_score !== undefined)
        ? "可对比结果与上次一致"
        : "首次筛选，无上次结果"
      : "";

  // 选中的结果如果被删除或换岗位，自动清理
  const validIds = new Set(state.results.map((item) => item.id));
  [...state.selected].forEach((id) => {
    if (!validIds.has(id)) state.selected.delete(id);
  });

  renderTable();
  updateScreenButton();
  updatePendingHint();
}

function updateSelectAllState(rows = visibleRows()) {
  const allChecked = rows.length > 0 && rows.every((item) => state.selected.has(item.id));
  els.selectAll.checked = allChecked;
  els.selectAll.indeterminate = !allChecked && rows.some((item) => state.selected.has(item.id));
  els.selectAll.disabled = rows.length === 0;
}

function emptyText(rows) {
  if (state.results.length === 0) {
    return state.resumes.length === 0
      ? "保存岗位并上传简历后，点击「开始 AI 筛选」，结果会显示在这里。"
      : "还没有筛选结果，点击「开始 AI 筛选」。";
  }
  if (rows.length > 0) return "";
  if (state.onlyChanged) return "本轮重新筛选后，没有分数或建议发生变化的候选人。";
  if (state.query.trim()) return `没有匹配「${state.query.trim()}」的候选人。`;
  return FILTER_EMPTY[state.filter] || "当前筛选条件下没有结果。";
}

function renderTable() {
  const rows = visibleRows();
  if (state.cursor >= rows.length) state.cursor = rows.length - 1;

  els.resultTable.hidden = rows.length === 0;
  els.emptyState.hidden = rows.length > 0;
  els.emptyState.textContent = emptyText(rows);

  els.resultBody.innerHTML = rows
    .map((item, index) => {
      const profile = item.profile || {};
      const verdict = VERDICT[item.verdict] || VERDICT.hold;
      const tier = scoreTier(item.score);
      const decision = DECISION[item.decision];
      const checked = state.selected.has(item.id);
      const rowClasses = [item.stale ? "stale" : "", index === state.cursor ? "focused" : ""]
        .filter(Boolean)
        .join(" ");

      const delta =
        item.previous_score !== null && item.previous_score !== undefined
          ? item.score - item.previous_score
          : null;
      const deltaHtml = delta
        ? `<span class="delta ${delta > 0 ? "up" : "down"}">${delta > 0 ? "↑" : "↓"}${Math.abs(delta)}</span>`
        : "";

      const previousVerdict =
        item.previous_verdict && item.previous_verdict !== item.verdict
          ? VERDICT[item.previous_verdict]
          : null;
      const verdictShift = previousVerdict
        ? `<div class="score-shift">原建议：${previousVerdict.label}</div>`
        : "";

      const scoreShift =
        item.decision &&
        item.decision_score !== null &&
        item.decision_score !== undefined &&
        item.decision_score !== item.score
          ? `<span class="score-shift" title="人工标注时的分数，重新筛选后分数已变化">标注时 ${item.decision_score} 分</span>`
          : "";
      const noteFlag = item.decision_note
        ? `<span class="note-flag" title="${escapeHtml(item.decision_note)}">📝</span>`
        : "";

      const decisionCell = decision
        ? `<div class="decision-cell">
             <span class="badge ${decision.cls}">${decision.label}</span>
             ${noteFlag}${scoreShift}
             <button class="decide-btn" type="button" data-decide="clear" data-id="${escapeHtml(item.id)}" title="撤销标注">↺</button>
           </div>`
        : `<div class="decide-actions">
             <button class="decide-btn accept" type="button" data-decide="accepted" data-id="${escapeHtml(item.id)}" title="采纳：进入沟通">✓</button>
             <button class="decide-btn reject" type="button" data-decide="rejected" data-id="${escapeHtml(item.id)}" title="拒绝：不进入沟通（快捷键 R）">✕</button>
           </div>`;

      return `
        <tr class="${rowClasses}" data-result-id="${escapeHtml(item.id)}" data-index="${index}">
          <td class="col-check"><input type="checkbox" data-select="${escapeHtml(item.id)}" ${checked ? "checked" : ""} aria-label="选择 ${escapeHtml(item.resume_name)}" /></td>
          <td>
            <div class="who">
              <div class="avatar">${escapeHtml(initial(item.resume_name))}</div>
              <div>
                <div class="name">${escapeHtml(item.resume_name)}</div>
                <div class="file" title="${escapeHtml(item.file_name)}">${escapeHtml(item.file_name)}</div>
              </div>
            </div>
          </td>
          <td>
            <div class="score">
              <div class="bar ${tier}"><i style="width:${Math.max(4, item.score)}%"></i></div>
              <b>${item.score}</b>
              ${deltaHtml}
            </div>
          </td>
          <td>
            <span class="badge ${verdict.cls}">${verdict.label}</span>
            ${verdictShift}
          </td>
          <td>${decisionCell}</td>
          <td><div class="ellipsis" title="${escapeHtml(profile.current_title || "")}">${escapeHtml(profile.current_title || "—")}</div></td>
          <td>${escapeHtml(profile.highest_degree || "未知")} / ${fmtYears(profile.years_of_experience)}</td>
          <td>
            <span class="chip chip-green">${item.matched.length}</span>
            <span class="chip chip-amber">${item.uncertain.length}</span>
          </td>
          <td class="summary">${escapeHtml(item.summary)}</td>
          <td><button class="btn btn-ghost btn-sm" type="button" data-open>详情</button></td>
        </tr>`;
    })
    .join("");

  updateSelectAllState(rows);

  els.resultBody.querySelectorAll("tr").forEach((row) => {
    row.addEventListener("click", () => {
      state.cursor = Number(row.dataset.index);
      openDrawer(row.dataset.resultId);
    });
  });

  els.resultBody.querySelectorAll("[data-select]").forEach((box) => {
    box.addEventListener("click", (event) => event.stopPropagation());
    box.addEventListener("change", () => {
      if (box.checked) state.selected.add(box.dataset.select);
      else state.selected.delete(box.dataset.select);
      renderBulkBar();
      updateSelectAllState(rows);
    });
  });

  els.resultBody.querySelectorAll("[data-decide]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const value = button.dataset.decide;
      decideResult(button.dataset.id, value === "clear" ? null : value);
    });
  });

  renderBulkBar();
}

/* --------------------------------------------------------------- 抽屉 */

function sectionList(title, items, renderItem) {
  const inner = items.length
    ? `<div class="items">${items.map(renderItem).join("")}</div>`
    : '<div class="hint">无</div>';
  return `<div class="section"><h4>${title}</h4>${inner}</div>`;
}

function decisionSection(result) {
  const current = result.decision ? DECISION[result.decision] : null;
  const shift =
    result.decision && result.decision_score !== null && result.decision_score !== undefined && result.decision_score !== result.score
      ? `标注时 ${result.decision_score} 分，当前 ${result.score} 分`
      : "";
  const meta = [result.decision_at ? `标注于 ${formatTime(result.decision_at)}` : "", shift]
    .filter(Boolean)
    .join(" · ");
  const note = result.decision_note || "";
  const noteDisabled = !result.decision;

  return `
    <div class="section">
      <h4>人工决策</h4>
      <div class="decide-bar">
        <button class="btn btn-secondary btn-sm" type="button" data-drawer-decide="accepted">
          ${result.decision === "accepted" ? "✓ 已采纳" : "采纳"}
        </button>
        <button class="btn btn-ghost btn-sm" type="button" data-drawer-decide="rejected">
          ${result.decision === "rejected" ? "✕ 已拒绝" : "拒绝"}
        </button>
        ${current ? '<button class="btn btn-ghost btn-sm" type="button" data-drawer-decide="clear">撤销标注</button>' : ""}
      </div>
      ${meta ? `<p class="hint" style="margin: 8px 0 0">${escapeHtml(meta)}</p>` : ""}
      <textarea class="note-editor" id="noteEditor" maxlength="200"
        placeholder="${noteDisabled ? "先做出采纳或拒绝，再补充备注" : "写一句判断依据，例如：沟通后候选人期望薪资超预算"}"
        ${noteDisabled ? "disabled" : ""}>${escapeHtml(note)}</textarea>
      <div class="note-actions">
        <button class="btn btn-secondary btn-sm" type="button" id="saveNoteBtn" ${noteDisabled ? "disabled" : ""}>保存备注</button>
        <span class="hint">${note.length}/200</span>
      </div>
      <p class="hint" style="margin: 8px 0 0">人工决策与备注不会被重新筛选覆盖。</p>
    </div>`;
}

function renderDrawer(result, rawText) {
  const profile = result.profile || {};
  const verdict = VERDICT[result.verdict] || VERDICT.hold;
  const scrollTop = els.drawerBody.scrollTop;

  els.drawerName.textContent = result.resume_name;
  els.drawerMeta.innerHTML = `${escapeHtml(result.file_name)} · <span class="badge ${verdict.cls}">${verdict.label}</span>`;
  els.drawerScore.textContent = result.score;

  const skills = (profile.key_skills || []).map((skill) => `<span class="tag">${escapeHtml(skill)}</span>`).join("");

  els.drawerBody.innerHTML = `
    ${result.stale ? '<div class="banner-warn" style="margin-bottom:16px">岗位条件已更新，本结果基于旧条件，建议重新筛选。</div>' : ""}

    <div class="section">
      <div class="profile-grid">
        <div class="profile-item"><div class="k">当前/最近职位</div><div class="v">${escapeHtml(profile.current_title || "—")}</div></div>
        <div class="profile-item"><div class="k">最高学历</div><div class="v">${escapeHtml(profile.highest_degree || "未知")}</div></div>
        <div class="profile-item"><div class="k">相关经验</div><div class="v">${fmtYears(profile.years_of_experience)}</div></div>
        <div class="profile-item"><div class="k">评分来源</div><div class="v">${result.mode === "deepseek" ? "大模型" : result.mode === "rule-fallback" ? "规则兜底" : "规则引擎"}</div></div>
      </div>
      ${skills ? `<div class="tags" style="margin-top:10px;border-style:solid">${skills}</div>` : ""}
      ${profile.experience_basis ? `<div class="hint" style="margin-top:10px">${escapeHtml(profile.experience_basis)}</div>` : '<div class="hint">历史结果未记录年限依据，建议重新筛选。</div>'}
      ${(profile.review_warnings || []).map((warning) => `<div class="banner-warn">${escapeHtml(warning)}</div>`).join("")}
    </div>

    ${decisionSection(result)}

    <div class="section">
      <h4>结论摘要</h4>
      <div class="item"><div class="req">${escapeHtml(result.summary)}</div></div>
    </div>

    ${sectionList(
      `符合的条件（${result.matched.length}）`,
      result.matched,
      (item) => `<div class="item"><div class="req">✓ ${escapeHtml(item.requirement)}</div><div class="ev">${escapeHtml(item.evidence || "简历原文未提供证据")}</div></div>`
    )}

    <p class="hint">${profile.evaluated_on ? "引用已完整定位到简历原文；原文存在不代表足以证明岗位要求，相关性与真实性仍需人工核实。" : "历史结果未执行新版完整引用校验，请重新筛选；以下引用需人工核对。"}</p>

    ${sectionList(
      `有待确认的条件（${result.uncertain.length}）`,
      result.uncertain,
      (item) => `<div class="item warn"><div class="req">? ${escapeHtml(item.requirement)}</div><div class="ev">${escapeHtml(item.reason)}</div></div>`
    )}

    <div class="section">
      <h4>相关优势</h4>
      ${result.strengths.length ? `<ul class="bullets">${result.strengths.map((s) => `<li>${escapeHtml(s)}</li>`).join("")}</ul>` : '<div class="hint">无</div>'}
    </div>

    <div class="section">
      <h4>风险与短板</h4>
      ${result.risks.length ? `<ul class="bullets">${result.risks.map((s) => `<li>${escapeHtml(s)}</li>`).join("")}</ul>` : '<div class="hint">无</div>'}
    </div>

    <div class="section">
      <h4>简历原文</h4>
      <pre class="raw">${escapeHtml(rawText || "（无法读取简历原文）")}</pre>
    </div>
  `;

  els.drawerBody.querySelectorAll("[data-drawer-decide]").forEach((button) => {
    button.addEventListener("click", () => {
      const value = button.dataset.drawerDecide;
      decideResult(result.id, value === "clear" ? null : value);
    });
  });

  const saveNoteBtn = els.drawerBody.querySelector("#saveNoteBtn");
  if (saveNoteBtn) {
    saveNoteBtn.addEventListener("click", () => {
      const editor = els.drawerBody.querySelector("#noteEditor");
      decideResult(result.id, result.decision, editor ? editor.value : "");
    });
  }

  els.drawerBody.scrollTop = scrollTop;
}

async function openDrawer(resultId) {
  const result = state.results.find((item) => item.id === resultId);
  if (!result) return;

  let rawText = state.resumeCache.get(result.resume_id);
  if (rawText === undefined) {
    try {
      const detail = await api(`/api/resumes/${result.resume_id}`);
      rawText = detail.text;
      state.resumeCache.set(result.resume_id, rawText);
    } catch {
      rawText = "（无法读取简历原文）";
    }
  }

  renderDrawer(result, rawText);
  els.drawer.setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
}

async function decideResult(resultId, decision, note) {
  const body = { decision };
  if (note !== undefined) body.note = note;
  try {
    const updated = await api(`/api/results/${resultId}/decision`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const index = state.results.findIndex((item) => item.id === resultId);
    if (index >= 0) state.results[index] = updated;
    renderResults();

    if (els.drawer.getAttribute("aria-hidden") === "false") {
      const current = state.results.find((item) => item.id === resultId);
      if (current) renderDrawer(current, state.resumeCache.get(current.resume_id));
    }

    if (note !== undefined) toast("备注已保存", "success");
    else if (decision === "accepted") toast("已标记为采纳", "success");
    else if (decision === "rejected") toast("已标记为拒绝", "success");
    else toast("已撤销标注");
  } catch (error) {
    toast(error.message, "error");
  }
}

async function deleteJob() {
  if (!state.jobId) {
    toast("当前没有选中的岗位", "error");
    return;
  }
  const title = els.jobTitle.value.trim() || "当前岗位";
  if (
    !window.confirm(
      `确定删除岗位「${title}」？\n该岗位下的简历与筛选结果会一并删除，且不可恢复。`
    )
  ) {
    return;
  }
  try {
    await api(`/api/jobs/${state.jobId}`, { method: "DELETE" });
    state.jobId = null;
    state.selected.clear();
    state.cursor = -1;
    await loadJobs();
    await selectJob(null);
    toast("岗位已删除");
  } catch (error) {
    toast(error.message, "error");
  }
}

async function bulkDecide(decision) {
  const ids = [...state.selected];
  if (!ids.length || !state.jobId) return;
  try {
    const report = await api(`/api/jobs/${state.jobId}/decisions`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ result_ids: ids, decision }),
    });
    state.selected.clear();
    await refreshResults();
    const label = decision === "accepted" ? "采纳" : decision === "rejected" ? "拒绝" : "清除标注";
    toast(`已批量${label} ${report.updated} 人`, "success");
  } catch (error) {
    toast(error.message, "error");
  }
}

function closeDrawer() {
  els.drawer.setAttribute("aria-hidden", "true");
  document.body.style.overflow = "";
}

/* --------------------------------------------------------------- 示例 */

async function seedDemo() {
  setBusy(true, "载入示例…");
  try {
    const data = await api("/api/demo/seed", { method: "POST" });
    await loadJobs();
    await selectJob(data.job_id);
    toast(`已载入示例岗位「${data.job_title}」和 ${data.total_resumes} 份简历`, "success");
    await screen();
  } catch (error) {
    toast(error.message, "error");
  } finally {
    setBusy(false);
  }
}

/* --------------------------------------------------------------- 事件 */

function bindEvents() {
  els.parseJdBtn.addEventListener("click", parseJd);
  els.saveJobBtn.addEventListener("click", saveJob);
  els.screenBtn.addEventListener("click", screen);
  els.rescreenBtn.addEventListener("click", screen);
  els.staleScreenBtn.addEventListener("click", screen);
  els.seedBtn.addEventListener("click", seedDemo);
  els.exportBtn.addEventListener("click", () => {
    if (!state.jobId) return;
    window.location.href = `/api/jobs/${state.jobId}/export.csv`;
  });

  els.jobSelect.addEventListener("change", () => {
    const value = els.jobSelect.value;
    if (!value) {
      state.jobId = null;
      resetForm();
      state.resumes = [];
      state.results = [];
      renderResumes();
      renderResults();
      return;
    }
    selectJob(value);
  });

  [els.requiredInput, els.niceInput].forEach((input) => {
    const list = input === els.requiredInput ? state.required : state.nice;
    input.addEventListener("keydown", (event) => {
      if (["Enter", ",", "，", "、", ";", "；"].includes(event.key)) {
        event.preventDefault();
        addTag(list, input.value);
        input.value = "";
      } else if (event.key === "Backspace" && !input.value && list.length) {
        list.pop();
        renderTags();
      }
    });
    input.addEventListener("blur", () => {
      if (input.value.trim()) {
        addTag(list, input.value);
        input.value = "";
      }
    });
  });

  els.dropzone.addEventListener("click", () => els.fileInput.click());
  els.dropzone.addEventListener("dragover", (event) => {
    event.preventDefault();
    els.dropzone.classList.add("dragover");
  });
  els.dropzone.addEventListener("dragleave", () => els.dropzone.classList.remove("dragover"));
  els.dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    els.dropzone.classList.remove("dragover");
    uploadFiles(event.dataTransfer.files);
  });
  els.fileInput.addEventListener("change", () => uploadFiles(els.fileInput.files));

  els.verdictFilter.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      els.verdictFilter.querySelectorAll("button").forEach((node) => node.classList.remove("active"));
      button.classList.add("active");
      state.filter = button.dataset.filter;
      renderTable();
    });
  });

  els.searchInput.addEventListener("input", () => {
    state.query = els.searchInput.value;
    state.cursor = -1;
    renderTable();
  });

  els.sortSelect.addEventListener("change", () => {
    state.sortMode = els.sortSelect.value;
    state.cursor = -1;
    renderTable();
  });

  els.onlyChanged.addEventListener("change", () => {
    state.onlyChanged = els.onlyChanged.checked;
    state.cursor = -1;
    renderTable();
  });

  els.selectAll.addEventListener("change", () => {
    const rows = visibleRows();
    if (els.selectAll.checked) rows.forEach((item) => state.selected.add(item.id));
    else rows.forEach((item) => state.selected.delete(item.id));
    renderTable();
  });

  els.bulkBar.querySelectorAll("[data-bulk]").forEach((button) => {
    button.addEventListener("click", () => {
      const value = button.dataset.bulk;
      bulkDecide(value === "clear" ? null : value);
    });
  });

  els.bulkCancel.addEventListener("click", () => {
    state.selected.clear();
    renderTable();
  });

  els.deleteJobBtn.addEventListener("click", deleteJob);

  els.drawer.querySelectorAll("[data-close]").forEach((node) => {
    node.addEventListener("click", closeDrawer);
  });

  document.addEventListener("keydown", handleKeyboard);
}

function handleKeyboard(event) {
  if (event.key === "Escape") {
    if (els.drawer.getAttribute("aria-hidden") === "false") closeDrawer();
    return;
  }

  const tag = (event.target.tagName || "").toLowerCase();
  const typing = ["input", "textarea", "select"].includes(tag) || event.target.isContentEditable;
  const drawerOpen = els.drawer.getAttribute("aria-hidden") === "false";
  if (typing || drawerOpen || state.busy) return;

  const rows = visibleRows();
  if (!rows.length) return;

  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    event.preventDefault();
    const step = event.key === "ArrowDown" ? 1 : -1;
    if (state.cursor < 0) state.cursor = 0;
    else state.cursor = Math.min(rows.length - 1, Math.max(0, state.cursor + step));
    renderTable();
    scrollCursorIntoView();
    return;
  }

  if (state.cursor < 0) state.cursor = 0;
  const current = rows[state.cursor];
  if (!current) return;

  const key = event.key.toLowerCase();
  if (key === "a") {
    event.preventDefault();
    decideResult(current.id, "accepted");
  } else if (key === "r") {
    event.preventDefault();
    decideResult(current.id, "rejected");
  } else if (key === "x") {
    event.preventDefault();
    decideResult(current.id, null);
  } else if (event.key === "Enter") {
    event.preventDefault();
    openDrawer(current.id);
  }
}

init();
