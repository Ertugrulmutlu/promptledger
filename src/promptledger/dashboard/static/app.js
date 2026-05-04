const LAYOUT_KEY = "promptledger.dashboard.cardOrder.v1";

const state = {
  allPrompts: [],
  prompts: [],
  facets: {},
  stats: null,
  selectedPrompt: null,
  selectedVersion: null,
  selectedVersionDetail: null,
  versions: [],
  versionDetails: new Map(),
  compareInitialized: false,
  draggedPromptId: null,
  selectedCards: new Set(),
  toastTimer: null,
};

const el = (id) => document.getElementById(id);

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

function formatDate(value) {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function badge(text) {
  const span = document.createElement("span");
  span.className = "badge";
  const lower = text.toLowerCase();
  if (lower.includes("stable")) span.classList.add("badge-stable");
  if (lower.includes("milestone")) span.classList.add("badge-milestone");
  if (lower.startsWith("label:")) span.classList.add("badge-label");
  span.textContent = text;
  return span;
}

function appendBadges(target, items) {
  target.innerHTML = "";
  items.filter(Boolean).forEach((item) => target.append(badge(item)));
}

function showToast(message) {
  const toast = el("toast");
  toast.textContent = message;
  toast.classList.remove("is-hidden");
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => toast.classList.add("is-hidden"), 1700);
}

function setOptions(select, values, label) {
  select.innerHTML = "";
  select.append(new Option(label, ""));
  values.forEach((value) => select.append(new Option(value, value)));
  refreshCustomSelect(select);
}

function enhanceSelect(select) {
  if (select.dataset.enhanced === "true") return;
  select.dataset.enhanced = "true";
  select.classList.add("native-select");
  const wrapper = document.createElement("div");
  wrapper.className = "custom-select";
  wrapper.innerHTML = `
    <button class="custom-select-trigger" type="button">
      <span></span>
      <i></i>
    </button>
    <div class="custom-select-menu"></div>
  `;
  select.parentNode.insertBefore(wrapper, select.nextSibling);
  wrapper.prepend(select);

  const trigger = wrapper.querySelector(".custom-select-trigger");
  trigger.addEventListener("click", () => {
    document.querySelectorAll(".custom-select.open").forEach((item) => {
      if (item !== wrapper) item.classList.remove("open");
    });
    wrapper.classList.toggle("open");
  });
  refreshCustomSelect(select);
}

function refreshCustomSelect(select) {
  if (select.dataset.enhanced !== "true") return;
  const wrapper = select.closest(".custom-select");
  if (!wrapper) return;
  const triggerText = wrapper.querySelector(".custom-select-trigger span");
  const menu = wrapper.querySelector(".custom-select-menu");
  const selected = select.options[select.selectedIndex];
  triggerText.textContent = selected ? selected.textContent : "";
  menu.innerHTML = "";
  [...select.options].forEach((option) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "custom-select-option";
    if (option.value === select.value) item.classList.add("selected");
    item.textContent = option.textContent;
    item.addEventListener("click", () => {
      select.value = option.value;
      wrapper.classList.remove("open");
      refreshCustomSelect(select);
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });
    menu.append(item);
  });
}

function loadLayoutOrder() {
  try {
    const saved = JSON.parse(localStorage.getItem(LAYOUT_KEY) || "{}");
    return saved && typeof saved === "object" ? saved : {};
  } catch {
    return {};
  }
}

function saveLayoutOrder() {
  const order = {};
  state.prompts.forEach((prompt, index) => {
    order[prompt.prompt_id] = index;
  });
  localStorage.setItem(LAYOUT_KEY, JSON.stringify(order));
}

function resetLayout() {
  localStorage.removeItem(LAYOUT_KEY);
  el("sort-mode").value = "updated";
  refreshCustomSelect(el("sort-mode"));
  state.prompts = [...state.prompts].sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  renderBoard();
}

function renderStats(stats) {
  const target = el("stats");
  target.innerHTML = "";
  [
    ["Prompts", stats.prompt_ids],
    ["Versions", stats.versions],
    ["Collections", stats.collections],
    ["Marked", stats.marked_versions],
  ].forEach(([label, value]) => {
    const card = document.createElement("div");
    card.className = "stat-card";
    card.innerHTML = `<strong></strong><span></span>`;
    card.querySelector("strong").textContent = value;
    card.querySelector("span").textContent = label;
    target.append(card);
  });
  el("version-count").textContent = stats.versions;
}

