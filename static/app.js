"use strict";
const $ = s => document.querySelector(s);
const fmt = (n, d = 0) => n == null ? "—" : n.toLocaleString("ru-RU",
  { minimumFractionDigits: d, maximumFractionDigits: d }) + " ₽";
const pct = n => n == null ? "—" : (n >= 0 ? "+" : "") + (n * 100).toFixed(2) + "%";
const cls = n => n >= 0 ? "pos" : "neg";
const api = async (p, o = {}) => {
  const response = await fetch("/api" + p, { cache: "no-store", ...o });
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = typeof payload === "object" ? payload.detail : payload;
    throw new Error(typeof detail === "string" && detail ? detail : `${response.status} ${response.statusText}`);
  }
  if (payload && typeof payload === "object" && payload.ok === false) {
    throw new Error(payload.error || "Операция не выполнена");
  }
  return payload;
};

const COLORS = {
  text: "#e8edf3", muted: "#8d9aaa", line: "#273342",
  grid: "rgba(148,163,184,.10)", amber: "#f4c457", teal: "#4fd1c5",
  blue: "#6f9ff8", green: "#4ade80", red: "#fb7185",
  purple: "#b783f4", orange: "#fb923c",
};
const AX = {
  axisLine: { show: false },
  axisTick: { show: false },
  axisLabel: { color: COLORS.muted, fontSize: 10, margin: 11 },
  splitLine: { lineStyle: { color: COLORS.grid } },
};
const charts = {};
function chart(id, opt) {
  if (!charts[id]) charts[id] = echarts.init(document.getElementById(id), null, { renderer: "canvas" });
  opt.textStyle = { fontFamily: "Inter, sans-serif", ...(opt.textStyle || {}) };
  if (opt.tooltip) {
    opt.tooltip = {
      backgroundColor: "rgba(11,16,23,.96)", borderColor: COLORS.line, borderWidth: 1,
      padding: [9, 11], textStyle: { color: COLORS.text, fontFamily: "Inter, sans-serif", fontSize: 11 },
      extraCssText: "border-radius:10px;box-shadow:0 14px 35px rgba(0,0,0,.34)",
      ...opt.tooltip,
    };
  }
  opt.animationDuration = opt.animationDuration ?? 420;
  opt.animationEasing = opt.animationEasing || "cubicOut";
  charts[id].setOption(opt, true);
}
window.addEventListener("resize", () => Object.values(charts).forEach(c => c.resize()));

// ===== TOAST =====
function toast(msg, type = "") {
  const wrap = $("#toast");
  const el = document.createElement("div");
  el.className = "toast-msg" + (type ? " " + type : "");
  el.textContent = msg;
  wrap.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

// ===== KPI CARDS =====
function renderKpis(s) {
  const cards = [
    { label: "Стоимость", value: fmt(s.value), sub: pct(s.pnl_pct), c: "", subC: cls(s.pnl), accent: COLORS.amber },
    { label: "Вложено", value: fmt(s.invested), sub: "только внешние пополнения", c: "", accent: COLORS.blue },
    { label: "Прибыль", value: fmt(s.pnl), sub: pct(s.pnl_pct), c: cls(s.pnl),
      accent: s.pnl >= 0 ? COLORS.green : COLORS.red },
    { label: "XIRR годовых", value: s.xirr == null ? "нет данных" : pct(s.xirr),
      sub: s.xirr == null ? "нужны транзакции" : "годовых с учётом дат вложений", c: cls(s.xirr || 0),
      accent: (s.xirr || 0) >= 0 ? COLORS.teal : COLORS.red },
    { label: "Получено выплат", value: fmt(s.income_received), sub: "", c: "", accent: COLORS.teal },
  ];
  $("#kpis").innerHTML = cards.map(x => `<div class="kpi" style="--kpi-accent:${x.accent}">
    <div class="label">${x.label}</div>
    <div class="value ${x.c}">${x.value}</div>
    <div class="sub ${x.subC ?? x.c}">${x.sub}</div>
  </div>`).join("");
}

// ===== GAMEBAR: PROGRESS + STREAK + DELTAS =====
let _portfolioGoal = 1_000_000;

function renderGamebar(s, returns) {
  const val = s.value || 0;
  const pctFill = Math.min(100, (val / _portfolioGoal) * 100);
  const pctVal = (val / _portfolioGoal * 100).toFixed(1) + "%";
  const left = Math.max(0, _portfolioGoal - val);

  $("#goal-label").textContent = `Цель: ${fmt(_portfolioGoal)}`;
  $("#progress-fill").style.width = pctFill + "%";
  $("#progress-pct").textContent = pctVal;
  $("#progress-sub").textContent = `${fmt(val)} из ${fmt(_portfolioGoal)} · осталось ${fmt(left)}`;

  const streak = s.streak || 0;
  $("#streak-val").textContent = streak;
  $("#streak-sub").textContent = streak === 1 ? "день подряд" : streak >= 2 && streak <= 4 ? "дня подряд" : "дней подряд";

  if (returns) {
    _setDelta("today", returns.today);
    _setDelta("week", returns.week);
    _setDelta("month", returns.month);
    _setDelta("ytd", returns.ytd);
  }
}

function _setDelta(id, d) {
  const el = $("#delta-" + id);
  const elPct = $("#delta-" + id + "-pct");
  if (!d || d.change == null || d.pct == null) {
    if (el) { el.className = "delta-val"; el.textContent = "—"; }
    if (elPct) { elPct.className = "delta-pct"; elPct.textContent = "нет опорного снимка"; }
    return;
  }
  const change = d.change;
  const p = d.pct;
  const sign = change >= 0 ? "+" : "";
  const c = change >= 0 ? "pos-val" : "neg-val";
  if (el) { el.className = "delta-val " + c; el.textContent = sign + fmt(change, 0); }
  if (elPct) { elPct.className = "delta-pct " + c; elPct.textContent = sign + (p * 100).toFixed(2) + "%"; }
}

// ===== VALUE CHART =====
let _valueHistory = [];
let _valuePeriod = "day";

function _isoWeekKey(isoDate) {
  const d = new Date(isoDate.slice(0, 10) + "T00:00:00Z");
  const day = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  const week = Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
  return `${d.getUTCFullYear()}-${String(week).padStart(2, "0")}`;
}

function _groupValueHistory(hist, period) {
  if (period === "day") return hist.map(h => ({ ...h, label: h.day || h.ts.slice(0, 10) }));
  const buckets = new Map();
  for (const row of hist) {
    const day = row.day || row.ts.slice(0, 10);
    const key = period === "week" ? _isoWeekKey(day) : day.slice(0, 7);
    buckets.set(key, { ...row, label: period === "week" ? `нед. ${key.slice(5)}` : key });
  }
  return [...buckets.values()];
}

function renderValue(hist = _valueHistory) {
  _valueHistory = hist || [];
  const rows = _groupValueHistory(_valueHistory, _valuePeriod);
  if (!rows.length) {
    chart("chart-value", { graphic: [{ type: "text", left: "center", top: "middle",
      style: { text: "График появится после первого снимка", fill: COLORS.muted, fontSize: 13 } }] });
    return;
  }
  const x = rows.map(h => h.label);
  const val = rows.map(h => h.value);
  const inv = rows.map(h => h.invested);
  chart("chart-value", {
    aria: { enabled: true, description: "График стоимости портфеля и внешних пополнений по снимкам" },
    grid: { left: 64, right: 16, top: 30, bottom: 30 },
    tooltip: { trigger: "axis", valueFormatter: v => fmt(v) },
    legend: { data: ["Стоимость", "Внешние пополнения"], textStyle: { color: COLORS.muted, fontSize: 10 }, top: 0, itemWidth: 16, itemHeight: 6 },
    xAxis: { type: "category", data: x, ...AX },
    yAxis: { type: "value", ...AX, axisLabel: { color: COLORS.muted, formatter: v => (v / 1000) + "k" } },
    series: [
      { name: "Стоимость", type: "line", smooth: true, data: val, symbol: "circle", symbolSize: 5,
        lineStyle: { width: 2.5, color: COLORS.amber }, itemStyle: { color: COLORS.amber },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1,
          [{ offset: 0, color: "rgba(244,196,87,.24)" }, { offset: 1, color: "rgba(244,196,87,0)" }]) } },
      { name: "Внешние пополнения", type: "line", smooth: true, data: inv, symbol: "none",
        lineStyle: { width: 1.5, color: COLORS.blue, type: "dashed" } },
    ],
  });
}

