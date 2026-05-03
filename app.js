const dataUrl = "data/records.json";

async function loadData() {
  const response = await fetch(dataUrl, { cache: "no-store" });
  if (!response.ok) {
    throw new Error("無法讀取資料檔");
  }
  return response.json();
}

function formatGeneratedAt(value) {
  if (!value) {
    return "未提供";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("zh-Hant-MO", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Macau",
  }).format(date);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function sortRecords(records) {
  return [...records].sort((a, b) => {
    if (a.date !== b.date) return a.date < b.date ? -1 : 1;
    const aTime = (a.time || "").split("~")[0];
    const bTime = (b.time || "").split("~")[0];
    if (aTime !== bTime) return aTime < bTime ? -1 : 1;
    const aCourt = a.court || "";
    const bCourt = b.court || "";
    return aCourt < bCourt ? -1 : aCourt > bCourt ? 1 : 0;
  });
}

function parseRecordEnd(record) {
  const dateMatch = String(record.date || "").match(/^(\d{4})\/(\d{1,2})\/(\d{1,2})$/);
  const endTime = String(record.time || "").split("~")[1] || "";
  const timeMatch = endTime.match(/^(\d{1,2}):(\d{2})$/);
  if (!dateMatch || !timeMatch) return null;
  const [, year, month, day] = dateMatch;
  const [, hour, minute] = timeMatch;
  return new Date(Number(year), Number(month) - 1, Number(day), Number(hour), Number(minute));
}

function filterActiveRecords(records) {
  const now = new Date();
  return records.filter((record) => {
    const end = parseRecordEnd(record);
    return !end || end >= now;
  });
}

function renderSummary(records) {
  const summary = document.querySelector("#summary");
  const dates = new Set(records.map((record) => record.date).filter(Boolean));
  const courts = new Set(records.map((record) => record.court).filter(Boolean));
  const knownNames = records.filter((record) => record.renterName || record.extraName).length;

  summary.innerHTML = `
    <article class="summary-card">
      <span>總筆數</span>
      <strong>${records.length}</strong>
      <em>含原圖檢視</em>
    </article>
    <article class="summary-card">
      <span>日期數量</span>
      <strong>${dates.size}</strong>
      <em>${[...dates].join("、") || "尚無資料"}</em>
    </article>
    <article class="summary-card">
      <span>已配對姓名</span>
      <strong>${knownNames}</strong>
      <em>${courts.size} 個球場編號</em>
    </article>
  `;
}

function rowTemplate(record, imageUrl) {
  const imageCell = imageUrl
    ? `<button class="thumb-btn" onclick="openLightbox('${escapeHtml(imageUrl)}', '${escapeHtml(record.date + " " + record.court)}')" aria-label="查看圖片">
          <img class="thumb-img" src="${escapeHtml(imageUrl)}" alt="${escapeHtml(record.date + " " + record.court)}" loading="lazy" />
        </button>`
    : `<span class="image-pruned">已清理</span>`;

  return `
    <tr>
      <td>${escapeHtml(record.date)}</td>
      <td>${escapeHtml(record.time)}</td>
      <td>${escapeHtml(record.court)}</td>
      <td>${escapeHtml(record.renterCode)}</td>
      <td>${escapeHtml(record.extraCode)}</td>
      <td>${escapeHtml(record.renterName)}</td>
      <td>${escapeHtml(record.extraName)}</td>
      <td>${imageCell}</td>
    </tr>
  `;
}

function renderTable(selector, records, options = {}) {
  const container = document.querySelector(selector);
  if (!records.length) {
    container.innerHTML = `<tr><td class="empty-state" colspan="8">目前沒有資料。</td></tr>`;
    return;
  }

  container.innerHTML = records
    .map((record) => rowTemplate(record, options.urlBuilder ? options.urlBuilder(record) : record.image))
    .join("");
}

function openLightbox(src, alt) {
  const lb = document.getElementById("lightbox");
  const img = document.getElementById("lightbox-img");
  img.src = src;
  img.alt = alt || "";
  lb.classList.add("active");
  document.body.style.overflow = "hidden";
}

function closeLightbox() {
  document.getElementById("lightbox").classList.remove("active");
  document.body.style.overflow = "";
}

document.addEventListener("DOMContentLoaded", () => {
  const lb = document.getElementById("lightbox");
  document.getElementById("lightbox-close").addEventListener("click", closeLightbox);
  lb.addEventListener("click", (e) => {
    if (e.target === lb) closeLightbox();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeLightbox();
  });
});

async function bootstrap() {
  try {
    const payload = await loadData();
    document.querySelector("#generated-at").textContent = formatGeneratedAt(payload.generatedAt);
    const activeRecords = filterActiveRecords(payload.records);
    const sorted = sortRecords(activeRecords);
    renderSummary(sorted);
    renderTable("#records-body", sorted);
  } catch (error) {
    document.querySelector("#generated-at").textContent = "載入失敗";
    renderSummary([]);
    renderTable("#records-body", []);
  }
}

bootstrap();