function metadataItems(prompt) {
  return [
    prompt.env && `env: ${prompt.env}`,
    prompt.collection && `collection: ${prompt.collection}`,
    prompt.role && `role: ${prompt.role}`,
    ...prompt.tags.map((tag) => `tag: ${tag}`),
    ...prompt.labels.map((label) => `label: ${label}`),
    ...prompt.markers,
  ];
}

function sortPrompts(prompts) {
  const mode = el("sort-mode").value;
  const items = [...prompts];
  if (mode === "id") {
    return items.sort((a, b) => a.prompt_id.localeCompare(b.prompt_id));
  }
  if (mode === "collection") {
    return items.sort((a, b) => {
      const collectionCompare = (a.collection || "").localeCompare(b.collection || "");
      return collectionCompare || a.prompt_id.localeCompare(b.prompt_id);
    });
  }
  if (mode === "layout") {
    const order = loadLayoutOrder();
    return items.sort((a, b) => {
      const left = order[a.prompt_id] ?? Number.MAX_SAFE_INTEGER;
      const right = order[b.prompt_id] ?? Number.MAX_SAFE_INTEGER;
      return left - right || b.updated_at.localeCompare(a.updated_at);
    });
  }
  return items.sort((a, b) => b.updated_at.localeCompare(a.updated_at));
}

function renderBoard() {
  const board = el("workspace-board");
  board.innerHTML = "";
  state.prompts = sortPrompts(state.prompts);
  el("card-count").textContent = `${state.prompts.length} card${state.prompts.length === 1 ? "" : "s"}`;
  el("workspace-empty").classList.toggle("is-hidden", state.prompts.length > 0);
  el("compare-selected").classList.toggle("is-hidden", state.selectedCards.size !== 2);
  if (!state.prompts.length) return;

  state.prompts.forEach((prompt) => {
    const card = document.createElement("article");
    card.className = "workspace-card";
    card.draggable = true;
    card.tabIndex = 0;
    card.dataset.promptId = prompt.prompt_id;
    if (state.selectedPrompt === prompt.prompt_id) card.classList.add("active");
    if (state.selectedCards.has(prompt.prompt_id)) card.classList.add("selected");
    card.innerHTML = `
      <div class="card-top">
        <label class="card-select" title="Select for compare">
          <input type="checkbox">
          <span></span>
        </label>
        <div>
          <div class="card-kicker"></div>
          <h3></h3>
        </div>
        <div class="card-top-actions">
          <span class="version-pill"></span>
          <button class="card-menu-button" type="button" aria-label="Card actions">...</button>
          <div class="card-action-menu">
            <button type="button" data-action="open">Open</button>
            <button type="button" data-action="copy-prompt">Copy latest prompt</button>
            <button type="button" data-action="copy-command">Copy CLI command</button>
            <button type="button" data-action="stable"></button>
            <button type="button" data-action="milestone"></button>
          </div>
        </div>
      </div>
      <p class="card-preview"></p>
      <div class="card-meta"></div>
      <div class="card-footer">
        <span class="updated"></span>
        <button class="open-button" type="button">Open</button>
      </div>
    `;
    card.querySelector(".card-kicker").textContent = prompt.collection || "Uncollected";
    card.querySelector("h3").textContent = prompt.prompt_id;
    card.querySelector(".version-pill").textContent = `v${prompt.version}`;
    card.querySelector('[data-action="stable"]').textContent = prompt.markers.includes("stable") ? "Remove stable" : "Mark latest as stable";
    card.querySelector('[data-action="milestone"]').textContent = prompt.markers.includes("milestone") ? "Remove milestone" : "Mark latest as milestone";
    card.querySelector(".card-select input").checked = state.selectedCards.has(prompt.prompt_id);
    card.querySelector(".card-preview").textContent = prompt.content_preview || "No preview available.";
    card.querySelector(".updated").textContent = formatDate(prompt.updated_at);
    const meta = card.querySelector(".card-meta");
    [
      prompt.env && prompt.env,
      prompt.role,
      ...prompt.tags.slice(0, 3),
      ...prompt.markers,
    ].filter(Boolean).forEach((item) => meta.append(badge(item)));

    card.addEventListener("click", (event) => {
      if (event.shiftKey) {
        toggleCardSelection(prompt.prompt_id);
        return;
      }
      if (event.target.closest(".card-select, .card-menu-button, .card-action-menu")) return;
      openPrompt(prompt.prompt_id);
    });
    card.addEventListener("keydown", (event) => {
      if (event.key === "Enter") openPrompt(prompt.prompt_id);
    });
    card.querySelector(".card-select input").addEventListener("change", (event) => {
      event.stopPropagation();
      toggleCardSelection(prompt.prompt_id);
    });
    card.querySelector(".card-menu-button").addEventListener("click", (event) => {
      event.stopPropagation();
      document.querySelectorAll(".workspace-card.menu-open").forEach((item) => {
        if (item !== card) item.classList.remove("menu-open");
      });
      card.classList.toggle("menu-open");
    });
    card.querySelector(".card-action-menu").addEventListener("click", async (event) => {
      const action = event.target.dataset.action;
      if (!action) return;
      event.stopPropagation();
      card.classList.remove("menu-open");
      await handleCardAction(action, prompt);
    });
    card.addEventListener("dragstart", (event) => {
      state.draggedPromptId = prompt.prompt_id;
      card.classList.add("dragging");
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", prompt.prompt_id);
    });
    card.addEventListener("dragend", () => {
      state.draggedPromptId = null;
      card.classList.remove("dragging");
      document.querySelectorAll(".workspace-card.drop-target").forEach((item) => item.classList.remove("drop-target"));
    });
    card.addEventListener("dragover", (event) => {
      event.preventDefault();
      if (state.draggedPromptId && state.draggedPromptId !== prompt.prompt_id) {
        card.classList.add("drop-target");
      }
    });
    card.addEventListener("dragleave", () => card.classList.remove("drop-target"));
    card.addEventListener("drop", (event) => {
      event.preventDefault();
      card.classList.remove("drop-target");
      reorderCards(state.draggedPromptId, prompt.prompt_id);
    });
    board.append(card);
  });
}