document.querySelectorAll(".value-period-btn").forEach(b => {
  b.onclick = () => {
    _valuePeriod = b.dataset.period;
    document.querySelectorAll(".value-period-btn").forEach(btn =>
      btn.classList.toggle("active", btn === b));
    renderValue();
  };
});

// ===== LEADERS RANKING =====
let _leadersPeriod = "day";

const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, char => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
})[char]);

function reconciledRubles(items) {
  const raw = items.map(item => Number(item.change || 0));
  const displayed = raw.map(value => {
    const truncated = Math.trunc(value);
    return Object.is(truncated, -0) ? 0 : truncated;
  });
  const total = raw.reduce((sum, value) => sum + value, 0);
  const target = Math.sign(total) * Math.round(Math.abs(total));
  const remainder = target - displayed.reduce((sum, value) => sum + value, 0);
  if (!remainder) return displayed;

  const direction = Math.sign(remainder);
  const order = raw.map((value, index) => ({
    index,
    fraction: value - displayed[index],
  })).sort((a, b) => direction > 0
    ? b.fraction - a.fraction
    : a.fraction - b.fraction);
  for (let step = 0; step < Math.abs(remainder); step += 1) {
    displayed[order[step % order.length].index] += direction;
  }
  return displayed;
}

function renderLeaders(data) {
  const list = $("#leaders-list");
  const items = [...(data?.items || [])]
    .sort((a, b) => Math.abs(b.change || 0) - Math.abs(a.change || 0));
  const range = $("#leaders-range");
  if (range) {
    if (data?.from && data?.to) {
      const from = new Date(data.from).toLocaleDateString("ru-RU");
      const to = new Date(data.to).toLocaleDateString("ru-RU");
      range.textContent = `${from} — ${to}${data.complete ? "" : " · неполная история"}`;
    } else {
      range.textContent = "нужно минимум два снимка портфеля";
    }
  }

  if (!items.length) {
    list.innerHTML = '<div class="leaders-empty">Нет изменений за выбранный период</div>';
    return;
  }

  const maxChange = Math.max(...items.map(item => Math.abs(item.change || 0)), 1);
  const displayedChanges = reconciledRubles(items);
  list.innerHTML = `
    <div class="leaders-list-head">
      <span></span><span>Инструмент</span><span>Изменение</span><span>Вклад в портфель</span>
    </div>
    ${items.map((item, index) => {
      const positive = (item.change || 0) >= 0;
      const direction = positive ? "positive" : "negative";
      const ticker = item.ticker || item.name || "—";
      const name = item.name && item.name !== ticker ? item.name : "";
      const priceChange = item.change_pct == null
        ? "новая позиция"
        : `${item.change_pct >= 0 ? "+" : ""}${(item.change_pct * 100).toFixed(2)}%`;
      const displayedChange = displayedChanges[index];
      const contribution = `${displayedChange > 0 ? "+" : ""}${fmt(displayedChange, 0)}`;
      const impact = `${((item.impact_pct || 0) * 100).toFixed(1)}% движения`;
      const width = Math.max(1.5, Math.abs(item.change || 0) / maxChange * 100);
      return `<div class="leader-row ${direction}" style="--leader-width:${width.toFixed(1)}%">
        <span class="leader-rank">${String(index + 1).padStart(2, "0")}</span>
        <span class="leader-instrument">
          <strong>${escapeHtml(ticker)}</strong>
          ${name ? `<small>${escapeHtml(name)}</small>` : ""}
          <em>${escapeHtml(priceChange)}</em>
        </span>
        <span class="leader-change">
          <strong>${escapeHtml(priceChange)}</strong>
          <small>стоимость ${fmt(item.value, 0)}</small>
        </span>
        <span class="leader-impact">
          <strong>${contribution}</strong>
          <small>${impact}</small>
        </span>
      </div>`;
    }).join("")}`;
}

