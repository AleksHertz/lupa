const uploadForm = document.getElementById("upload-form");
const uploadStatus = document.getElementById("upload-status");
const applyFilters = document.getElementById("apply-filters");
const warehouseList = document.getElementById("filter-warehouse");
const warehouseSelectAllButton = document.getElementById("warehouse-select-all");
const warehouseClearButton = document.getElementById("warehouse-clear");
const topTableBody = document.getElementById("top-table-body");
const topLimitGroup = document.getElementById("top-limit");
const topSearchInput = document.getElementById("top-search");
const topPrevButton = document.getElementById("top-prev");
const topNextButton = document.getElementById("top-next");
const topJumpInput = document.getElementById("top-jump-rank");
const topJumpButton = document.getElementById("top-jump-btn");
const datePreset = document.getElementById("filter-date-preset");
const stockToggle = document.getElementById("toggle-stock");
const companySwitcher = document.getElementById("company-switcher");
const fetchError = document.getElementById("fetch-error");

const BASE_URL = window.BASE_URL ?? "";
const buildUrl = (path) => `${BASE_URL}${path}`;
const DEBUG = window.DEBUG === true;

const kpiSold = document.getElementById("kpi-sold");
const kpiReplenished = document.getElementById("kpi-replenished");
const kpiMaxSold = document.getElementById("kpi-max-sold");
const kpiMaxRepl = document.getElementById("kpi-max-repl");

let lastSeriesParams = null;
let lastSeriesPayload = null;
let topItems = [];
let filteredTopItems = [];
let selectedTopKey = null;
let selectedTopIndex = -1;
let warehouseCounts = new Map();

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

function extractErrorMessage(body) {
  if (!body) return "";
  try {
    const parsed = JSON.parse(body);
    if (parsed?.detail !== undefined) {
      if (typeof parsed.detail === "string") return parsed.detail;
      if (parsed.detail?.message) return parsed.detail.message;
      return JSON.stringify(parsed.detail);
    }
    if (parsed?.message) return parsed.message;
    return JSON.stringify(parsed);
  } catch (error) {
    return body;
  }
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
    const errorMessage = extractErrorMessage(body);
    console.error("Fetch failed", {
      url,
      status: response.status,
      contentType,
      body,
    });
    setFetchError({ url, status: response.status, body: errorMessage || body });
    return { ok: false, response, body, errorMessage };
  }

  if (expectJson && !contentType.includes("application/json")) {
    const body = await response.text();
    const errorMessage = extractErrorMessage(body);
    console.error("Fetch failed", {
      url,
      status: response.status,
      contentType,
      body,
    });
    setFetchError({ url, status: response.status, body: errorMessage || body });
    return { ok: false, response, body, errorMessage };
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
  if (!warehouseList) return [];
  return Array.from(warehouseList.querySelectorAll('input[type="checkbox"]:checked'))
    .map((option) => option.value.trim())
    .filter(Boolean);
}

function logSelectedWarehouses() {
  if (!DEBUG) return;
  console.log("selectedWarehouses", getSelectedWarehouses());
}

function getTopLimit() {
  const selected = topLimitGroup?.querySelector('input[name="top-limit"]:checked');
  return selected?.value || "100";
}

function getSelectedCompany() {
  const value = companySwitcher?.value?.trim();
  return value ? value.toLowerCase() : "alliance";
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
    const normalized = key === "company" ? value.toLowerCase() : value;
    if (!normalized.trim()) return;
    params.append(key, normalized);
    return;
  }
  params.append(key, value);
}

function collectFilters() {
  const sku = document.getElementById("filter-sku").value || "";
  const manufacturer = document.getElementById("filter-manufacturer").value || "";
  const company = getSelectedCompany();
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
    return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(value);
  }
  return `${value}`;
}

function formatCurrency(value) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  if (typeof value === "number") {
    return new Intl.NumberFormat("ru-RU", {
      style: "currency",
      currency: "RUB",
      maximumFractionDigits: 2,
    }).format(value);
  }
  return `${value}`;
}