function reorderCards(sourceId, targetId) {
  if (!sourceId || !targetId || sourceId === targetId) return;
  const sourceIndex = state.prompts.findIndex((prompt) => prompt.prompt_id === sourceId);
  const targetIndex = state.prompts.findIndex((prompt) => prompt.prompt_id === targetId);
  if (sourceIndex < 0 || targetIndex < 0) return;
  const [moved] = state.prompts.splice(sourceIndex, 1);
  state.prompts.splice(targetIndex, 0, moved);
  el("sort-mode").value = "layout";
  refreshCustomSelect(el("sort-mode"));
  saveLayoutOrder();
  renderBoard();
}

function toggleCardSelection(promptId) {
  if (state.selectedCards.has(promptId)) {
    state.selectedCards.delete(promptId);
  } else {
    if (state.selectedCards.size >= 2) {
      const first = state.selectedCards.values().next().value;
      state.selectedCards.delete(first);
    }
    state.selectedCards.add(promptId);
  }
  renderBoard();
}

async function loadLatestPrompt(prompt) {
  return getJson(`/api/prompts/${encodeURIComponent(prompt.prompt_id)}/versions/${prompt.version}`);
}

async function handleCardAction(action, prompt) {
  if (action === "open") {
    await openPrompt(prompt.prompt_id);
    return;
  }
  if (action === "copy-prompt") {
    const latest = await loadLatestPrompt(prompt);
    await copyText(latest.content || "", "Copied prompt");
    return;
  }
  if (action === "copy-command") {
    await copyText(`promptledger add --id ${prompt.prompt_id} --file <path> --quick`, "Copied command");
    return;
  }
  if (action === "stable" || action === "milestone") {
    const present = prompt.markers.includes(action);
    await toggleMarker(prompt.prompt_id, prompt.version, action, !present);
    showToast(present ? `Removed ${action}` : `Marked as ${action}`);
    await refreshDashboardData();
    return;
  }
}

async function toggleMarker(promptId, version, markerName, shouldSet) {
  const method = shouldSet ? "POST" : "DELETE";
  const response = await fetch(
    `/api/prompts/${encodeURIComponent(promptId)}/versions/${version}/markers/${markerName}`,
    { method },
  );
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || `Marker update failed: ${response.status}`);
  }
  return response.json();
}

