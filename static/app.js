const uploadForm = document.getElementById("upload-form");
const uploadStatus = document.getElementById("upload-status");
const applyFilters = document.getElementById("apply-filters");
const warehouseSelect = document.getElementById("filter-warehouse");
const topTableBody = document.getElementById("top-table-body");
const topLimitGroup = document.getElementById("top-limit");
const datePreset = document.getElementById("filter-date-preset");
const stockToggle = document.getElementById("toggle-stock");

const kpiSold = document.getElementById("kpi-sold");
const kpiReplenished = document.getElementById("kpi-replenished");
const kpiMaxSold = document.getElementById("kpi-max-sold");
const kpiMaxRepl = document.getElementById("kpi-max-repl");

function setStatus(message, isError = false) {
  uploadStatus.textContent = message;
  uploadStatus.style.color = isError ? "#b42318" : "#027a48";
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

function collectFilters() {
  const sku = document.getElementById("filter-sku").value || "";
  const manufacturer = document.getElementById("filter-manufacturer").value || "";
  const company = document.getElementById("filter-company")?.value || "";
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
  setStatus("Загрузка...", false);
  try {
    const response = await fetch("/upload", {
      method: "POST",
      body: formData,
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Ошибка загрузки");
    }
    setStatus(`Готово. Снимков: ${payload.snapshots}, дельт: ${payload.deltas}.`);
  } catch (error) {
    setStatus(error.message, true);
  }
});

async function loadWarehouseOptions() {
  if (!warehouseSelect) return;
  try {
    const response = await fetch("/filters/suggestions?field=warehouse&q=");
    if (!response.ok) return;
    const payload = await response.json();
    warehouseSelect.innerHTML = "";
    payload.items.forEach((item) => {
      const option = document.createElement("option");
      option.value = item;
      option.textContent = item;
      warehouseSelect.append(option);
    });
  } catch (error) {
    warehouseSelect.innerHTML = "";
  }
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
  const response = await fetch(`/series?${params.toString()}`);
  const payload = await response.json();

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
    y: payload.price_start_day,
    name: "Цена (старт дня)",
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
  const response = await fetch(`/top?${params.toString()}`);
  if (!response.ok) {
    renderTopTable([]);
    return;
  }
  const payload = await response.json();
  const items = Array.isArray(payload) ? payload : payload.items || [];
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

loadWarehouseOptions();