function escapeHtml(value) {
  return `${value}`
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function normalizeText(value) {
  if (value === null || value === undefined) return "";
  return `${value}`.normalize("NFKC").toLowerCase();
}

function getItemKey(item) {
  const itemId = item?.item_id ?? "unknown";
  const warehouse = item?.warehouse ?? "ALL";
  return `${itemId}::${warehouse}`;
}

function buildWarehouseCounts(items) {
  const counts = new Map();
  items.forEach((item) => {
    if (!item?.item_id) return;
    const warehouse = item?.warehouse ?? "ALL";
    const entry = counts.get(item.item_id) ?? new Set();
    entry.add(warehouse);
    counts.set(item.item_id, entry);
  });
  return counts;
}

function hasMultipleWarehouses(item) {
  if (!item?.item_id) return false;
  return (warehouseCounts.get(item.item_id)?.size ?? 0) > 1;
}

function getWarehouseLabel(item) {
  return item?.warehouse ?? "ALL";
}

function updateSelectionIndex() {
  if (!selectedTopKey) {
    selectedTopIndex = -1;
    return;
  }
  selectedTopIndex = filteredTopItems.findIndex(
    (item) => getItemKey(item) === selectedTopKey
  );
}

function updateNavButtons() {
  if (!topPrevButton || !topNextButton) return;
  if (filteredTopItems.length === 0) {
    topPrevButton.disabled = true;
    topNextButton.disabled = true;
    return;
  }
  topPrevButton.disabled = selectedTopIndex <= 0;
  topNextButton.disabled =
    selectedTopIndex < 0 || selectedTopIndex >= filteredTopItems.length - 1;
}

function scrollToSelectedRow() {
  if (!topTableBody || !selectedTopKey) return;
  const selector = `tr[data-key="${window.CSS?.escape
    ? window.CSS.escape(selectedTopKey)
    : selectedTopKey.replaceAll('"', '\\"')}"]`;
  const row = topTableBody.querySelector(selector);
  if (row) {
    row.scrollIntoView({ block: "nearest" });
  }
}

function applyTopFilter() {
  const query = normalizeText(topSearchInput?.value || "");
  if (!query) {
    filteredTopItems = [...topItems];
  } else {
    filteredTopItems = topItems.filter((item) => {
      const sku = normalizeText(item?.canonical_sku || item?.sku || "");
      const name = normalizeText(item?.name || "");
      return sku.includes(query) || name.includes(query);
    });
  }
  updateSelectionIndex();
  renderTopTable(filteredTopItems);
  if (selectedTopIndex >= 0) {
    scrollToSelectedRow();
  }
  updateNavButtons();
}

function setSelectedItem(item, options = {}) {
  if (!item) return;
  selectedTopKey = getItemKey(item);
  updateSelectionIndex();
  renderTopTable(filteredTopItems);
  if (options.scroll !== false) {
    scrollToSelectedRow();
  }
  if (options.fetch !== false) {
    fetchSeriesForItem(item);
  }
  updateNavButtons();
}

function moveSelection(offset) {
  if (filteredTopItems.length === 0) return;
  if (selectedTopIndex < 0) {
    const index = offset > 0 ? 0 : filteredTopItems.length - 1;
    setSelectedItem(filteredTopItems[index]);
    return;
  }
  const nextIndex = selectedTopIndex + offset;
  if (nextIndex < 0 || nextIndex >= filteredTopItems.length) return;
  setSelectedItem(filteredTopItems[nextIndex]);
}

function jumpToRank(rankValue) {
  const rank = Number.parseInt(rankValue, 10);
  if (!Number.isFinite(rank)) return;
  const target = filteredTopItems.find((item) => Number(item.rank) === rank);
  if (!target) return;
  setSelectedItem(target);
}

function setSeriesEmptyState(availableRange, onShowAvailable) {
  const chartEl = document.getElementById("chart");
  if (!chartEl) return;
  Plotly.purge(chartEl);
  chartEl.innerHTML = "";

  const wrapper = document.createElement("div");
  wrapper.className = "empty-state";

  const message = document.createElement("p");
  if (availableRange?.min && availableRange?.max) {
    message.textContent = `Нет данных за период. Доступно: ${availableRange.min}..${availableRange.max}`;
  } else {
    message.textContent = "Нет данных за период.";
  }
  wrapper.append(message);

  if (availableRange?.min && availableRange?.max) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "Показать доступный период";
    button.addEventListener("click", () => {
      onShowAvailable?.(availableRange.min, availableRange.max);
    });
    wrapper.append(button);
  }

  chartEl.append(wrapper);
}