async function loadVersion(versionNumber) {
  const key = `${state.selectedPrompt}@${versionNumber}`;
  if (!state.versionDetails.has(key)) {
    const data = await getJson(`/api/prompts/${encodeURIComponent(state.selectedPrompt)}/versions/${versionNumber}`);
    state.versionDetails.set(key, data);
  }
  return state.versionDetails.get(key);
}

async function openPrompt(promptId) {
  state.selectedPrompt = promptId;
  state.versionDetails.clear();
  state.compareInitialized = false;
  const data = await getJson(`/api/prompts/${encodeURIComponent(promptId)}/versions`);
  state.versions = data.versions;
  const latest = state.versions[0];
  if (!latest) return;
  renderBoard();
  el("detail-modal").classList.remove("compare-only");
  el("detail-modal").classList.remove("is-hidden");
  await selectVersion(latest.version);
}

function closeModal() {
  el("detail-modal").classList.add("is-hidden");
}

function renderSelectedVersion(version) {
  state.selectedVersionDetail = version;
  el("modal-title").textContent = version.prompt_id;
  el("prompt-subtitle").textContent = version.reason || "No reason recorded";
  el("code-title").textContent = `${version.prompt_id}@v${version.version}`;
  el("prompt-content").textContent = version.content || "(empty prompt text)";
  el("modal-meta").innerHTML = "";
  [
    `version ${version.version}`,
    formatDate(version.created_at),
    version.content_hash && `hash ${version.content_hash.slice(0, 10)}`,
  ].filter(Boolean).forEach((item) => {
    const span = document.createElement("span");
    span.textContent = item;
    el("modal-meta").append(span);
  });
  appendBadges(el("modal-badges"), metadataItems(version));
  appendBadges(el("code-badges"), [
    version.env,
    version.collection,
    version.role,
    ...version.markers,
  ]);
}

function renderTimeline() {
  const target = el("timeline");
  target.innerHTML = "";
  el("timeline-subtitle").textContent = `${state.versions.length} versions, newest first`;
  state.versions.forEach((version, index) => {
    const item = document.createElement("button");
    item.className = "timeline-item";
    if (version.version === state.selectedVersion) item.classList.add("active");
    item.innerHTML = `
      <div class="timeline-main">
        <strong></strong>
        <span class="timeline-date"></span>
      </div>
      <p></p>
      <div class="timeline-badges"></div>
      <div class="timeline-actions">
        <button type="button" data-marker="stable"></button>
        <button type="button" data-marker="milestone"></button>
      </div>
    `;
    item.querySelector("strong").textContent = `Version ${version.version}`;
    item.querySelector(".timeline-date").textContent = formatDate(version.created_at);
    item.querySelector("p").textContent = version.reason || (state.versions.length === 1 ? "First version" : "No reason recorded");
    const badges = item.querySelector(".timeline-badges");
    if (index === 0) badges.append(badge("latest"));
    [...version.markers, ...version.labels.map((label) => `label: ${label}`)]
      .slice(0, 4)
      .forEach((itemText) => badges.append(badge(itemText)));
    item.querySelector('[data-marker="stable"]').textContent = version.markers.includes("stable") ? "Remove stable" : "Mark stable";
    item.querySelector('[data-marker="milestone"]').textContent = version.markers.includes("milestone") ? "Remove milestone" : "Mark milestone";
    item.querySelector(".timeline-actions").addEventListener("click", async (event) => {
      const marker = event.target.dataset.marker;
      if (!marker) return;
      event.stopPropagation();
      const present = version.markers.includes(marker);
      await toggleMarker(version.prompt_id, version.version, marker, !present);
      showToast(present ? `Removed ${marker}` : `Marked as ${marker}`);
      await refreshDashboardData();
    });
    item.addEventListener("click", () => selectVersion(version.version));
    target.append(item);
  });
}

async function selectVersion(versionNumber) {
  state.selectedVersion = versionNumber;
  const version = await loadVersion(versionNumber);
  renderSelectedVersion(version);
  renderTimeline();
  updateCompareOptions();
}