async function loadLeaders(period) {
  _leadersPeriod = period;
  document.querySelectorAll(".leaders-btn").forEach(b =>
    b.classList.toggle("active", b.dataset.period === period));
  try {
    renderLeaders(await api("/leaders?period=" + period));
  } catch(e) {
    console.error("leaders error", e);
    const range = $("#leaders-range");
    if (range) range.textContent = "ошибка загрузки данных";
    $("#leaders-list").innerHTML = '<div class="leaders-empty error">Не удалось загрузить список · обновите страницу</div>';
  }
}

document.querySelectorAll(".leaders-btn").forEach(b => {
  b.onclick = () => loadLeaders(b.dataset.period);
});

// ===== ALLOCATION DONUT =====
function renderAlloc(s) {
  const data = Object.entries(s.by_class).map(([k, v]) => ({ name: k, value: v.value }));
  const compact = window.innerWidth <= 720;
  if ($("#alloc-total")) $("#alloc-total").textContent = fmt(s.value);
  if (!data.length) {
    chart("chart-alloc", { graphic: [{ type: "text", left: "center", top: "middle",
      style: { text: "Структура появится после импорта", fill: COLORS.muted, fontSize: 13 } }] });
    return;
  }
  chart("chart-alloc", {
    aria: { enabled: true, description: "Распределение текущей стоимости портфеля по классам активов" },
    tooltip: { trigger: "item", valueFormatter: v => fmt(v) },
    legend: { bottom: 0, textStyle: { color: COLORS.muted, fontSize: 10 }, itemWidth: 10, itemHeight: 10 },
    color: [COLORS.amber, COLORS.teal, COLORS.blue, COLORS.purple, COLORS.orange],
    series: [{ type: "pie", radius: compact ? ["44%", "68%"] : ["48%", "72%"], center: ["50%", "44%"],
      avoidLabelOverlap: true, itemStyle: { borderColor: "#121923", borderWidth: 3, borderRadius: 4 },
      label: { show: !compact, color: COLORS.text, fontSize: 10, formatter: "{b}\n{d}%" }, data }],
  });
}

// ===== RETURNS CHART =====
let _returnsPeriod = "daily";

function renderReturns(data) {
  const pts = data.points || [];
  if (!pts.length) {
    chart("chart-returns", { graphic: [{ type: "text", left: "center", top: "middle",
      style: { text: "Нужно минимум два снимка", fill: COLORS.muted, fontSize: 13 } }] });
    return;
  }
  const manyBars = pts.length > 60;
  chart("chart-returns", {
    aria: { enabled: true, description: "Доходность портфеля по выбранным периодам" },
    grid: { left: 52, right: 10, top: 20, bottom: manyBars ? 4 : 30 },
    tooltip: {
      trigger: "axis",
      formatter: p => {
        const pt = pts[p[0]?.dataIndex];
        if (!pt) return "";
        const sign = pt.pct >= 0 ? "+" : "";
        const pctStr = sign + (pt.pct * 100).toFixed(2) + "%";
        const rubStr = sign + pt.change.toLocaleString("ru-RU", { maximumFractionDigits: 0 }) + " ₽";
        return `${p[0].axisValue}<br/><b>${pctStr}</b>  ${rubStr}`;
      },
    },
    xAxis: { type: "category", data: pts.map(p => p.label), ...AX,
      axisLabel: { color: COLORS.muted, show: !manyBars, rotate: pts.length > 20 ? 45 : 0 } },
    yAxis: { type: "value", ...AX, axisLabel: { color: COLORS.muted, formatter: v => v.toFixed(1) + "%" } },
    series: [{
      type: "bar",
      barCategoryGap: "6%",   // плотные столбики
      data: pts.map(p => ({
        value: +(p.pct * 100).toFixed(3),
        itemStyle: { color: p.pct >= 0 ? COLORS.green : COLORS.red, borderRadius: [3, 3, 0, 0] },
      })),
    }],
  });
}

async function loadReturns(period) {
  _returnsPeriod = period;
  document.querySelectorAll(".returns-btn").forEach(b => {
    b.classList.toggle("active", b.dataset.period === period);
  });
  try {
    const data = await api("/returns?period=" + period);
    renderReturns(data);
  } catch(e) { console.error("returns error", e); }
}

document.querySelectorAll(".returns-btn").forEach(b => {
  b.onclick = () => loadReturns(b.dataset.period);
});

// ===== FULLCALENDAR =====
const EVCOLOR = { "Купон": COLORS.teal, "Проценты": COLORS.amber, "Дивиденд": COLORS.purple,
  "Погашение": COLORS.blue, "Возврат вклада": COLORS.blue };
let _fc = null;

