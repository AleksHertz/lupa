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
  return Array.from(warehouseSelect.selectedOptions).map((option) => option.value);
}

function getTopLimit() {
  const selected = topLimitGroup?.querySelector('input[name="top-limit"]:checked');
  return selected?.value || "100";
}

function getSelectedCompany() {
  return companySwitcher?.value || "";
}

function collectFilters() {
  const sku = document.getElementById("filter-sku").value || "";
  const manufacturer = document.getElementById("filter-manufacturer").value || "";
  const company = getSelectedCompany();
  const project = document.getElementById("filter-project")?.value || "";
  const dateFrom = document.getElementById("filter-date-from").value;
  const dateTo = document.getElementById("filter-date-to").value;
  const warehouse = getSelectedWarehouses();

  return {
    sku,
    manufacturer,
    company,
    project,
    warehouse,
    dateFrom,
    dateTo,
  };
}

uploadForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(uploadForm);
  formData.set("company", getSelectedCompany());
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
  const params = new URLSearchParams({
    field: "warehouse",
    q: "",
    company: getSelectedCompany(),
  });
  const result = await safeFetch(buildUrl(`/filters/suggestions?${params.toString()}`));
  if (!result.ok) {
    warehouseSelect.innerHTML = "";
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

async function fetchSeries() {
  const {
    sku,
    manufacturer,
    company,
    project,
    warehouse,
    dateFrom,
    dateTo,
  } = collectFilters();

  if (!dateFrom || !dateTo) {
    return;
  }

  const params = new URLSearchParams({
    sku,
    warehouse: warehouse.join(","),
    manufacturer,
    company,
    project,
    date_from: dateFrom,
    date_to: dateTo,
  });
  const result = await safeFetch(buildUrl(`/series?${params.toString()}`));
  if (!result.ok) {
    return;
  }
  const payload = result.payload;

  const soldTrace = {
    x: payload.dates,
    y: payload.sold_qty,
    name: "Продано",
    type: "bar",
    marker: { color: "#2563eb" },
  };

  const replTrace = {
    x: payload.dates,
    y: payload.replenished_qty,
    name: "Пополнено",
    type: "bar",
    marker: { color: "#16a34a" },
  };

  const priceTrace = {
    x: payload.dates,
    y: payload.price,
    name: "Цена",
    yaxis: "y2",
    type: "scatter",
    mode: "lines+markers",
    line: { color: "#f97316" },
  };

  const traces = [soldTrace, replTrace, priceTrace];

  if (stockToggle?.checked && payload.stock_qty) {
    traces.push({
      x: payload.dates,
      y: payload.stock_qty,
      name: "Остаток",
      yaxis: "y3",
      type: "scatter",
      mode: "lines",
      line: { color: "#0ea5e9", width: 2 },
    });
  }

  const layout = {
    barmode: "group",
    yaxis: { title: "Кол-во" },
    yaxis2: {
      title: "Цена",
      overlaying: "y",
      side: "right",
    },
    yaxis3: {
      title: "Остаток",
      overlaying: "y",
      side: "right",
      position: 1.05,
    },
    margin: { t: 30 },
  };

  Plotly.newPlot("chart", traces, layout, {
    responsive: true,
  });

  kpiSold.textContent = payload.kpi.sold_total.toFixed(2);
  kpiReplenished.textContent = payload.kpi.replenished_total.toFixed(2);
  kpiMaxSold.textContent = payload.kpi.max_sold_date || "—";
  kpiMaxRepl.textContent = payload.kpi.max_replenished_date || "—";
}

function renderTopTable(items) {
  if (!topTableBody) return;
  topTableBody.innerHTML = "";
  items.forEach((item) => {
    const row = document.createElement("tr");
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
      const skuInput = document.getElementById("filter-sku");
      if (skuInput && item.sku) {
        skuInput.value = item.sku;
      }
      fetchSeries();
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
    warehouse,
    dateFrom,
    dateTo,
  } = collectFilters();
  const limit = getTopLimit();

  if (!dateFrom || !dateTo) {
    return;
  }

  const params = new URLSearchParams({
    sku,
    manufacturer,
    company,
    project,
    warehouse: warehouse.join(","),
    date_from: dateFrom,
    date_to: dateTo,
    limit,
  });
  const result = await safeFetch(buildUrl(`/top?${params.toString()}`));
  if (!result.ok) {
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
