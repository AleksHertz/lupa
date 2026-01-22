const uploadForm = document.getElementById("upload-form");
const uploadStatus = document.getElementById("upload-status");
const applyFilters = document.getElementById("apply-filters");
const warehouseSelect = document.getElementById("filter-warehouse");
const topTableBody = document.getElementById("top-table-body");
const topLimitGroup = document.getElementById("top-limit");
const datePreset = document.getElementById("filter-date-preset");
const stockToggle = document.getElementById("toggle-stock");
const companySwitcher = document.getElementById("company-switcher");
const fetchError = document.getElementById("fetch-error");

const BASE_URL = window.BASE_URL ?? "";
const buildUrl = (path) => `${BASE_URL}${path}`;

const kpiSold = document.getElementById("kpi-sold");
const kpiReplenished = document.getElementById("kpi-replenished");
const kpiMaxSold = document.getElementById("kpi-max-sold");
const kpiMaxRepl = document.getElementById("kpi-max-repl");

let lastSeriesParams = null;

function setStatus(message, isError = false) {
  uploadStatus.textContent = message;
  uploadStatus.style.color = isError ? "#b42318" : "#027a48";
}

function setFetchError({ url, status, body }) {
  if (!fetchError) return;
  const preview = body ? body.slice(0, 300) : "—";
  fetchError.textContent = `Ошибка запроса.\nURL: ${url}\nСтатус: ${status ?? "—"}\nОтвет: ${preview}`;
  fetchError.style.display = "block";
}

function clearFetchError() {
  if (!fetchError) return;
  fetchError.textContent = "";
  fetchError.style.display = "none";
}

async function safeFetch(url, options, expectJson = true) {
  console.log("Fetch", url);
  clearFetchError();
  let response;
  try {
    response = await fetch(url, options);
  } catch (error) {
    console.error("Fetch failed", { url, error });
    setFetchError({ url, status: "network", body: error.message });
    return { ok: false, error };
  }

  const contentType = response.headers.get("content-type") || "";
  console.log("Fetch response", {
    url,
    status: response.status,
    contentType,
  });

  if (!response.ok) {
    const body = await response.text();
    console.error("Fetch failed", {
      url,
      status: response.status,
      contentType,
      body,
    });
    setFetchError({ url, status: response.status, body });
    return { ok: false, response, body };
  }

  if (expectJson && !contentType.includes("application/json")) {
    const body = await response.text();
    console.error("Fetch failed", {
      url,
      status: response.status,
      contentType,
      body,
    });
    setFetchError({ url, status: response.status, body });
    return { ok: false, response, body };
  }

  const payload = expectJson ? await response.json() : null;
  return { ok: true, response, payload };
}