function initFullCalendar(events) {
  const fcEvents = events.map(e => ({
    title: e.instrument,
    start: e.date,
    backgroundColor: EVCOLOR[e.type] || COLORS.teal,
    borderColor: "transparent",
    textColor: "#0e1116",
    extendedProps: { type: e.type, amount: e.amount, name: e.instrument },
  }));

  if (!_fc) {
    _fc = new FullCalendar.Calendar(document.getElementById("fc-calendar"), {
      locale: "ru",
      firstDay: 1,
      weekNumberCalculation: "ISO",
      initialView: window.innerWidth <= 720 ? "listMonth" : "dayGridMonth",
      headerToolbar: { left: "prev,next today", center: "title", right: "dayGridMonth,listMonth" },
      buttonText: { today: "Сегодня", month: "Календарь", list: "Список" },
      fixedWeekCount: false,
      showNonCurrentDates: false,
      dayMaxEvents: 2,
      moreLinkText: count => `+${count}`,
      displayEventTime: false,
      eventOrder: "start,type,name",
      noEventsContent: "В этом месяце выплат нет",
      listDayFormat: { weekday: "long", day: "numeric", month: "long" },
      listDaySideFormat: false,
      height: "auto",
      events: fcEvents,
      eventContent: info => {
        const p = info.event.extendedProps;
        const amount = p.amount
          ? p.amount.toLocaleString("ru-RU", { maximumFractionDigits: 0 }) + " ₽"
          : "";
        if (info.view.type === "dayGridMonth") {
          const shortName = p.name.split(" ")[0];
          return { html: `<span class="fc-event-name">${escapeHtml(shortName)}</span><strong class="fc-event-amount">${amount}</strong>` };
        }
        return { html: `<span class="fc-event-copy"><strong>${escapeHtml(p.name)}</strong><small>${escapeHtml(p.type)}</small></span><strong class="fc-event-list-amount">${amount}</strong>` };
      },
      eventClick: info => {
        const p = info.event.extendedProps;
        toast(`${p.name} — ${p.type}: ${fmt(p.amount, 2)}`);
      },
      eventDidMount: info => {
        info.el.title = `${info.event.extendedProps.name} — ${info.event.extendedProps.type}`;
      },
    });
    _fc.render();
  } else {
    _fc.removeAllEvents();
    _fc.addEventSource(fcEvents);
  }
}

// ===== CALENDAR LIST (СПИСОК ВЫПЛАТ) =====
function renderCalList(events) {
  const wrap = $("#calendar");
  if (!events.length) {
    wrap.innerHTML = '<div class="calendar-empty">Ближайших выплат пока нет</div>';
    return;
  }
  wrap.innerHTML = events.slice(0, 30).map(e => {
    const color = EVCOLOR[e.type] || COLORS.muted;
    const d = e.date
      ? new Date(e.date + "T00:00:00").toLocaleDateString("ru-RU", { day: "2-digit", month: "short" }).replace(".", "")
      : "";
    return `<div class="cal-event" style="border-left:2px solid ${color}22">
      <span class="cal-event-date">${d}</span>
      <span class="cal-event-name" title="${escapeHtml(e.instrument)}">${escapeHtml(e.instrument)}</span>
      <span class="cal-event-amt" style="color:${color}">${fmt(e.amount, 0)}</span>
      <span class="cal-event-type">${escapeHtml(e.type)}</span>
    </div>`;
  }).join("");
}

// ===== PASSIVE INCOME =====
let _perSec = 0;
let _counterStarted = false;

function startLiveCounter(annual) {
  _perSec = annual / (365 * 24 * 3600);
  if (_counterStarted) return;
  _counterStarted = true;
  setInterval(() => {
    const now = new Date();
    const sod = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const secs = (now - sod) / 1000;
    const el = $("#live-counter");
    if (el) el.textContent = (_perSec * secs).toLocaleString("ru-RU",
      { minimumFractionDigits: 3, maximumFractionDigits: 3 }) + " ₽";
  }, 250);
}

function updateLiveCounterRate(annual) {
  _perSec = annual / (365 * 24 * 3600);
}

function renderPassive(p) {
  const annual = p.annual || 0;
  updateLiveCounterRate(annual);
  if (!_counterStarted) startLiveCounter(annual);

  const r = (v, d) => v.toLocaleString("ru-RU", { minimumFractionDigits: d, maximumFractionDigits: d }) + " ₽";
  const perDay = annual / 365;
  const perHour = perDay / 24;
  const perMin = perHour / 60;
  const perSec = perMin / 60;

  const rows = [
    { lbl: "В год", val: fmt(annual) },
    { lbl: "В месяц", val: fmt(annual / 12) },
  ];

  $("#passive").innerHTML =
    rows.map(row => `<div class="passive-row"><span class="lbl">${row.lbl}</span><span class="val">${row.val}</span></div>`).join("") +
    `<div class="passive-rates">
      <div class="passive-rate"><div class="rate-lbl">в день</div><div class="rate-val">${r(perDay, 0)}</div></div>
      <div class="passive-rate"><div class="rate-lbl">в час</div><div class="rate-val">${r(perHour, 1)}</div></div>
      <div class="passive-rate"><div class="rate-lbl">в минуту</div><div class="rate-val">${r(perMin, 3)}</div></div>
      <div class="passive-rate"><div class="rate-lbl">в секунду</div><div class="rate-val">${r(perSec, 5)}</div></div>
    </div>` +
    (p.detail || []).sort((a, b) => b.annual - a.annual).map(d =>
      `<div class="passive-row"><span class="lbl">${d.name}</span><span class="val">${fmt(d.annual)}/год</span></div>`
    ).join("");
}