function updateCompareOptions() {
  const left = el("compare-left");
  const right = el("compare-right");
  const previousLeft = left.value;
  const previousRight = right.value;
  left.innerHTML = "";
  right.innerHTML = "";
  state.versions.forEach((version) => {
    left.append(new Option(`${state.selectedPrompt}@v${version.version}`, version.version));
    right.append(new Option(`${state.selectedPrompt}@v${version.version}`, version.version));
  });
  if (!state.compareInitialized) {
    if (state.versions.length > 1) {
      left.value = state.versions[1].version;
      right.value = state.versions[0].version;
    } else if (state.versions.length === 1) {
      left.value = state.versions[0].version;
      right.value = state.versions[0].version;
    }
    state.compareInitialized = true;
  } else {
    left.value = previousLeft || state.selectedVersion;
    right.value = previousRight || state.selectedVersion;
  }
  refreshCustomSelect(left);
  refreshCustomSelect(right);
  renderCompare();
}

function diffLines(leftText, rightText) {
  const leftLines = leftText.split("\n");
  const rightLines = rightText.split("\n");
  const max = Math.max(leftLines.length, rightLines.length);
  const left = [];
  const right = [];
  for (let index = 0; index < max; index += 1) {
    const leftLine = leftLines[index] ?? "";
    const rightLine = rightLines[index] ?? "";
    const changed = leftLine !== rightLine;
    left.push({ text: leftLine, type: changed ? "removed" : "neutral" });
    right.push({ text: rightLine, type: changed ? "added" : "neutral" });
  }
  return { left, right };
}

function renderDiffLine(target, item, index) {
  const row = document.createElement("div");
  row.className = `diff-line diff-${item.type}`;
  const number = document.createElement("span");
  number.className = "diff-number";
  number.textContent = index + 1;
  const text = document.createElement("span");
  text.className = "diff-text";
  text.textContent = item.text || " ";
  row.append(number, text);
  target.append(row);
}

function renderDirectCompare(left, right) {
  el("compare-left-label").textContent = `${left.prompt_id}@v${left.version}`;
  el("compare-right-label").textContent = `${right.prompt_id}@v${right.version}`;
  const diff = diffLines(left.content || "", right.content || "");
  const leftTarget = el("compare-left-text");
  const rightTarget = el("compare-right-text");
  leftTarget.innerHTML = "";
  rightTarget.innerHTML = "";
  diff.left.forEach((item, index) => renderDiffLine(leftTarget, item, index));
  diff.right.forEach((item, index) => renderDiffLine(rightTarget, item, index));
}

async function renderCompare() {
  if (!state.selectedPrompt) return;
  const leftValue = el("compare-left").value;
  const rightValue = el("compare-right").value;
  if (!leftValue || !rightValue) return;
  const left = await loadVersion(Number(leftValue));
  const right = await loadVersion(Number(rightValue));
  renderDirectCompare(left, right);
}

async function openSelectedCompare() {
  if (state.selectedCards.size !== 2) return;
  const selected = [...state.selectedCards]
    .map((promptId) => state.prompts.find((prompt) => prompt.prompt_id === promptId) || state.allPrompts.find((prompt) => prompt.prompt_id === promptId))
    .filter(Boolean);
  if (selected.length !== 2) return;
  const [left, right] = await Promise.all(selected.map((prompt) => loadLatestPrompt(prompt)));
  state.selectedPrompt = null;
  state.selectedVersionDetail = right;
  el("detail-modal").classList.add("compare-only");
  el("detail-modal").classList.remove("is-hidden");
  el("modal-title").textContent = `${left.prompt_id} vs ${right.prompt_id}`;
  el("modal-meta").innerHTML = "";
  [`${left.prompt_id}@v${left.version}`, `${right.prompt_id}@v${right.version}`].forEach((item) => {
    const span = document.createElement("span");
    span.textContent = item;
    el("modal-meta").append(span);
  });
  appendBadges(el("modal-badges"), ["latest versions"]);
  el("compare-left").innerHTML = `<option>${left.prompt_id}@v${left.version}</option>`;
  el("compare-right").innerHTML = `<option>${right.prompt_id}@v${right.version}</option>`;
  refreshCustomSelect(el("compare-left"));
  refreshCustomSelect(el("compare-right"));
  renderDirectCompare(left, right);
}

