const uploadForm = document.getElementById("upload-form");
const uploadStatus = document.getElementById("upload-status");
const applyFilters = document.getElementById("apply-filters");

const kpiSold = document.getElementById("kpi-sold");
const kpiReplenished = document.getElementById("kpi-replenished");
const kpiMaxSold = document.getElementById("kpi-max-sold");
const kpiMaxRepl = document.getElementById("kpi-max-repl");

function setStatus(message, isError = false) {
  uploadStatus.textContent = message;
  uploadStatus.style.color = isError ? "#b42318" : "#027a48";
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

async function fetchSeries() {
  const sku = document.getElementById("filter-sku").value || "";
  const warehouse = document.getElementById("filter-warehouse").value || "";
  const manufacturer = document.getElementById("filter-manufacturer").value || "";
  const dateFrom = document.getElementById("filter-date-from").value;
  const dateTo = document.getElementById("filter-date-to").value;

  if (!dateFrom || !dateTo) {
    return;
  }

  const params = new URLSearchParams({
    sku,
    warehouse,
    manufacturer,
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

  const layout = {
    barmode: "group",
    yaxis: { title: "Кол-во" },
    yaxis2: {
      title: "Цена",
      overlaying: "y",
      side: "right",
    },
    margin: { t: 30 },
  };

  Plotly.newPlot("chart", [soldTrace, replTrace, priceTrace], layout, {
    responsive: true,
  });

  kpiSold.textContent = payload.kpi.sold_total.toFixed(2);
  kpiReplenished.textContent = payload.kpi.replenished_total.toFixed(2);
  kpiMaxSold.textContent = payload.kpi.max_sold_date || "—";
  kpiMaxRepl.textContent = payload.kpi.max_replenished_date || "—";
}

applyFilters?.addEventListener("click", (event) => {
  event.preventDefault();
  fetchSeries();
});