// ===== POSITIONS TABLE =====
const KIND_RU = { bond: "Облигация", share: "Акция", etf: "Фонд", currency: "Валюта", deposit: "Вклад" };
const _GROUP_ORDER = ["bond", "etf", "share", "currency", "deposit"];
const _GROUP_RU = { bond: "Облигации", etf: "Фонды", share: "Акции", currency: "Валюта", deposit: "Вклады" };
let _fxLabel = "";

function renderPositions(pos) {
  const head = `<thead><tr>
    <th>Инструмент</th><th>Тип</th><th>Кол-во</th>
    <th>Себестоимость</th><th>Стоимость</th><th>Выплаты</th><th>P&L</th><th>%</th>
  </tr></thead>`;

  const groups = {};
  for (const p of pos) (groups[p.kind] = groups[p.kind] || []).push(p);

  let body = "";
  for (const kind of _GROUP_ORDER) {
    const items = groups[kind];
    if (!items || !items.length) continue;
    body += `<tr class="group-row"><td colspan="8">${_GROUP_RU[kind]}</td></tr>`;
    body += items.map(p => {
      const isFx = p.kind === "currency" && p.currency !== "RUB";
      const isMaturedDeposit = p.kind === "deposit" && p.meta?.close_date
        && p.meta.close_date < new Date().toISOString().slice(0, 10);
      const sub = isFx && _fxLabel
        ? `<div class="instrument-sub">${escapeHtml(_fxLabel)}</div>`
        : isMaturedDeposit
          ? '<div class="instrument-sub warning">Срок завершён · сверьте фактическую выплату</div>'
          : "";
      return `<tr>
        <td>${escapeHtml(p.name)}${sub}</td>
        <td><span class="kind-badge">${escapeHtml(KIND_RU[p.kind] || p.kind)}</span></td>
        <td class="num">${p.qty.toLocaleString("ru-RU")}</td>
        <td class="num">${fmt(p.cost_basis ?? p.invested)}</td>
        <td class="num">${fmt(p.value)}</td>
        <td class="${cls(p.income)}">${p.income ? fmt(p.income, 2) : "—"}</td>
        <td class="${cls(p.pnl)}">${fmt(p.pnl, 2)}</td>
        <td class="${cls(p.pnl_pct)}">${pct(p.pnl_pct)}</td>
      </tr>`;
    }).join("");
  }
  if (!body) {
    body = '<tr class="empty-row"><td colspan="8"><strong>Пока нет позиций</strong><span>Импортируйте T-Invest или добавьте вклад вручную.</span></td></tr>';
  }
  $("#positions").innerHTML = head + "<tbody>" + body + "</tbody>";
}

// ===== PRICE HISTORY =====
let _priceHistoryData = [];

async function loadPriceHistory() {
  const days = $("#price-hist-days").value;
  _priceHistoryData = await api("/prices/history?days=" + days);
  const sel = $("#price-hist-inst");
  const prev = sel.value;
  sel.innerHTML = '<option value="">выберите инструмент…</option>' +
    _priceHistoryData.map(d => `<option value="${d.id}">${d.name}</option>`).join("");
  if (prev && _priceHistoryData.find(d => String(d.id) === prev)) sel.value = prev;
  renderPriceChart();
}

function renderPriceChart() {
  const id = $("#price-hist-inst").value;
  if (!id) {
    chart("chart-prices", { graphic: [{ type: "text", left: "center", top: "middle",
      style: { text: "Выберите инструмент", fill: COLORS.muted, fontSize: 13 } }] });
    return;
  }
  const d = _priceHistoryData.find(x => String(x.id) === id);
  if (!d || !d.history.length) {
    chart("chart-prices", { graphic: [{ type: "text", left: "center", top: "middle",
      style: { text: "Нет данных — нажмите ⟳ Цены", fill: COLORS.muted, fontSize: 13 } }] });
    return;
  }
  const label = d.kind === "currency" ? `${d.currency}/RUB` : `${d.name}, ₽`;
  chart("chart-prices", {
    aria: { enabled: true, description: `История цены инструмента ${d.name}` },
    grid: { left: 70, right: 16, top: 30, bottom: 30 },
    tooltip: { trigger: "axis", valueFormatter: v => v.toLocaleString("ru-RU", { minimumFractionDigits: 2 }) },
    xAxis: { type: "category", data: d.history.map(h => h.ts.slice(0, 16).replace("T", " ")),
      ...AX, axisLabel: { color: COLORS.muted, rotate: 30 } },
    yAxis: { type: "value", ...AX, scale: true,
      axisLabel: { color: COLORS.muted, formatter: v => v.toLocaleString("ru-RU") } },
    series: [{ name: label, type: "line", smooth: false, symbol: "circle", symbolSize: 4,
      data: d.history.map(h => +h.price.toFixed(4)),
      lineStyle: { width: 2, color: COLORS.amber }, itemStyle: { color: COLORS.amber },
      areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1,
        [{ offset: 0, color: "rgba(244,196,87,.2)" }, { offset: 1, color: "rgba(244,196,87,0)" }]) } }],
  });
}

$("#price-hist-inst").onchange = renderPriceChart;
$("#price-hist-days").onchange = loadPriceHistory;

// ===== MODAL: DEPOSIT =====
const DAY_MS = 24 * 60 * 60 * 1000;

function _dateFromInput(value) {
  return value ? new Date(value + "T00:00:00Z") : null;
}

function _addMonthsUtc(date, months) {
  const year = date.getUTCFullYear() + Math.floor((date.getUTCMonth() + months) / 12);
  const month = (date.getUTCMonth() + months) % 12;
  const lastDay = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  return new Date(Date.UTC(year, month, Math.min(date.getUTCDate(), lastDay)));
}