function ensureDetailedToggle() {
  const existing = document.getElementById("toggle-detailed");
  if (existing) return existing;

  const filters = document.querySelector(".filters");
  if (!filters) return null;

  const label = document.createElement("label");
  label.className = "inline";

  const span = document.createElement("span");
  span.textContent = "Detailed by warehouse";

  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.id = "toggle-detailed";

  label.append(span, checkbox);

  const stockLabel = document.querySelector('label.inline input#toggle-stock')?.parentElement;
  if (stockLabel) {
    stockLabel.insertAdjacentElement("afterend", label);
  } else {
    filters.append(label);
  }

  checkbox.addEventListener("change", () => {
    if (lastSeriesPayload) {
      renderSeries(lastSeriesPayload);
    }
  });

  return checkbox;
}

function buildSeriesByWarehouse(series) {
  const byWarehouse = new Map();
  const datesSet = new Set();

  series.forEach((entry) => {
    if (!entry?.date) return;
    const warehouse = entry.warehouse ?? "ALL";
    const date = entry.date;
    datesSet.add(date);

    const warehouseMap = byWarehouse.get(warehouse) ?? new Map();
    const existing = warehouseMap.get(date) ?? {
      sold: 0,
      replenished: 0,
      stock: null,
      price: null,
    };
    const replValue =
      entry.repl !== undefined && entry.repl !== null ? entry.repl : entry.replenished ?? 0;

    existing.sold += entry.sold ?? 0;
    existing.replenished += replValue;
    if (entry.stock !== null && entry.stock !== undefined) {
      existing.stock = entry.stock;
    }
    if (entry.price !== null && entry.price !== undefined) {
      existing.price = entry.price;
    }

    warehouseMap.set(date, existing);
    byWarehouse.set(warehouse, warehouseMap);
  });

  const dates = Array.from(datesSet).sort();
  return { dates, byWarehouse };
}

function buildWarehouseTimeline(warehouseMap, dates) {
  const sold = [];
  const replenished = [];
  const stock = [];
  const price = [];
  let lastStock = null;

  dates.forEach((date) => {
    const entry = warehouseMap.get(date);
    const soldValue = entry?.sold ?? 0;
    const replValue = entry?.replenished ?? 0;
    const stockValue = entry?.stock ?? null;
    const priceValue = entry?.price ?? null;

    if (stockValue !== null) {
      lastStock = stockValue;
    }

    sold.push(soldValue);
    replenished.push(replValue);
    stock.push(stockValue !== null ? stockValue : lastStock);
    price.push(priceValue);
  });

  return { sold, replenished, stock, price };
}

function buildHoverCustomData({ dates, warehouse, stock, sold, replenished, price }) {
  return dates.map((date, index) => [
    warehouse ?? "ALL",
    formatNumber(stock[index]),
    formatNumber(sold[index]),
    formatNumber(replenished[index]),
    formatCurrency(price[index]),
    date,
  ]);
}

function buildHoverTemplate() {
  return (
    "Дата: %{customdata[5]}<br>" +
    "Склад: %{customdata[0]}<br>" +
    "Остаток: %{customdata[1]}<br>" +
    "Продано: %{customdata[2]}<br>" +
    "Пополнено: %{customdata[3]}<br>" +
    "Цена: %{customdata[4]}<extra></extra>"
  );
}

function createWarehouseColors(count) {
  const base = [
    "#2563eb",
    "#16a34a",
    "#0ea5e9",
    "#f97316",
    "#7c3aed",
    "#db2777",
    "#facc15",
  ];
  const colors = [];
  for (let index = 0; index < count; index += 1) {
    colors.push(base[index % base.length]);
  }
  return colors;
}