async function applyFilters() {
  const params = new URLSearchParams();
  [
    ["contains", el("search").value],
    ["collection", el("collection-filter").value],
    ["role", el("role-filter").value],
    ["env", el("env-filter").value],
    ["marker", el("marker-filter").value],
  ].forEach(([name, value]) => {
    if (value) params.set(name, value);
  });
  const data = await getJson(`/api/search?${params.toString()}`);
  const latest = new Map();
  data.results.forEach((result) => {
    const existing = latest.get(result.prompt_id);
    if (!existing || result.version > existing.version) latest.set(result.prompt_id, result);
  });
  state.prompts = [...latest.values()];
  const visibleIds = new Set(state.prompts.map((prompt) => prompt.prompt_id));
  [...state.selectedCards].forEach((promptId) => {
    if (!visibleIds.has(promptId)) state.selectedCards.delete(promptId);
  });
  el("workspace-empty").querySelector("h2").textContent = "No prompts found for this query";
  el("workspace-empty").querySelector("p").textContent = "Try a broader search or clear one of the filters.";
  renderBoard();
}

async function refreshDashboardData() {
  const [prompts, stats] = await Promise.all([getJson("/api/prompts"), getJson("/api/stats")]);
  state.allPrompts = prompts.prompts;
  state.facets = prompts.facets;
  state.stats = stats;
  renderStats(stats);
  await applyFilters();
  if (state.selectedPrompt) {
    const data = await getJson(`/api/prompts/${encodeURIComponent(state.selectedPrompt)}/versions`);
    state.versions = data.versions;
    state.versionDetails.clear();
    if (state.selectedVersion) {
      await selectVersion(state.selectedVersion);
    }
  }
}

async function copyText(text, message = "Copied") {
  if (!navigator.clipboard) {
    showToast("Clipboard unavailable");
    return;
  }
  await navigator.clipboard.writeText(text);
  showToast(message);
}

async function init() {
  const [prompts, stats] = await Promise.all([getJson("/api/prompts"), getJson("/api/stats")]);
  state.allPrompts = prompts.prompts;
  state.prompts = prompts.prompts;
  state.facets = prompts.facets;
  state.stats = stats;
  ["collection-filter", "role-filter", "env-filter", "marker-filter", "sort-mode", "compare-left", "compare-right"].forEach((id) => {
    enhanceSelect(el(id));
  });
  setOptions(el("collection-filter"), state.facets.collections || [], "All collections");
  setOptions(el("role-filter"), state.facets.roles || [], "All roles");
  setOptions(el("env-filter"), state.facets.envs || [], "All envs");
  setOptions(el("marker-filter"), state.facets.markers || [], "All markers");
  renderStats(stats);
  renderBoard();
}

["search", "collection-filter", "role-filter", "env-filter", "marker-filter"].forEach((id) => {
  el(id).addEventListener("input", applyFilters);
  el(id).addEventListener("change", applyFilters);
});
el("sort-mode").addEventListener("change", renderBoard);
el("reset-layout-side").addEventListener("click", resetLayout);
el("compare-selected").addEventListener("click", openSelectedCompare);
el("modal-close").addEventListener("click", closeModal);
el("detail-modal").addEventListener("click", (event) => {
  if (event.target === el("detail-modal")) closeModal();
});
el("compare-left").addEventListener("change", renderCompare);
el("compare-right").addEventListener("change", renderCompare);
el("copy-prompt").addEventListener("click", () => {
  if (state.selectedVersionDetail) copyText(state.selectedVersionDetail.content || "", "Copied prompt");
});
el("copy-command").addEventListener("click", () => {
  const promptId = state.selectedPrompt || state.selectedVersionDetail?.prompt_id;
  if (!promptId) return;
  copyText(`promptledger add --id ${promptId} --file <path> --quick`, "Copied command");
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeModal();
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "c" && !el("detail-modal").classList.contains("is-hidden")) {
    if (state.selectedVersionDetail) {
      event.preventDefault();
      copyText(state.selectedVersionDetail.content || "", "Copied prompt");
    }
  }
  if (event.key === "/" && document.activeElement !== el("search")) {
    event.preventDefault();
    el("search").focus();
  }
});
document.addEventListener("click", (event) => {
  if (event.target.closest(".custom-select")) return;
  document.querySelectorAll(".custom-select.open").forEach((item) => item.classList.remove("open"));
  if (event.target.closest(".card-menu-button, .card-action-menu")) return;
  document.querySelectorAll(".workspace-card.menu-open").forEach((item) => item.classList.remove("menu-open"));
});

init().catch((error) => {
  el("workspace-empty").classList.remove("is-hidden");
  el("workspace-empty").querySelector("h2").textContent = "Dashboard error";
  el("workspace-empty").querySelector("p").textContent = error.message;
});