function updateDepositPreview() {
  const principal = Number($("#m-principal").value);
  const annualRate = Number($("#m-rate").value) / 100;
  const openDate = _dateFromInput($("#m-open-date").value);
  const closeDate = _dateFromInput($("#m-close-date").value);
  const preview = $("#deposit-preview");
  if (!(principal > 0) || !(annualRate >= 0) || !openDate || !closeDate || closeDate <= openDate) {
    preview.textContent = "Заполните сумму, даты и ставку — здесь появится расчёт.";
    preview.classList.remove("ready");
    return;
  }

  let finalValue;
  if ($("#m-interest-mode").value === "simple") {
    const days = (closeDate - openDate) / DAY_MS;
    finalValue = principal * (1 + annualRate * days / 365);
  } else {
    let months = Math.max(0,
      (closeDate.getUTCFullYear() - openDate.getUTCFullYear()) * 12
      + closeDate.getUTCMonth() - openDate.getUTCMonth());
    while (months > 0 && _addMonthsUtc(openDate, months) > closeDate) months -= 1;
    while (_addMonthsUtc(openDate, months + 1) <= closeDate) months += 1;
    const anchor = _addMonthsUtc(openDate, months);
    const remainderDays = (closeDate - anchor) / DAY_MS;
    finalValue = principal * (1 + annualRate / 12) ** months
      * (1 + annualRate * remainderDays / 365);
  }
  const interest = finalValue - principal;
  preview.innerHTML = `<span>Ожидаемый доход</span><strong>${fmt(interest, 2)}</strong><small>К концу срока: ${fmt(finalValue, 2)} · оценка до налогов</small>`;
  preview.classList.add("ready");
}

function openModal() {
  $("#modal-overlay").classList.remove("hidden");
  const now = new Date();
  const today = new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()));
  $("#m-open-date").value = today.toISOString().slice(0, 10);
  $("#m-close-date").value = _addMonthsUtc(today, 6).toISOString().slice(0, 10);
  $("#m-name").value = ""; $("#m-principal").value = "";
  $("#m-rate").value = ""; $("#m-interest-mode").value = "simple";
  updateDepositPreview();
  setTimeout(() => $("#m-name").focus(), 0);
}
function closeModal() { $("#modal-overlay").classList.add("hidden"); }

async function saveModal(event) {
  event?.preventDefault();
  const form = $("#deposit-form");
  if (!form.reportValidity()) return;
  const name = $("#m-name").value.trim();
  if (!name) { toast("Укажите название"); return; }
  const principal = Number($("#m-principal").value);
  const annualRatePct = Number($("#m-rate").value);
  const openDate = $("#m-open-date").value;
  const closeDate = $("#m-close-date").value;
  if (_dateFromInput(closeDate) <= _dateFromInput(openDate)) {
    toast("Дата закрытия должна быть позже даты открытия", "err");
    return;
  }

  const button = $("#modal-save");
  button.disabled = true;
  try {
    const result = await api("/deposits", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        principal,
        open_date: openDate,
        close_date: closeDate,
        annual_rate_pct: annualRatePct,
        interest_mode: $("#m-interest-mode").value,
      }),
    });
    closeModal();
    toast(`Вклад добавлен · ожидаемый доход ${fmt(result.estimated_interest, 2)}`);
    await loadAll();
  } catch (error) {
    toast("Не удалось добавить вклад: " + error.message, "err");
  } finally {
    button.disabled = false;
  }
}

$("#btn-add").onclick = openModal;
$("#modal-close").onclick = closeModal;
$("#modal-cancel").onclick = closeModal;
$("#modal-overlay").onclick = e => { if (e.target === $("#modal-overlay")) closeModal(); };
$("#deposit-form").onsubmit = saveModal;
document.addEventListener("keydown", event => {
  if (event.key === "Escape" && !$("#modal-overlay").classList.contains("hidden")) closeModal();
  if (event.key === "Escape" && !$("#backup-overlay").classList.contains("hidden")) closeBackupModal();
});
["#m-principal", "#m-open-date", "#m-close-date", "#m-rate"].forEach(id => {
  $(id).addEventListener("input", updateDepositPreview);
});
$("#m-interest-mode").onchange = () => {
  $("#m-mode-help").textContent = $("#m-interest-mode").value === "simple"
    ? "Простые проценты начисляются по дням."
    : "Проценты ежемесячно прибавляются к сумме вклада.";
  updateDepositPreview();
};

// ===== BUTTON HANDLERS =====
let _appStatus = null;
let _fxSourceInitialized = false;
let _backupItems = [];

function backupDate(value) {
  if (!value) return "дата неизвестна";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
  }).format(new Date(value));
}

