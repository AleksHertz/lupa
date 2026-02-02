const DEBUG = true;

const uploadForm = document.getElementById("upload-form");
const uploadStatus = document.getElementById("upload-status");
const applyFilters = document.getElementById("apply-filters");
const warehouseList = document.getElementById("filter-warehouse");
const warehouseSelectAllButton = document.getElementById("warehouse-select-all");
const warehouseClearButton = document.getElementById("warehouse-clear");
const topTableBody = document.getElementById("top-table-body");
const topSearchInput = document.getElementById("top-search");
const topPagePrevButton = document.getElementById("top-page-prev");
const topPageNextButton = document.getElementById("top-page-next");
const topPageNumberInput = document.getElementById("top-page-number");
const topPageSizeSelect = document.getElementById("top-page-size");
const topPageTotal = document.getElementById("top-page-total");
const datePreset = document.getElementById("filter-date-preset");
const stockToggle = document.getElementById("toggle-stock");
const sumWarehouseToggle = document.getElementById("toggle-sum-warehouses");
const companySwitcher = document.getElementById("company-switcher");
const fetchError = document.getElementById("fetch-error");
const latestLoadedBadge = document.getElementById("latest-loaded-date");
const chartSection = document.getElementById("chartSection");
const detailSku = document.getElementById("detail-sku");
const detailName = document.getElementById("detail-name");
const detailManufacturer = document.getElementById("detail-manufacturer");
const detailWarehouses = document.getElementById("detail-warehouses");
const seriesDebug = document.getElementById("series-debug");
const seriesDebugUrl = document.getElementById("series-debug-url");
const seriesDebugStatus = document.getElementById("series-debug-status");
const seriesDebugCount = document.getElementById("series-debug-count");
const seriesDebugSample = document.getElementById("series-debug-sample");

const BASE_URL = window.BASE_URL ?? "";
const buildUrl = (path) => `${BASE_URL}${path}`;
const ALL_WAREHOUSES_LABEL = "ВСЕ";
const kpiSold = document.getElementById("kpi-sold");
const kpiReplenished = document.getElementById("kpi-replenished");
const kpiRank = document.getElementById("kpi-rank");
const kpiStock = document.getElementById("kpi-stock");
const kpiPrice = document.getElementById("kpi-price");
const kpiWarehouses = document.getElementById("kpi-warehouses");
const kpiLatestDate = document.getElementById("kpi-latest-date");

let lastSeriesParams = null;
let lastSeriesPayload = null;
let lastSelectedItem = null;
let topItems = [];
let filteredTopItems = [];
let selectedTopKey = null;
let selectedTopIndex = -1;
let topPage = 1;
let topPageSize = 30;
let topTotalPages = 1;
let topGroupByWarehouse = true;
let latestLoadedLogged = false;

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