function formatDate(value) {
  const year = value.getFullYear();
  const month = `${value.getMonth() + 1}`.padStart(2, "0");
  const day = `${value.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function applyDatePreset(preset) {
  if (!preset) return;
  const today = new Date();
  const dateFrom = document.getElementById("filter-date-from");
  const dateTo = document.getElementById("filter-date-to");
  const end = new Date(today);
  let start = new Date(today);

  if (preset === "7d") {
    start.setDate(start.getDate() - 6);
  } else if (preset === "30d") {
    start.setDate(start.getDate() - 29);
  } else if (preset === "90d") {
    start.setDate(start.getDate() - 89);
  } else if (preset === "month") {
    start = new Date(today.getFullYear(), today.getMonth(), 1);
  }

  dateFrom.value = formatDate(start);
  dateTo.value = formatDate(end);
}

function getSelectedWarehouses() {
  if (!warehouseSelect) return [];
  return Array.from(warehouseSelect.selectedOptions)
    .map((option) => option.value.trim())
    .filter(Boolean);
}

function getTopLimit() {
  const selected = topLimitGroup?.querySelector('input[name="top-limit"]:checked');
  return selected?.value || "100";
}

function getSelectedCompany() {
  return companySwitcher?.value || "";
}

function appendParam(params, key, value) {
  if (value === undefined || value === null) return;
  if (Array.isArray(value)) {
    if (value.length === 0) return;
    const joined = value.join(",");
    if (!joined) return;
    params.append(key, joined);
    return;
  }
  if (typeof value === "string") {
    if (!value.trim()) return;
    params.append(key, value);
    return;
  }
  params.append(key, value);
}

function collectFilters() {
  const sku = document.getElementById("filter-sku").value || "";
  const manufacturer = document.getElementById("filter-manufacturer").value || "";
  const company = getSelectedCompany()?.toLowerCase() || "";
  const project = document.getElementById("filter-project")?.value || "";
  const dateFrom = document.getElementById("filter-date-from").value;
  const dateTo = document.getElementById("filter-date-to").value;
  const warehouses = getSelectedWarehouses();

  return {
    sku,
    manufacturer,
    company,
    project,
    warehouses,
    dateFrom,
    dateTo,
  };
}

function formatNumber(value) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  if (typeof value === "number") {
    return value.toLocaleString("ru-RU");
  }
  return `${value}`;
}

function setSeriesEmptyState(availableRange, onShowAvailable) {
  const chartEl = document.getElementById("chart");
  if (!chartEl) return;
  Plotly.purge(chartEl);
  chartEl.innerHTML = "";

  const wrapper = document.createElement("div");
  wrapper.className = "empty-state";

  const message = document.createElement("p");
  message.textContent = "Нет данных…";
  wrapper.append(message);

  if (availableRange?.min && availableRange?.max) {
    const range = document.createElement("p");
    range.textContent = `Доступный период: ${availableRange.min} — ${availableRange.max}`;
    wrapper.append(range);

    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "Show available period";
    button.addEventListener("click", () => {
      onShowAvailable?.(availableRange.min, availableRange.max);
    });
    wrapper.append(button);
  }

  chartEl.append(wrapper);
}

function renderSeries(payload) {
  const summary = payload?.summary || {};
  const series = Array.isArray(payload?.series) ? payload.series : [];

  kpiSold.textContent = formatNumber(summary.sold_total);
  kpiReplenished.textContent = formatNumber(summary.replenished_total);
  kpiMaxSold.textContent = formatNumber(summary.rank);
  kpiMaxRepl.textContent = "—";

  if (series.length === 0) {
    setSeriesEmptyState(payload?.available_range, (minDate, maxDate) => {
      const dateFromInput = document.getElementById("filter-date-from");
      const dateToInput = document.getElementById("filter-date-to");
      if (dateFromInput) dateFromInput.value = minDate;
      if (dateToInput) dateToInput.value = maxDate;
      if (lastSeriesParams) {
        fetchSeriesWithParams({
          ...lastSeriesParams,
          dateFrom: minDate,
          dateTo: maxDate,
        });
      }
    });
    return;
  }

  const dates = series.map((entry) => entry.date);
  const soldValues = series.map((entry) => entry.sold ?? 0);
  const replenishedValues = series.map((entry) => entry.replenished ?? 0);
  const stockValues = series.map((entry) => entry.stock ?? null);
  const priceValues = series.map((entry) => entry.price ?? null);

  const soldTrace = {
    x: dates,
    y: soldValues,
    name: "Продано",
    type: "bar",
    marker: { color: "#2563eb" },
  };

  const replTrace = {
    x: dates,
    y: replenishedValues,
    name: "Пополнено",
    type: "bar",
    marker: { color: "#16a34a" },
  };

  const traces = [soldTrace, replTrace];

  if (stockToggle?.checked && stockValues.some((value) => value !== null)) {
    traces.push({
      x: dates,
      y: stockValues,
      name: "Остаток",
      yaxis: "y2",
      type: "scatter",
      mode: "lines",
      line: { color: "#0ea5e9", width: 2 },
    });
  }

  if (priceValues.some((value) => value !== null)) {
    traces.push({
      x: dates,
      y: priceValues,
      name: "Цена",
      yaxis: "y3",
      type: "scatter",
      mode: "lines+markers",
      line: { color: "#f97316" },
    });
  }

  const layout = {
    barmode: "group",
    yaxis: { title: "Кол-во" },
    yaxis2: {
      title: "Остаток",
      overlaying: "y",
      side: "right",
    },
    yaxis3: {
      title: "Цена",
      overlaying: "y",
      side: "right",
      position: 1.08,
    },
    margin: { t: 30 },
  };

  Plotly.newPlot("chart", traces, layout, {
    responsive: true,
  });
}

function getUploadMode() {
  const mode = new URLSearchParams(window.location.search).get("mode");
  return mode === "bootstrap" ? "bootstrap" : "reject";
}

uploadForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(uploadForm);
  formData.set("company", getSelectedCompany());
  formData.set("mode", getUploadMode());
  setStatus("Загрузка...", false);
  const result = await safeFetch(buildUrl("/upload"), {
    method: "POST",
    body: formData,
  });
  if (!result.ok) {
    setStatus("Ошибка загрузки. Проверьте блок ошибок.", true);
    return;
  }
  setStatus(`Готово. Снимков: ${result.payload.snapshots}, дельт: ${result.payload.deltas}.`);
});

async function loadWarehouseOptions() {
  if (!warehouseSelect) return;
  const params = new URLSearchParams();
  appendParam(params, "field", "warehouse");
  appendParam(params, "company", getSelectedCompany()?.toLowerCase());
  const result = await safeFetch(buildUrl(`/filters/suggestions?${params.toString()}`));
  if (!result.ok) {
    warehouseSelect.innerHTML = "";
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "Не удалось загрузить список складов";
    option.disabled = true;
    warehouseSelect.append(option);
    return;
  }
  warehouseSelect.innerHTML = "";
  result.payload.items.forEach((item) => {
    const option = document.createElement("option");
    option.value = item;
    option.textContent = item;
    warehouseSelect.append(option);
  });
}

function setAllWarehousesSelected(isSelected) {
  if (!warehouseSelect) return;
  Array.from(warehouseSelect.options).forEach((option) => {
    option.selected = isSelected;
  });
}

function initWarehouseActions() {
  if (!warehouseSelect) return;
  const parent = warehouseSelect.parentElement;
  if (!parent || parent.dataset.actionsInitialized === "true") return;

  const actions = document.createElement("div");
  actions.className = "warehouse-actions";

  const selectAllButton = document.createElement("button");
  selectAllButton.type = "button";
  selectAllButton.textContent = "Select all";
  selectAllButton.addEventListener("click", () => {
    setAllWarehousesSelected(true);
  });

  const clearButton = document.createElement("button");
  clearButton.type = "button";
  clearButton.textContent = "Clear";
  clearButton.addEventListener("click", () => {
    setAllWarehousesSelected(false);
  });

  actions.append(selectAllButton, clearButton);
  warehouseSelect.insertAdjacentElement("afterend", actions);
  parent.dataset.actionsInitialized = "true";
}

async function fetchSeriesWithParams({
  itemId,
  sku,
  manufacturer,
  company,
  project,
  warehouses,
  dateFrom,
  dateTo,
}) {
  if (!dateFrom || !dateTo) {
    return;
  }
  const params = new URLSearchParams();
  appendParam(params, "item_id", itemId);
  appendParam(params, "sku", sku);
  appendParam(params, "warehouses", warehouses);
  appendParam(params, "manufacturer", manufacturer);
  appendParam(params, "company", company);
  appendParam(params, "project", project);
  appendParam(params, "date_from", dateFrom);
  appendParam(params, "date_to", dateTo);
  const result = await safeFetch(buildUrl(`/series?${params.toString()}`));
  if (!result.response?.ok) {
    return;
  }
  lastSeriesParams = {
    itemId,
    sku,
    manufacturer,
    company,
    project,
    warehouses,
    dateFrom,
    dateTo,
  };
  renderSeries(result.payload);
}

async function fetchSeries() {
  const {
    sku,
    manufacturer,
    company,
    project,
    warehouses,
    dateFrom,
    dateTo,
  } = collectFilters();
  await fetchSeriesWithParams({
    sku,
    manufacturer,
    company,
    project,
    warehouses,
    dateFrom,
    dateTo,
  });
}

async function fetchSeriesForItem(item) {
  const { company, warehouses, dateFrom, dateTo } = collectFilters();
  const rowWarehouse =
    item?.warehouse && item.warehouse !== "ALL" ? item.warehouse : null;
  const resolvedWarehouses = rowWarehouse
    ? [rowWarehouse]
    : warehouses.length > 0
      ? warehouses
      : null;
  await fetchSeriesWithParams({
    itemId: item?.item_id,
    company,
    warehouses: resolvedWarehouses,
    dateFrom,
    dateTo,
  });
}

function renderTopTable(items) {
  if (!topTableBody) return;
  topTableBody.innerHTML = "";
  items.forEach((item) => {
    const row = document.createElement("tr");
    if (item.item_id) {
      row.dataset.itemId = item.item_id;
    }
    row.innerHTML = `
      <td>${item.rank ?? "—"}</td>
      <td>${item.sku ?? "—"}</td>
      <td>${item.name ?? "—"}</td>
      <td>${item.manufacturer ?? "—"}</td>
      <td>${item.brand ?? "—"}</td>
      <td>${item.warehouse ?? "ALL"}</td>
      <td>${item.sold_qty ?? "—"}</td>
      <td>${item.replenished_qty ?? "—"}</td>
      <td>${item.last_price ?? "—"}</td>
    `;
    row.addEventListener("click", () => {
      fetchSeriesForItem(item);
    });
    topTableBody.append(row);
  });
}

async function fetchTop() {
  const {
    sku,
    manufacturer,
    company,
    project,
    warehouses,
    dateFrom,
    dateTo,
  } = collectFilters();
  const limit = getTopLimit();

  if (!dateFrom || !dateTo) {
    return;
  }

  const params = new URLSearchParams();
  appendParam(params, "sku", sku);
  appendParam(params, "manufacturer", manufacturer);
  appendParam(params, "company", company);
  appendParam(params, "project", project);
  appendParam(params, "warehouses", warehouses);
  appendParam(params, "date_from", dateFrom);
  appendParam(params, "date_to", dateTo);
  appendParam(params, "limit", limit);
  const url = buildUrl(`/top?${params.toString()}`);
  const result = await safeFetch(url);
  if (!result.response?.ok) {
    let detail = "";
    if (result.body) {
      try {
        detail = JSON.parse(result.body)?.detail || "";
      } catch (error) {
        detail = result.body;
      }
    }
    const fallback = detail || result.error?.message || "Не удалось загрузить данные.";
    setFetchError({
      url,
      status: result.response?.status ?? "network",
      body: fallback,
    });
    renderTopTable([]);
    return;
  }
  const items = Array.isArray(result.payload) ? result.payload : result.payload.items || [];
  renderTopTable(items);
}

applyFilters?.addEventListener("click", (event) => {
  event.preventDefault();
  fetchSeries();
  fetchTop();
});

datePreset?.addEventListener("change", (event) => {
  applyDatePreset(event.target.value);
});

topLimitGroup?.addEventListener("change", () => {
  fetchTop();
});

stockToggle?.addEventListener("change", () => {
  fetchSeries();
});

companySwitcher?.addEventListener("change", () => {
  loadWarehouseOptions();
  fetchSeries();
  fetchTop();
});

loadWarehouseOptions();
initWarehouseActions();