function backupSize(bytes) {
  if (!Number.isFinite(bytes)) return "";
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} КБ`;
  return `${(bytes / 1024 / 1024).toFixed(1)} МБ`;
}

function renderBackupConfig(status) {
  const box = $("#backup-status");
  const help = $("#backup-help");
  const create = $("#backup-create");
  box.classList.remove("ready", "error");
  if (!status?.configured) {
    box.classList.add("error");
    box.querySelector("strong").textContent = "Репозиторий не настроен";
    box.querySelector("small").textContent = "Укажите BACKUP_GIT_REPOSITORY в локальном .env.";
    help.classList.remove("hidden");
    create.disabled = true;
    return false;
  }
  if (!status.git_available) {
    box.classList.add("error");
    box.querySelector("strong").textContent = "Git не найден";
    box.querySelector("small").textContent = "Установите Git и перезапустите приложение.";
    help.classList.remove("hidden");
    create.disabled = true;
    return false;
  }
  box.classList.add("ready");
  box.querySelector("strong").textContent = "Приватный репозиторий подключён";
  box.querySelector("small").textContent = status.latest_local
    ? `Последняя локальная копия: ${backupDate(status.latest_local.created_at)}`
    : "Копий на этом компьютере пока нет.";
  help.classList.add("hidden");
  create.disabled = false;
  return true;
}

function renderBackupList(items) {
  _backupItems = Array.isArray(items) ? items : [];
  const select = $("#backup-select");
  const restore = $("#backup-restore");
  select.replaceChildren();
  if (!_backupItems.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "Бэкапов пока нет";
    select.appendChild(option);
    select.disabled = true;
    restore.disabled = true;
    $("#backup-meta").textContent = "Создайте первую резервную копию текущей базы.";
    return;
  }
  _backupItems.forEach(item => {
    const option = document.createElement("option");
    option.value = item.name;
    option.textContent = `${backupDate(item.created_at)} · ${backupSize(item.size_bytes)}`;
    select.appendChild(option);
  });
  select.disabled = false;
  restore.disabled = false;
  updateBackupMeta();
}

function updateBackupMeta() {
  const item = _backupItems.find(entry => entry.name === $("#backup-select").value);
  $("#backup-meta").textContent = item
    ? `${item.name} · ${backupSize(item.size_bytes)}. Текущая база будет сохранена локально.`
    : "Перед восстановлением текущая база будет сохранена локально.";
}

async function loadBackupList() {
  const select = $("#backup-select");
  const restore = $("#backup-restore");
  select.disabled = true;
  restore.disabled = true;
  select.replaceChildren(new Option("Обновляем список…", ""));
  try {
    const result = await api("/backups");
    renderBackupList(result.items);
  } catch (error) {
    renderBackupList([]);
    $("#backup-meta").textContent = error.message;
    throw error;
  }
}

async function openBackupModal() {
  $("#backup-overlay").classList.remove("hidden");
  if (!renderBackupConfig(_appStatus?.backups)) {
    renderBackupList([]);
    return;
  }
  try {
    await loadBackupList();
  } catch (error) {
    toast("Не удалось получить список бэкапов: " + error.message, "err");
  }
}

function closeBackupModal() {
  $("#backup-overlay").classList.add("hidden");
}

async function createGitBackup() {
  const accepted = window.confirm(
    "Создать и отправить незашифрованную копию базы в настроенный приватный репозиторий?"
  );
  if (!accepted) return;
  const button = $("#backup-create");
  button.disabled = true;
  button.textContent = "Сохраняем…";
  toast("Создаём и отправляем резервную копию…");
  try {
    const result = await api("/backups", { method: "POST" });
    toast(`Бэкап ${result.backup.name} отправлен ✓`);
    _appStatus = await api("/status");
    renderBackupConfig(_appStatus.backups);
    await loadBackupList();
  } catch (error) {
    toast("Не удалось создать бэкап: " + error.message, "err");
  } finally {
    button.textContent = "Создать бэкап";
    button.disabled = !(_appStatus?.backups?.configured && _appStatus?.backups?.git_available);
  }
}

async function restoreGitBackup() {
  const filename = $("#backup-select").value;
  if (!filename) return;
  const accepted = window.confirm(
    `Восстановить ${filename}? Текущая база будет сохранена локально, затем полностью заменена.`
  );
  if (!accepted) return;
  const button = $("#backup-restore");
  button.disabled = true;
  button.textContent = "Восстанавливаем…";
  toast("Проверяем и восстанавливаем базу…");
  try {
    const result = await api("/backups/restore", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename, confirm: true }),
    });
    toast(`Восстановлено из ${result.restored.name} ✓`);
    setTimeout(() => window.location.reload(), 1400);
  } catch (error) {
    toast("Не удалось восстановить базу: " + error.message, "err");
    button.disabled = false;
    button.textContent = "Восстановить";
  }
}

async function act(path, msg) {
  toast("…");
  try {
    const result = await api(path, { method: "POST" });
    toast(msg + " ✓");
    return result;
  } catch(e) {
    toast(msg + ": " + e.message, "err");
    return null;
  } finally {
    await loadAll();
  }
}

async function syncTinvest() {
  if (_appStatus && !_appStatus.tinvest.configured) {
    toast("Сначала добавьте read-only TINVEST_TOKEN в .env и перезапустите приложение", "err");
    return;
  }
  toast("Импортирую операции и цены T-Invest…");
  try {
    const result = await api("/sync/tinvest?days=3650", { method: "POST" });
    const warning = result.warnings?.length ? ` · предупреждений: ${result.warnings.length}` : "";
    toast(`T-Invest: новых операций ${result.imported}, цен ${result.prices_updated}${warning}`);
  } catch (error) {
    toast("T-Invest: " + error.message, "err");
  }
  await loadAll();
}

async function chooseTrackingStart() {
  const current = _appStatus?.tracking_start_date || `${new Date().getFullYear()}-01-01`;
  const value = window.prompt("С какой даты учитывать портфель? Формат: ГГГГ-ММ-ДД", current);
  if (value === null) return;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    toast("Введите дату в формате ГГГГ-ММ-ДД", "err");
    return;
  }
  const accepted = window.confirm(
    `Начать учёт с ${value}? Перед очисткой старых импортированных операций будет создана резервная копия.`
  );
  if (!accepted) return;
  toast("Настраиваю период учёта…");
  try {
    const result = await api("/settings/tracking-start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ start_date: value, confirm: true }),
    });
    toast(`Учёт начинается ${result.start_date} · удалено старых позиций: ${result.deleted.instruments}`);
  } catch (error) {
    toast("Не удалось изменить начало учёта: " + error.message, "err");
  }
  await loadAll();
}

async function applyFxSource() {
  const src = $("#fx-source").value;
  toast("Загружаю курс…");
  try {
    const r = await api("/fetch/fx?source=" + src, { method: "POST" });
    _fxLabel = r.source_label || src;
    toast(_fxLabel + " · обновлено");
  } catch(e) { toast("Ошибка курса", "err"); }
  await loadAll();
}

$("#btn-reload").onclick = async () => {
  toast("Обновление…");
  const completed = [];
  const errors = [];
  let snapshotCreated = false;
  try {
    if (_appStatus?.tinvest.configured) {
      try {
        await api("/sync/tinvest?days=3650", { method: "POST" });
        completed.push("T-Invest");
        snapshotCreated = true;
      } catch (error) { errors.push("T-Invest: " + error.message); }
    }
    try {
      const result = await api("/fetch/fx?source=" + $("#fx-source").value, { method: "POST" });
      _fxLabel = result.source_label || "";
      completed.push("курсы");
    } catch (error) { errors.push("курсы: " + error.message); }
    if (!snapshotCreated) {
      await api("/snapshot", { method: "POST" });
      completed.push("снимок");
    }
    if (errors.length) toast(errors.join(" · "), "err");
    else toast("Обновлено: " + completed.join(", "));
  } catch(e) { toast("Ошибка обновления: " + e.message, "err"); }
  await loadAll();
};

$("#btn-snap").onclick  = () => act("/snapshot", "Снимок");
$("#btn-excel").onclick = async () => {
  toast("Генерация Excel…");
  try {
    const resp = await fetch("/api/export/excel");
    if (!resp.ok) {
      const txt = await resp.text();
      toast("Ошибка Excel: " + txt.slice(0, 120), "err");
      return;
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `portfolio_${new Date().toISOString().slice(0,10)}.xlsx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    toast("Excel скачан ✓");
  } catch(e) { toast("Ошибка Excel: " + e.message, "err"); }
};
$("#btn-prices").onclick = async () => {
  const result = await act("/fetch/prices", "Цены обновлены");
  if (result) toast(`Обновлено инструментов: ${result.updated?.length || 0}`);
};
$("#btn-sync").onclick = syncTinvest;
$("#btn-tracking-start").onclick = chooseTrackingStart;
$("#btn-fx").onclick = applyFxSource;
$("#btn-backups").onclick = openBackupModal;
$("#backup-close").onclick = closeBackupModal;
$("#backup-cancel").onclick = closeBackupModal;
$("#backup-overlay").onclick = event => { if (event.target === $("#backup-overlay")) closeBackupModal(); };
$("#backup-create").onclick = createGitBackup;
$("#backup-restore").onclick = restoreGitBackup;
$("#backup-select").onchange = updateBackupMeta;
$("#fx-source").onchange = applyFxSource;
$("#onboarding-sync").onclick = syncTinvest;
$("#onboarding-tracking").onclick = chooseTrackingStart;
$("#onboarding-deposit").onclick = openModal;