function updateSeriesDebugPanel({ url, status, points }) {
  if (!seriesDebug) return;
  if (seriesDebugUrl) {
    seriesDebugUrl.textContent = url || "—";
  }
  if (seriesDebugStatus) {
    seriesDebugStatus.textContent = status ?? "—";
  }
  if (seriesDebugCount) {
    seriesDebugCount.textContent = `${points?.length ?? 0}`;
  }
  if (seriesDebugSample) {
    const sample = Array.isArray(points) ? points.slice(0, 3) : [];
    seriesDebugSample.textContent =
      sample.length > 0 ? JSON.stringify(sample, null, 2) : "—";
  }
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
  if (DEBUG) {
    console.log("Fetch", url);
  }
  clearFetchError();
  let response;
  try {
    response = await fetch(url, options);
  } catch (error) {
    if (DEBUG) {
      console.error("Fetch failed", { url, error });
    }
    setFetchError({ url, status: "network", body: error.message });
    return { ok: false, error };
  }

  const contentType = response.headers.get("content-type") || "";
  if (DEBUG) {
    console.log("Fetch response", {
      url,
      status: response.status,
      contentType,
    });
  }

  if (!response.ok) {
    const body = await response.text();
    const errorMessage = extractErrorMessage(body);
    if (DEBUG) {
      console.error("Fetch failed", {
        url,
        status: response.status,
        contentType,
        body,
      });
    }
    setFetchError({ url, status: response.status, body: errorMessage || body });
    return { ok: false, response, body, errorMessage };
  }

  if (expectJson && !contentType.includes("application/json")) {
    const body = await response.text();
    const errorMessage = extractErrorMessage(body);
    if (DEBUG) {
      console.error("Fetch failed", {
        url,
        status: response.status,
        contentType,
        body,
      });
    }
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

function fmtDateRu(iso) {
  if (!iso) return "—";
  if (iso instanceof Date) {
    return formatDate(iso).split("-").reverse().join(".");
  }
  const normalized = `${iso}`.split("T")[0];
  const parts = normalized.split("-");
  if (parts.length !== 3) return `${iso}`;
  const [year, month, day] = parts;
  if (!year || !month || !day) return `${iso}`;
  return `${day}.${month}.${year}`;
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
  const selectedWarehouses = getSelectedWarehouses();
  if (DEBUG) {
    console.log("selectedWarehouses", selectedWarehouses);
  }
  updateSumWarehouseToggle(selectedWarehouses);
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

function updateLatestLoadedBadge(latestDate) {
  if (!latestLoadedBadge) return;
  const formattedDate = latestDate ? fmtDateRu(latestDate) : "—";
  latestLoadedBadge.textContent = `Последняя загруженная дата: ${formattedDate}`;
  if (DEBUG && !latestLoadedLogged && latestDate) {
    console.log("latestLoadedDateFormatted", { latestDate, formattedDate });
    latestLoadedLogged = true;
  }
  if (kpiLatestDate) {
    kpiLatestDate.textContent = formattedDate;
  }
}

function updateChartDetails({ item, warehousesLabel }) {
  const resolvedItem = item || lastSelectedItem;
  if (detailSku) {
    detailSku.textContent = `Артикул: ${resolvedItem?.canonical_sku ?? "—"}`;
  }
  if (detailName) {
    detailName.textContent = `Наименование: ${resolvedItem?.name ?? "—"}`;
  }
  if (detailManufacturer) {
    detailManufacturer.textContent = `Производитель: ${resolvedItem?.manufacturer ?? "—"}`;
  }
  if (detailWarehouses) {
    detailWarehouses.textContent = `Склады: ${warehousesLabel || "—"}`;
  }
}

function updatePaginationControls(totalCount) {
  topTotalPages = Math.max(1, Math.ceil(totalCount / topPageSize));
  if (topPage > topTotalPages) {
    topPage = topTotalPages;
  }
  if (topPageNumberInput) {
    topPageNumberInput.value = `${Math.min(topPage, topTotalPages)}`;
    topPageNumberInput.max = `${topTotalPages}`;
  }
  if (topPageTotal) {
    topPageTotal.textContent = `из ${topTotalPages}`;
  }
  if (topPagePrevButton) {
    topPagePrevButton.disabled = topPage <= 1;
  }
  if (topPageNextButton) {
    topPageNextButton.disabled = topPage >= topTotalPages;
  }
}

function updateSumWarehouseToggle(warehouses) {
  if (!sumWarehouseToggle) return;
  const hasMultiple = (warehouses?.length ?? 0) > 1;
  sumWarehouseToggle.disabled = !hasMultiple;
  if (!hasMultiple) {
    sumWarehouseToggle.checked = false;
  }
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

function getWarehouseLabel(item) {
  if (!topGroupByWarehouse) return ALL_WAREHOUSES_LABEL;
  return item?.warehouse ?? ALL_WAREHOUSES_LABEL;
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
}

function setSelectedItem(item, options = {}) {
  if (!item) return;
  lastSelectedItem = item;
  if (DEBUG) {
    const { warehouses, dateFrom, dateTo, company } = collectFilters();
    console.debug("selected row", {
      itemId: item?.item_id,
      sku: item?.canonical_sku ?? item?.sku,
      rank: item?.rank,
      company,
      warehouses,
      dateFrom,
      dateTo,
    });
  }
  selectedTopKey = getItemKey(item);
  updateSelectionIndex();
  renderTopTable(filteredTopItems);
  if (options.scroll !== false) {
    scrollToSelectedRow();
  }
  if (chartSection) {
    chartSection.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  if (options.fetch !== false) {
    fetchSeriesForItem(item);
  }
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
    message.textContent = `Нет данных за выбранный период. Доступно: ${fmtDateRu(
      availableRange.min
    )}..${fmtDateRu(availableRange.max)}`;
  } else {
    message.textContent = "Нет данных за выбранный период.";
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

function setChartLoadingState() {
  const chartEl = document.getElementById("chart");
  if (!chartEl) return;
  Plotly.purge(chartEl);
  chartEl.innerHTML = "<div class=\"empty-state\"><p>Загрузка графика…</p></div>";
}

function setChartErrorState({ status, body }) {
  const chartEl = document.getElementById("chart");
  if (!chartEl) return;
  Plotly.purge(chartEl);
  const statusLabel = status ?? "—";
  const details = body ? ` (${escapeHtml(body)})` : "";
  chartEl.innerHTML = `<div class="empty-state"><p>Ошибка загрузки графика. Статус: ${statusLabel}${details}</p></div>`;
}

function setChartPlaceholder() {
  const chartEl = document.getElementById("chart");
  if (!chartEl) return;
  Plotly.purge(chartEl);
  chartEl.innerHTML =
    "<div class=\"empty-state\"><p>Выберите позицию в таблице для отображения графика.</p></div>";
}

function extractSeries(payload) {
  if (!payload || !Array.isArray(payload.series)) return [];
  return payload.series;
}

function normalizeSeriesPoints(points) {
  if (!Array.isArray(points)) return [];
  return points
    .map((entry) => {
      if (!entry?.date || !entry?.warehouse) return null;
      return {
        date: `${entry.date}`,
        warehouse: `${entry.warehouse}`,
        stock_qty:
          entry.stock_qty === null || entry.stock_qty === undefined
            ? null
            : Number(entry.stock_qty),
        price:
          entry.price === null || entry.price === undefined ? null : Number(entry.price),
        sold_qty: Number(entry.sold_qty ?? 0),
        replenished_qty: Number(entry.replenished_qty ?? 0),
      };
    })
    .filter((entry) => entry);
}

function buildSeriesByWarehouse(points) {
  const byWarehouse = new Map();
  const datesSet = new Set();

  points.forEach((entry) => {
    const warehouse = entry.warehouse ?? ALL_WAREHOUSES_LABEL;
    const date = entry.date;
    datesSet.add(date);

    const warehouseMap = byWarehouse.get(warehouse) ?? new Map();
    warehouseMap.set(date, entry);
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

  dates.forEach((date) => {
    const entry = warehouseMap.get(date);
    sold.push(entry?.sold_qty ?? 0);
    replenished.push(entry?.replenished_qty ?? 0);
    stock.push(entry?.stock_qty ?? null);
    price.push(entry?.price ?? null);
  });

  return { sold, replenished, stock, price };
}

function buildHoverCustomData({ dates, warehouse, stock, sold, replenished, price }) {
  return dates.map((date, index) => [
    warehouse ?? ALL_WAREHOUSES_LABEL,
    formatNumber(stock[index]),
    formatNumber(sold[index]),
    formatNumber(replenished[index]),
    formatCurrency(price[index]),
    fmtDateRu(date),
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
    "#14b8a6",
    "#f43f5e",
    "#84cc16",
  ];
  const colors = [];
  for (let index = 0; index < count; index += 1) {
    colors.push(base[index % base.length]);
  }
  return colors;
}

function renderSeries(payload) {
  const rawSeries = extractSeries(payload);
  const points = normalizeSeriesPoints(rawSeries);
  lastSeriesPayload = payload;

  const warehousesFromPayload = Array.isArray(payload?.warehouses)
    ? payload.warehouses
    : [];
  const selectedWarehouses =
    warehousesFromPayload.length > 0
      ? warehousesFromPayload
      : lastSeriesParams?.warehouses && lastSeriesParams.warehouses.length > 0
        ? lastSeriesParams.warehouses
        : getSelectedWarehouses();
  const warehousesLabel =
    selectedWarehouses.length > 0 ? selectedWarehouses.join(", ") : ALL_WAREHOUSES_LABEL;
  updateChartDetails({ item: lastSelectedItem, warehousesLabel });

  if (kpiRank) {
    kpiRank.textContent = formatNumber(lastSelectedItem?.rank);
  }
  const soldTotal = points.reduce((sum, entry) => sum + (entry.sold_qty || 0), 0);
  const replenishedTotal = points.reduce(
    (sum, entry) => sum + (entry.replenished_qty || 0),
    0
  );
  kpiSold.textContent = formatNumber(soldTotal);
  kpiReplenished.textContent = formatNumber(replenishedTotal);

  if (rawSeries.length === 0) {
    if (kpiStock) kpiStock.textContent = "—";
    if (kpiPrice) kpiPrice.textContent = "—";
    if (kpiWarehouses) kpiWarehouses.textContent = "—";
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

  if (points.length === 0) {
    if (DEBUG) {
      console.debug("SERIES RESPONSE", payload);
      console.debug("SERIES LENGTH", rawSeries.length);
      console.debug("FIRST POINT", rawSeries?.[0]);
    }
    setChartErrorState({
      status: "—",
      body: "Данные серии не распознаны. Проверьте схему ответа.",
    });
    return;
  }

  if (DEBUG) {
    console.debug("series keys", Object.keys(payload || {}));
    console.debug("series first row", points[0]);
  }

  const { dates, byWarehouse } = buildSeriesByWarehouse(points);
  const warehouses = Array.from(byWarehouse.keys());
  const hasMultipleWarehouses = warehouses.length > 1;
  const sumWarehouses = Boolean(sumWarehouseToggle?.checked && hasMultipleWarehouses);
  const showPerWarehouse = !sumWarehouses;
  if (DEBUG) {
    console.log("seriesSummary", {
      seriesSize: points.length,
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
  const warehouseTimelines = new Map();

  warehouses.forEach((warehouse, index) => {
    const warehouseMap = byWarehouse.get(warehouse) ?? new Map();
    const timeline = buildWarehouseTimeline(warehouseMap, dates);
    warehouseTimelines.set(warehouse, timeline);

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

    const customData = buildHoverCustomData({
      dates,
      warehouse,
      stock: timeline.stock,
      sold: timeline.sold,
      replenished: timeline.replenished,
      price: timeline.price,
    });

    if (showPerWarehouse && stockToggle?.checked) {
      traces.push({
        x: dates,
        y: timeline.stock,
        name: `Остаток — ${warehouse}`,
        yaxis: "y",
        type: "scatter",
        mode: "lines",
        connectgaps: true,
        line: { color: colors[index], width: 2 },
        customdata: customData,
        hovertemplate: hoverTemplate,
      });
    }
  });

  aggregated.price = aggregatedPriceSum.map((sum, index) =>
    aggregatedPriceCount[index] > 0 ? sum / aggregatedPriceCount[index] : null
  );
  const aggregateCustomData = buildHoverCustomData({
    dates,
    warehouse: ALL_WAREHOUSES_LABEL,
    stock: aggregated.stock,
    sold: aggregated.sold,
    replenished: aggregated.replenished,
    price: aggregated.price,
  });

  if (stockToggle?.checked && (!showPerWarehouse || !hasMultipleWarehouses)) {
    traces.push({
      x: dates,
      y: aggregated.stock,
      name: "Остаток",
      yaxis: "y",
      type: "scatter",
      mode: "lines",
      connectgaps: true,
      line: { color: "#2563eb", width: 2 },
      customdata: aggregateCustomData,
      hovertemplate: hoverTemplate,
      showlegend: true,
    });
  }

  traces.push({
    x: dates,
    y: aggregated.sold,
    name: "Продано",
    type: "bar",
    yaxis: "y2",
    marker: { color: "#2563eb", opacity: 0.35 },
    customdata: aggregateCustomData,
    hovertemplate: hoverTemplate,
  });

  traces.push({
    x: dates,
    y: aggregated.replenished,
    name: "Пополнено",
    type: "bar",
    yaxis: "y2",
    marker: { color: "#16a34a", opacity: 0.25 },
    customdata: aggregateCustomData,
    hovertemplate: hoverTemplate,
  });

  const latestStockEntries = [];
  const latestPriceEntries = [];
  warehouses.forEach((warehouse) => {
    const warehouseMap = byWarehouse.get(warehouse);
    if (!warehouseMap) return;
    const warehouseDates = Array.from(warehouseMap.keys()).sort();
    const latestDate = warehouseDates[warehouseDates.length - 1];
    const entry = warehouseMap.get(latestDate);
    if (entry?.stock_qty !== null && entry?.stock_qty !== undefined) {
      latestStockEntries.push(entry.stock_qty);
    }
    if (entry?.price !== null && entry?.price !== undefined) {
      latestPriceEntries.push(entry.price);
    }
  });

  if (kpiStock) {
    kpiStock.textContent = formatNumber(
      latestStockEntries.reduce((sum, value) => sum + value, 0)
    );
  }
  if (kpiWarehouses) {
    kpiWarehouses.textContent =
      warehouses.length > 0 ? warehouses.join(", ") : ALL_WAREHOUSES_LABEL;
  }
  if (kpiPrice) {
    if (latestPriceEntries.length === 0) {
      kpiPrice.textContent = "—";
    } else {
      const minPrice = Math.min(...latestPriceEntries);
      const maxPrice = Math.max(...latestPriceEntries);
      kpiPrice.textContent =
        minPrice === maxPrice
          ? formatCurrency(minPrice)
          : `${formatCurrency(minPrice)} – ${formatCurrency(maxPrice)}`;
    }
  }

  const layout = {
    barmode: "group",
    yaxis: { title: "Остаток" },
    yaxis2: {
      title: "Продажи/пополнения",
      overlaying: "y",
      side: "right",
    },
    margin: { t: 30 },
  };

  if (DEBUG) {
    console.debug("RENDER CHART CALLED");
  }
  try {
    if (!window.Plotly?.newPlot) {
      throw new Error("Plotly не загружен");
    }
    const chartEl = document.getElementById("chart");
    if (!chartEl) {
      throw new Error("Контейнер графика #chart не найден");
    }
    Plotly.newPlot(chartEl, traces, layout, {
      responsive: true,
    });
  } catch (error) {
    console.error("chartRenderError", error);
    setChartErrorState({
      status: "—",
      body: `Ошибка отрисовки графика: ${error?.message ?? error}`,
    });
  }
}

function getUploadMode() {
  const mode = new URLSearchParams(window.location.search).get("mode");
  return mode === "bootstrap" ? "bootstrap" : "reject";
}

async function fetchLatestLoadedDate() {
  const params = new URLSearchParams();
  appendParam(params, "company", getSelectedCompany());
  const url = buildUrl(`/meta/latest_date?${params.toString()}`);
  if (DEBUG) {
    console.log("latestDateUrl", url);
  }
  const result = await safeFetch(url);
  if (!result.ok) {
    updateLatestLoadedBadge(null);
    return;
  }
  updateLatestLoadedBadge(result.payload?.latest_date || null);
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
  fetchLatestLoadedDate();
});

async function loadWarehouseOptions() {
  if (!warehouseList) return;
  const params = new URLSearchParams();
  appendParam(params, "field", "warehouse");
  appendParam(params, "company", getSelectedCompany());
  const url = buildUrl(`/filters/suggestions?${params.toString()}`);
  if (DEBUG) {
    console.log("filtersSuggestionsParams", {
      field: "warehouse",
      company: getSelectedCompany(),
    });
    console.log("filtersSuggestionsUrl", url);
  }
  const result = await safeFetch(url);
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
  company,
  warehouses,
  dateFrom,
  dateTo,
}) {
  if (!dateFrom || !dateTo) {
    return;
  }
  setChartLoadingState();
  updateSumWarehouseToggle(warehouses ?? getSelectedWarehouses());
  const resolvedCompany = company || getSelectedCompany();
  const params = new URLSearchParams();
  appendParam(params, "item_id", itemId);
  appendParam(params, "warehouses", warehouses);
  appendParam(params, "company", resolvedCompany);
  appendParam(params, "date_from", dateFrom);
  appendParam(params, "date_to", dateTo);
  const url = buildUrl(`/series?${params.toString()}`);
  updateSeriesDebugPanel({ url, status: "loading", points: [] });
  if (DEBUG) {
    console.log("seriesParams", {
      itemId,
      company: resolvedCompany,
      warehouses,
      dateFrom,
      dateTo,
    });
    console.log("seriesUrl", url);
  }
  if (DEBUG) {
    console.debug("seriesFetchUrl", url);
  }
  const result = await safeFetch(url);
  if (DEBUG) {
    console.debug("seriesFetchStatus", result.response?.status ?? "—");
  }
  if (!result.response?.ok) {
    if (DEBUG) {
      console.error("seriesError", {
        status: result.response?.status,
        body: result.errorMessage || result.body,
      });
    }
    setChartErrorState({
      status: result.response?.status,
      body: result.errorMessage || result.body,
    });
    updateSeriesDebugPanel({
      url,
      status: result.response?.status ?? "error",
      points: [],
    });
    return;
  }
  const resp = result.payload ?? {};
  const series = extractSeries(resp);
  console.debug("SERIES RESPONSE", resp);
  console.debug("SERIES LENGTH", series?.length);
  console.debug("FIRST POINT", series?.[0]);
  if (DEBUG) {
    console.debug("series keys", Object.keys(resp));
    console.debug("available_range", resp.available_range);
    if (series.length > 0) {
      console.debug("series sample", series.slice(0, 3));
    }
  }
  updateSeriesDebugPanel({
    url,
    status: result.response?.status ?? "ok",
    points: series,
  });
  lastSeriesParams = {
    itemId,
    company: resolvedCompany,
    warehouses,
    dateFrom,
    dateTo,
  };
  renderSeries(result.payload);
}

async function fetchSeries() {
  if (selectedTopIndex >= 0 && filteredTopItems[selectedTopIndex]) {
    await fetchSeriesForItem(filteredTopItems[selectedTopIndex]);
    return;
  }
  setChartPlaceholder();
}

async function fetchSeriesForItem(item) {
  if (!item?.item_id) {
    if (DEBUG) {
      console.error("seriesError", { message: "missing item_id", item });
    }
    setChartErrorState({ status: "—", body: "Не найден item_id для выбранной строки." });
    return;
  }
  const { company, warehouses, dateFrom, dateTo } = collectFilters();
  const rowWarehouse =
    topGroupByWarehouse && item?.warehouse && item.warehouse !== ALL_WAREHOUSES_LABEL
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
      <td>${formatNumber(item.sold_total)}</td>
      <td>${formatNumber(item.replenished_total)}</td>
      <td>${formatCurrency(item.last_price)}</td>
    `;
    row.addEventListener("click", () => {
      setSelectedItem(item);
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

  if (!dateFrom || !dateTo) {
    return;
  }

  topGroupByWarehouse = warehouses.length <= 1;

  const params = new URLSearchParams();
  appendParam(params, "sku", sku);
  appendParam(params, "manufacturer", manufacturer);
  appendParam(params, "company", company);
  appendParam(params, "project", project);
  appendParam(params, "warehouses", warehouses);
  appendParam(params, "date_from", dateFrom);
  appendParam(params, "date_to", dateTo);
  appendParam(params, "limit", topPageSize);
  appendParam(params, "page", topPage);
  appendParam(params, "group_by_warehouse", topGroupByWarehouse);
  const url = buildUrl(`/top?${params.toString()}`);
  if (DEBUG) {
    console.log("topParams", {
      sku,
      manufacturer,
      company,
      project,
      warehouses,
      dateFrom,
      dateTo,
      page: topPage,
      pageSize: topPageSize,
      groupByWarehouse: topGroupByWarehouse,
    });
    console.log("topUrl", url);
  }
  const result = await safeFetch(url);
  if (!result.response?.ok) {
    renderTopTable([]);
    return;
  }
  const payload = result.payload || {};
  const items = Array.isArray(payload) ? payload : payload.items || [];
  const totalCount = payload.total_count ?? payload.total ?? items.length;
  if (DEBUG) {
    console.log("topResponseSize", { rows: items.length, total: totalCount });
  }
  topItems = items;
  applyTopFilter();
  updatePaginationControls(totalCount);
  if (selectedTopIndex >= 0 && filteredTopItems[selectedTopIndex]) {
    fetchSeriesForItem(filteredTopItems[selectedTopIndex]);
  } else {
    selectedTopKey = null;
    selectedTopIndex = -1;
    renderTopTable(filteredTopItems);
    setChartPlaceholder();
  }
}

applyFilters?.addEventListener("click", (event) => {
  event.preventDefault();
  if (DEBUG) {
    console.log("filtersApplied", collectFilters());
  }
  topPage = 1;
  fetchTop();
});

datePreset?.addEventListener("change", (event) => {
  applyDatePreset(event.target.value);
});

topSearchInput?.addEventListener("input", () => {
  applyTopFilter();
});

topPagePrevButton?.addEventListener("click", () => {
  if (topPage > 1) {
    topPage -= 1;
    fetchTop();
  }
});

topPageNextButton?.addEventListener("click", () => {
  if (topPage < topTotalPages) {
    topPage += 1;
    fetchTop();
  }
});

topPageNumberInput?.addEventListener("change", () => {
  const nextPage = Number.parseInt(topPageNumberInput.value, 10);
  if (!Number.isFinite(nextPage)) return;
  topPage = Math.min(Math.max(nextPage, 1), topTotalPages);
  fetchTop();
});

topPageSizeSelect?.addEventListener("change", () => {
  const nextSize = Number.parseInt(topPageSizeSelect.value, 10);
  if (!Number.isFinite(nextSize)) return;
  topPageSize = nextSize;
  topPage = 1;
  fetchTop();
});

stockToggle?.addEventListener("change", () => {
  if (lastSeriesPayload) {
    renderSeries(lastSeriesPayload);
  } else {
    fetchSeries();
  }
});

sumWarehouseToggle?.addEventListener("change", () => {
  if (lastSeriesPayload) {
    renderSeries(lastSeriesPayload);
  }
});

companySwitcher?.addEventListener("change", () => {
  loadWarehouseOptions();
  topPage = 1;
  fetchTop();
  fetchLatestLoadedDate();
});

loadWarehouseOptions();
initWarehouseActions();
fetchLatestLoadedDate();
setChartPlaceholder();