function renderSeries(payload) {
  const summary = payload?.summary || {};
  const series = Array.isArray(payload?.series) ? payload.series : [];
  lastSeriesPayload = payload;
  const detailedToggle = ensureDetailedToggle();

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

  const { dates, byWarehouse } = buildSeriesByWarehouse(series);
  const warehouses = Array.from(byWarehouse.keys());
  const hasMultipleWarehouses = warehouses.length > 1;
  const showDetailed = Boolean(detailedToggle?.checked && hasMultipleWarehouses);
  if (DEBUG) {
    console.log("seriesSummary", {
      seriesSize: series.length,
      warehouseCount: warehouses.length,
    });
  }
  const hoverTemplate = buildHoverTemplate();
  const traces = [];
  const colors = createWarehouseColors(warehouses.length);

  const aggregated = {
    sold: Array(dates.length).fill(0),
    replenished: Array(dates.length).fill(0),
    stock: Array(dates.length).fill(0),
    price: Array(dates.length).fill(null),
  };
  const aggregatedPriceSum = Array(dates.length).fill(0);
  const aggregatedPriceCount = Array(dates.length).fill(0);

  warehouses.forEach((warehouse, index) => {
    const warehouseMap = byWarehouse.get(warehouse) ?? new Map();
    const timeline = buildWarehouseTimeline(warehouseMap, dates);
    const customData = buildHoverCustomData({
      dates,
      warehouse,
      stock: timeline.stock,
      sold: timeline.sold,
      replenished: timeline.replenished,
      price: timeline.price,
    });

    for (let i = 0; i < dates.length; i += 1) {
      aggregated.sold[i] += timeline.sold[i];
      aggregated.replenished[i] += timeline.replenished[i];
      if (timeline.stock[i] !== null && timeline.stock[i] !== undefined) {
        aggregated.stock[i] += timeline.stock[i];
      }
      if (timeline.price[i] !== null && timeline.price[i] !== undefined) {
        aggregatedPriceSum[i] += timeline.price[i];
        aggregatedPriceCount[i] += 1;
      }
    }

    if (stockToggle?.checked && timeline.stock.some((value) => value !== null)) {
      traces.push({
        x: dates,
        y: timeline.stock,
        name: hasMultipleWarehouses ? `Остаток — ${warehouse}` : "Остаток",
        yaxis: "y",
        type: "scatter",
        mode: "lines",
        connectgaps: true,
        line: { color: colors[index], width: 2 },
        customdata: customData,
        hovertemplate: hoverTemplate,
      });
    }

    if (timeline.price.some((value) => value !== null)) {
      const changeMarkers = timeline.price.map((value, i) => {
        if (value === null || value === undefined) return null;
        if (i === 0) return value;
        const prev = timeline.price[i - 1];
        return prev !== value ? value : null;
      });

      traces.push({
        x: dates,
        y: timeline.price,
        name: hasMultipleWarehouses ? `Цена — ${warehouse}` : "Цена",
        yaxis: "y3",
        type: "scatter",
        mode: "lines",
        connectgaps: true,
        line: { color: "#f97316", width: 1 },
        customdata: customData,
        hovertemplate: hoverTemplate,
        showlegend: !hasMultipleWarehouses,
      });

      traces.push({
        x: dates,
        y: changeMarkers,
        name: hasMultipleWarehouses ? `Изменение цены — ${warehouse}` : "Изменение цены",
        yaxis: "y3",
        type: "scatter",
        mode: "markers",
        marker: { color: "#f97316", size: 6, symbol: "circle" },
        customdata: customData,
        hovertemplate: hoverTemplate,
        showlegend: false,
      });
    }

    if (showDetailed) {
      traces.push({
        x: dates,
        y: timeline.sold,
        name: `Продано — ${warehouse}`,
        type: "bar",
        yaxis: "y2",
        marker: { color: colors[index] },
        customdata: customData,
        hovertemplate: hoverTemplate,
      });

      traces.push({
        x: dates,
        y: timeline.replenished,
        name: `Пополнено — ${warehouse}`,
        type: "bar",
        yaxis: "y2",
        marker: { color: colors[index], opacity: 0.45 },
        customdata: customData,
        hovertemplate: hoverTemplate,
      });
    }
  });

  if (!showDetailed) {
    aggregated.price = aggregatedPriceSum.map((sum, index) =>
      aggregatedPriceCount[index] > 0 ? sum / aggregatedPriceCount[index] : null
    );
    const aggregateWarehouse = hasMultipleWarehouses ? "ALL" : warehouses[0] ?? "ALL";
    const customData = buildHoverCustomData({
      dates,
      warehouse: aggregateWarehouse,
      stock: aggregated.stock,
      sold: aggregated.sold,
      replenished: aggregated.replenished,
      price: aggregated.price,
    });

    traces.push({
      x: dates,
      y: aggregated.sold,
      name: "Продано",
      type: "bar",
      yaxis: "y2",
      marker: { color: "#2563eb" },
      customdata: customData,
      hovertemplate: hoverTemplate,
    });

    traces.push({
      x: dates,
      y: aggregated.replenished,
      name: "Пополнено",
      type: "bar",
      yaxis: "y2",
      marker: { color: "#16a34a" },
      customdata: customData,
      hovertemplate: hoverTemplate,
    });
  }

  const layout = {
    barmode: "group",
    yaxis: { title: "Остаток" },
    yaxis2: {
      title: "Продажи/пополнения",
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
  if (!warehouseList) return;
  const params = new URLSearchParams();
  appendParam(params, "field", "warehouse");
  appendParam(params, "company", getSelectedCompany());
  const result = await safeFetch(buildUrl(`/filters/suggestions?${params.toString()}`));
  if (!result.ok) {
    warehouseList.innerHTML = "";
    const message = document.createElement("div");
    message.className = "warehouse-empty";
    message.textContent = "Не удалось загрузить список складов";
    warehouseList.append(message);
    return;
  }
  warehouseList.innerHTML = "";
  result.payload.items.forEach((item) => {
    const label = document.createElement("label");
    label.className = "warehouse-option";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = item;
    checkbox.addEventListener("change", () => {
      label.classList.toggle("is-selected", checkbox.checked);
      logSelectedWarehouses();
    });

    const text = document.createElement("span");
    text.textContent = item;

    label.append(checkbox, text);
    warehouseList.append(label);
  });
}

function setAllWarehousesSelected(isSelected) {
  if (!warehouseList) return;
  Array.from(warehouseList.querySelectorAll('input[type="checkbox"]')).forEach((checkbox) => {
    checkbox.checked = isSelected;
    const label = checkbox.closest(".warehouse-option");
    if (label) {
      label.classList.toggle("is-selected", isSelected);
    }
  });
}

function initWarehouseActions() {
  if (!warehouseList) return;
  if (warehouseSelectAllButton) {
    warehouseSelectAllButton.addEventListener("click", () => {
      setAllWarehousesSelected(true);
      logSelectedWarehouses();
    });
  }
  if (warehouseClearButton) {
    warehouseClearButton.addEventListener("click", () => {
      setAllWarehousesSelected(false);
      logSelectedWarehouses();
    });
  }
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
  const resolvedCompany = company || getSelectedCompany();
  const params = new URLSearchParams();
  appendParam(params, "item_id", itemId);
  appendParam(params, "sku", sku);
  appendParam(params, "warehouses", warehouses);
  appendParam(params, "manufacturer", manufacturer);
  appendParam(params, "company", resolvedCompany);
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
    company: resolvedCompany,
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
    item?.warehouse && item.warehouse !== "ALL" && !hasMultipleWarehouses(item)
      ? item.warehouse
      : null;
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
    const key = getItemKey(item);
    const row = document.createElement("tr");
    row.dataset.key = key;
    if (item.item_id) {
      row.dataset.itemId = item.item_id;
    }
    if (key === selectedTopKey) {
      row.classList.add("is-selected");
    }
    const nameValue = item.name ?? "—";
    const nameLabel = escapeHtml(nameValue);
    row.innerHTML = `
      <td>${item.rank ?? "—"}</td>
      <td>${escapeHtml(item.canonical_sku ?? "—")}</td>
      <td>
        <span class="cell-ellipsis" title="${nameLabel}">
          ${nameLabel}
        </span>
      </td>
      <td>${getWarehouseLabel(item)}</td>
      <td>${escapeHtml(item.group_name ?? "—")}</td>
      <td>${formatNumber(item.sold_total)}</td>
      <td>${formatNumber(item.replenished_total)}</td>
      <td>${formatCurrency(item.last_price)}</td>
    `;
    row.addEventListener("click", () => {
      setSelectedItem(item);
    });
    topTableBody.append(row);
  });
  updateNavButtons();
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
    renderTopTable([]);
    return;
  }
  const items = Array.isArray(result.payload) ? result.payload : result.payload.items || [];
  topItems = items;
  warehouseCounts = buildWarehouseCounts(items);
  applyTopFilter();
  if (selectedTopIndex >= 0) {
    fetchSeriesForItem(filteredTopItems[selectedTopIndex]);
  }
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

topSearchInput?.addEventListener("input", () => {
  applyTopFilter();
});

topPrevButton?.addEventListener("click", () => {
  moveSelection(-1);
});

topNextButton?.addEventListener("click", () => {
  moveSelection(1);
});

topJumpButton?.addEventListener("click", () => {
  jumpToRank(topJumpInput?.value || "");
});

topJumpInput?.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    jumpToRank(topJumpInput?.value || "");
  }
});

stockToggle?.addEventListener("change", () => {
  if (lastSeriesPayload) {
    renderSeries(lastSeriesPayload);
  } else {
    fetchSeries();
  }
});

companySwitcher?.addEventListener("change", () => {
  loadWarehouseOptions();
  fetchSeries();
  fetchTop();
});

loadWarehouseOptions();
initWarehouseActions();
ensureDetailedToggle();