function renderOnboarding(status) {
  const panel = $("#onboarding");
  const empty = !status.data.instruments;
  const configured = status.tinvest.configured;
  panel.classList.toggle("hidden", !empty && configured);
  if (!empty && !configured) {
    $("#onboarding-title").textContent = "T-Invest сейчас не подключён";
    $("#onboarding-text").textContent = "Сохранённые данные доступны. Для следующего импорта добавьте read-only токен в .env и перезапустите приложение.";
  } else {
    $("#onboarding-title").textContent = configured ? "Импортируйте свой портфель" : "Подключите свои данные";
    $("#onboarding-text").textContent = configured
      ? "Токен найден, но локальная база пока пуста. Начните с импорта."
      : "База пока пуста. Данные хранятся только на этом компьютере.";
  }
  $("#onboarding-sync").disabled = !configured;
  $("#onboarding-sync").title = configured ? "" : "Добавьте TINVEST_TOKEN в .env и перезапустите приложение";
  const trackingLabel = status.tracking_start_date
    ? `Учёт с ${status.tracking_start_date.split("-").reverse().join(".")}`
    : "Учёт с…";
  $("#btn-tracking-start").textContent = trackingLabel;
}

// ===== MAIN LOAD =====
async function loadAll() {
  try {
    const today = new Date().toISOString().slice(0, 10);
    const [status, s, hist, calEvents, passive] = await Promise.all([
      api("/status"), api("/summary"), api("/history"),
      api("/calendar?months=36&past=true"),
      api("/income"),
    ]);

    _appStatus = status;
    _portfolioGoal = Number(status.portfolio_goal) > 0 ? Number(status.portfolio_goal) : 1_000_000;
    renderOnboarding(status);
    if (!_fxSourceInitialized && status.fx_source) {
      $("#fx-source").value = status.fx_source;
      _fxSourceInitialized = true;
    }

    if ($("#asof")) $("#asof").textContent = "на " + s.as_of;
    renderKpis(s);
    renderValue(hist);
    renderAlloc(s);

    const all = Array.isArray(calEvents) ? calEvents : [];
    initFullCalendar(all);

    const upcoming = all.filter(e => e.date >= today);
    renderCalList(upcoming);

    const paySum = upcoming.filter(e => ["Купон","Проценты","Дивиденд"].includes(e.type))
      .reduce((a, e) => a + e.amount, 0);
    if ($("#cal-sum")) $("#cal-sum").textContent = "впереди " + fmt(paySum);

    renderPassive(passive);
    renderPositions(s.positions);

    // Параллельно грузим дополнительные данные
    const [returns, leaders] = await Promise.all([
      api("/returns?period=" + _returnsPeriod).catch(() => null),
      api("/leaders?period=" + _leadersPeriod).catch(() => null),
    ]);

    renderGamebar(s, returns);
    if (returns) renderReturns(returns);
    if (leaders) renderLeaders(leaders);

    await loadPriceHistory();
  } catch(e) {
    toast("Ошибка загрузки: " + e.message, "err");
    console.error(e);
  }
}

// ===== STARTUP =====
loadAll();
