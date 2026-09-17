const money = (n, code = "INR") =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: code, maximumFractionDigits: 0 }).format(n || 0);

const state = { user: null, data: null, cats: [], donut: null, bars: null, vaultOpen: false };

const qs = (s, el = document) => el.querySelector(s);
const qsa = (s, el = document) => [...el.querySelectorAll(s)];

const titles = {
  overview: "Overview",
  next: "Next options",
  history: "Year history",
  salary: "Salary & income",
  spend: "Monthly expenditures",
  phone: "Phone transactions",
  cash: "Cash transactions",
  sip: "SIP after savings",
  plans: "Financial saving",
  emi: "EMI after savings",
  budgets: "Budgets & bills",
  import: "Import CSV",
  fx: "Currency converter",
  vault: "Password vault",
  notes: "Memos",
  profile: "Profile",
};

const modeCopy = {
  personal: "Personal workspace: salary, household spend, then SIP / goals / EMI from leftover.",
  business: "Business workspace: revenue, payroll, vendors and GST, then surplus into reserves and loans.",
  student: "Student workspace: stipend, fees, hostel and mess, then small SIPs and semester goals.",
};

async function api(url, options = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (res.headers.get("content-type")?.includes("text/csv")) return res;
  const data = await res.json();
  if (!data.ok) throw new Error(data.error || "Request failed");
  return data;
}

function setView(name) {
  const slides = qsa(".slide");
  const index = slides.findIndex((el) => el.dataset.panel === name);
  slides.forEach((el, i) => {
    el.classList.remove("is-active", "is-prev", "is-next", "is-far");
    if (i === index) el.classList.add("is-active");
    else if (i === index - 1) el.classList.add("is-prev");
    else if (i === index + 1) el.classList.add("is-next");
    else el.classList.add("is-far");
  });
  qsa(".nav-btn").forEach((el) => el.classList.toggle("active", el.dataset.view === name));
  qs("#view-title").textContent = titles[name];
  qsa("#slide-dots button").forEach((dot, i) => dot.classList.toggle("on", i === index));
  if (name === "fx") loadFx();
  if (name === "vault" && state.vaultOpen) loadVault();
  setTimeout(() => {
    state.donut?.resize();
    state.bars?.resize();
  }, 720);
  state.view = name;
}

function shiftView(dir) {
  const slides = qsa(".slide");
  const index = slides.findIndex((el) => el.classList.contains("is-active"));
  const next = Math.min(slides.length - 1, Math.max(0, index + dir));
  setView(slides[next].dataset.panel);
}

function fillCats() {
  qsa("[data-cats]").forEach((select) => {
    select.innerHTML = state.cats.map((c) => `<option>${c}</option>`).join("");
  });
}

function txnRows(rows, tableId) {
  const el = qs(tableId);
  el.innerHTML = `<tr><th>Date</th><th>Detail</th><th>Channel</th><th>Amount</th><th></th></tr>` +
    rows.map((r) => `<tr>
      <td>${r.occurred_on}</td>
      <td>${r.title}<br /><span class="eyebrow">${r.category} · ${r.merchant || ""}</span></td>
      <td><span class="pill ${r.channel}">${r.channel}</span></td>
      <td>${money(r.amount, state.user.base_currency)}</td>
      <td><button class="danger" data-del="transactions" data-id="${r.id}">Remove</button></td>
    </tr>`).join("");
}

function render() {
  const d = state.data;
  const c = state.user.base_currency;
  qs("#hello").textContent = `Hello, ${state.user.full_name.split(" ")[0]}`;
  qs("#type-badge").textContent = state.user.account_type;
  qs("#org-line").textContent = [state.user.organization, state.user.city].filter(Boolean).join(" · ");
  qs("#mode-note").textContent = modeCopy[state.user.account_type];
  qs("#mode-note").classList.remove("hidden");
  qs("#export-link").href = `/api/export.csv?month=${qs("#month").value}`;

  qs("#kpis").innerHTML = [
    ["Income", d.kpis.income],
    ["Spent", d.kpis.spent],
    ["After-savings committed", d.kpis.committed],
    ["Free this month", d.kpis.saving],
  ].map(([k, v]) => `<article class="kpi"><span>${k}</span><b>${money(v, c)}</b></article>`).join("");

  const donutData = [d.donut.spent, d.donut.sip, d.donut.plans, d.donut.emi, d.donut.free];
  const donutLabels = ["Expenditure", "SIP", "Financial saving", "EMI", "Still free"];
  const colors = ["#c45c3e", "#6d28d9", "#a78bfa", "#4c1d95", "#ede9fe"];
  if (state.donut) state.donut.destroy();
  state.donut = new Chart(qs("#donut"), {
    type: "doughnut",
    data: { labels: donutLabels, datasets: [{ data: donutData, backgroundColor: colors, borderWidth: 0 }] },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: "bottom" } },
      cutout: "62%",
    },
  });
  if (state.bars) state.bars.destroy();
  state.bars = new Chart(qs("#bars"), {
    type: "bar",
    data: {
      labels: d.categories.map((x) => x.name),
      datasets: [{ data: d.categories.map((x) => x.value), backgroundColor: "#4c1d95" }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true } },
    },
  });

  qs("#income-table").innerHTML = `<tr><th>Title</th><th>Source</th><th>Credit</th><th>Amount</th><th></th></tr>` +
    d.incomes.map((r) => `<tr><td>${r.title}<br /><span class="eyebrow">${r.credit_code || ""}</span></td><td>${r.source}<br /><span class="eyebrow">${r.bank_name || ""}</span></td><td>${r.credit_date || r.month} · day ${r.credit_day}</td><td>${money(r.amount, c)}</td>
      <td><button class="danger" data-del="incomes" data-id="${r.id}">Remove</button></td></tr>`).join("");
  txnRows(d.transactions, "#spend-table");
  txnRows(d.transactions.filter((t) => t.channel === "phone"), "#phone-table");
  txnRows(d.transactions.filter((t) => t.channel === "cash"), "#cash-table");

  qs("#sip-list").innerHTML = d.sips.map((r) => `<div class="item">
    <div><b>${r.name}</b><div class="eyebrow">Invested ${money(r.invested, c)} · projected ${money(r.projected, c)}</div></div>
    <div>${money(r.monthly_amount, c)} / mo <button class="danger" data-del="sips" data-id="${r.id}">Remove</button></div>
  </div>`).join("") || "<p>No SIPs yet. Add from leftover savings.</p>";

  qs("#plan-list").innerHTML = d.savings.map((r) => `<div class="item">
    <div style="flex:1"><b>${r.name}</b> · ${r.kind}
      <div class="progress" style="margin-top:8px"><i style="width:${Math.min(r.progress, 100)}%"></i></div>
      <div class="eyebrow">${money(r.current_amount, c)} of ${money(r.target_amount, c)} · ${r.progress}%</div>
    </div>
    <button class="danger" data-del="savings" data-id="${r.id}">Remove</button>
  </div>`).join("") || "<p>Create an emergency or goal plan.</p>";

  qs("#emi-list").innerHTML = d.emis.map((r) => `<div class="item">
    <div><b>${r.name}</b><div class="eyebrow">${r.remaining} left · ${r.annual_rate}% </div></div>
    <div>${money(r.installment, c)} EMI <button class="danger" data-del="emis" data-id="${r.id}">Remove</button></div>
  </div>`).join("") || "<p>No EMIs on this leftover.</p>";

  qs("#budget-list").innerHTML = d.budgets.map((r) => `<div class="item">
    <div><b>${r.category}</b><div class="eyebrow">Used ${money(r.used, c)} / ${money(r.monthly_limit, c)}</div>
      <div class="progress"><i style="width:${Math.min(100, (r.used / r.monthly_limit) * 100 || 0)}%"></i></div></div>
    <button class="danger" data-del="budgets" data-id="${r.id}">Remove</button>
  </div>`).join("");

  qs("#bill-list").innerHTML = d.bills.map((r) => `<div class="item">
    <div><b>${r.name}</b><div class="eyebrow">Due day ${r.due_day}</div></div>
    <div>${money(r.amount, c)} <button class="danger" data-del="bills" data-id="${r.id}">Remove</button></div>
  </div>`).join("");

  qs("#memo-list").innerHTML = d.memos.map((r) => `<div class="item">
    <div><b>${r.title}</b><div class="eyebrow">${r.tag}</div><p>${r.body}</p></div>
    <button class="danger" data-del="memos" data-id="${r.id}">Remove</button>
  </div>`).join("");

  const pf = qs("#profile-form");
  pf.full_name.value = state.user.full_name;
  pf.organization.value = state.user.organization;
  pf.city.value = state.user.city;
  pf.base_currency.value = state.user.base_currency;
  if (pf.bank_name) pf.bank_name.value = state.user.bank_name || "";
  if (pf.salary_credit_day) pf.salary_credit_day.value = state.user.salary_credit_day || 1;

  const years = d.years || [];
  const yearSel = qs("#year");
  const currentYear = (qs("#month").value || "").slice(0, 4);
  yearSel.innerHTML = years.map((y) => `<option value="${y.year}">${y.year}</option>`).join("") || `<option>${new Date().getFullYear()}</option>`;
  if ([...yearSel.options].some((o) => o.value === currentYear)) yearSel.value = currentYear;
  qs("#year-grid").innerHTML = years.map((y) => `<article class="kpi"><span>${y.year} · ${y.months} months</span><b>${money(y.saved, c)}</b><div class="eyebrow">In ${money(y.income, c)} · Out ${money(y.spent, c)}</div></article>`).join("");
  const nxt = d.next || {};
  qs("#next-kpis").innerHTML = [
    ["Next salary credit", nxt.salary_on || "—"],
    ["Bank", nxt.bank || "Set in profile"],
    ["Suggested SIP", money(nxt.suggested_sip, c)],
    ["Emergency slice", money(nxt.suggested_emergency, c)],
  ].map(([k, v]) => `<article class="kpi"><span>${k}</span><b>${v}</b></article>`).join("");
  qs("#next-box").innerHTML = `<h3>What to do with leftover</h3>
    <p>After spend, park 40% in SIP, 30% in emergency, 30% as EMI buffer. Next salary day is <b>${nxt.salary_day}</b>${nxt.bank ? " at " + nxt.bank : ""}.</p>
    <div class="list">${(nxt.bills || []).map((b) => `<div class="item"><div>${b.name}</div><div>Due ${b.due_day} · ${money(b.amount, c)}</div></div>`).join("") || "<p>No recurring bills yet.</p>"}</div>`;
}

async function refresh() {
  const month = qs("#month").value;
  state.data = (await api(`/api/overview?month=${month}`));
  render();
}

async function boot() {
  const me = await api("/api/me");
  state.user = me.user;
  state.cats = me.categories;
  fillCats();
  const now = new Date();
  qs("#month").value = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  qsa("[name=month],[name=start_month]").forEach((el) => { if (el && !el.value) el.value = qs("#month").value; });
  const dots = qs("#slide-dots");
  dots.innerHTML = qsa(".slide").map((el) => `<button type="button" data-go="${el.dataset.panel}"></button>`).join("");
  qsa("#slide-dots button").forEach((dot) => dot.addEventListener("click", () => setView(dot.dataset.go)));
  await refresh();
  setView("overview");
}

qsa(".nav-btn").forEach((btn) => btn.addEventListener("click", () => setView(btn.dataset.view)));
qs("#slide-prev").addEventListener("click", () => shiftView(-1));
qs("#slide-next").addEventListener("click", () => shiftView(1));
document.addEventListener("keydown", (event) => {
  const tag = event.target.tagName;
  if (["INPUT", "SELECT", "TEXTAREA"].includes(tag)) return;
  if (event.key === "ArrowLeft") shiftView(-1);
  if (event.key === "ArrowRight") shiftView(1);
});
let startX = 0;
qs("#stage").addEventListener("pointerdown", (event) => { startX = event.clientX; });
qs("#stage").addEventListener("pointerup", (event) => {
  if (["INPUT", "SELECT", "TEXTAREA", "BUTTON"].includes(event.target.tagName)) return;
  const dx = event.clientX - startX;
  if (dx > 70) shiftView(-1);
  if (dx < -70) shiftView(1);
});
qs("#month").addEventListener("change", refresh);
qs("#year").addEventListener("change", () => {
  const monthPart = (qs("#month").value || "01-01").slice(5) || "01";
  qs("#month").value = `${qs("#year").value}-${monthPart}`;
  refresh();
});
qs("#csv-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const body = new FormData(event.target);
  const res = await fetch("/api/import/csv", { method: "POST", body });
  const data = await res.json();
  const msg = qs("#csv-msg");
  if (!data.ok) {
    msg.textContent = data.error;
    return;
  }
  msg.textContent = `Converted and added ${data.count} rows.`;
  qs("#csv-result").innerHTML = `<table class="table"><tr><th>Date</th><th>Title</th><th>Channel</th><th>Amount</th></tr>${
    (data.items || []).map((r) => `<tr><td>${r.occurred_on}</td><td>${r.title}</td><td>${r.channel}</td><td>${r.amount} (${r.direction})</td></tr>`).join("")
  }</table>`;
  await refresh();
});
qs("#logout").addEventListener("click", async () => {
  await api("/api/auth/logout", { method: "POST" });
  window.location.href = "/";
});

document.addEventListener("click", async (event) => {
  const btn = event.target.closest("[data-del]");
  if (!btn) return;
  await api(`/api/${btn.dataset.del}/${btn.dataset.id}`, { method: "DELETE" });
  await refresh();
  if (state.vaultOpen && btn.dataset.del === "vault") loadVault();
});

const formMap = {
  income: "/api/incomes",
  txn: "/api/transactions",
  sip: "/api/sips",
  saving: "/api/savings",
  emi: "/api/emis",
  budget: "/api/budgets",
  bill: "/api/bills",
  memo: "/api/memos",
  vault: "/api/vault",
};

qsa("[data-form]").forEach((form) => {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(form).entries());
    if (form.dataset.form === "txn") payload.direction = "out";
    if (payload.month === "") payload.month = qs("#month").value;
    await api(formMap[form.dataset.form], { method: "POST", body: JSON.stringify(payload) });
    form.reset();
    fillCats();
    await refresh();
    if (form.dataset.form === "vault") loadVault();
  });
});

qs("#profile-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(event.target).entries());
  const data = await api("/api/me", { method: "POST", body: JSON.stringify(payload) });
  state.user = data.user;
  render();
});

qs("#vault-unlock").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await api("/api/vault/unlock", { method: "POST", body: JSON.stringify({ pin: qs("#vault-pin").value }) });
    state.vaultOpen = true;
    qs("#vault-lock").classList.add("hidden");
    qs("#vault-box").classList.remove("hidden");
    loadVault();
  } catch (err) {
    qs("#vault-msg").textContent = err.message;
  }
});

qs("#vault-set").addEventListener("submit", async (event) => {
  event.preventDefault();
  await api("/api/vault/pin", { method: "POST", body: JSON.stringify({ pin: qs("#vault-new-pin").value }) });
  state.vaultOpen = true;
  qs("#vault-lock").classList.add("hidden");
  qs("#vault-box").classList.remove("hidden");
});

async function loadVault() {
  const data = await api("/api/vault");
  qs("#vault-list").innerHTML = data.items.map((r) => `<div class="item">
    <div><b>${r.label}</b><div class="eyebrow">${r.login_id} · ${r.website}</div>
      <code>${r.password}</code></div>
    <button class="danger" data-del="vault" data-id="${r.id}">Remove</button>
  </div>`).join("") || "<p>Vault is empty.</p>";
}

let fxCountries = [];
async function loadFx() {
  const data = await api("/api/currency");
  fxCountries = data.countries;
  const opts = fxCountries.map((c) => `<option value="${c.code}">${c.flag} ${c.country} (${c.code})</option>`).join("");
  qs("#fx-from").innerHTML = opts;
  qs("#fx-to").innerHTML = opts;
  qs("#fx-from").value = state.user.base_currency;
  qs("#fx-to").value = "USD";
  paintCountries("");
  qs("#fx-meta").textContent = data.live ? `Live · ${data.as_of}` : `Fallback rates · ${data.as_of}`;
}

function paintCountries(q) {
  const needle = q.toLowerCase();
  qs("#fx-countries").innerHTML = fxCountries
    .filter((c) => `${c.country} ${c.code}`.toLowerCase().includes(needle))
    .map((c) => `<div class="country-row"><span>${c.flag} ${c.country}</span><span>${c.code} ${c.symbol}</span></div>`)
    .join("");
}

qs("#fx-search").addEventListener("input", (e) => paintCountries(e.target.value));
qs("#fx-swap").addEventListener("click", () => {
  const a = qs("#fx-from").value;
  qs("#fx-from").value = qs("#fx-to").value;
  qs("#fx-to").value = a;
});
qs("#fx-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const from = qs("#fx-from").value;
  const to = qs("#fx-to").value;
  const amount = qs("#fx-amount").value;
  const data = await api(`/api/currency/convert?amount=${amount}&from=${from}&to=${to}`);
  qs("#fx-result").textContent = `${amount} ${from} = ${data.result.toFixed(2)} ${to}`;
  qs("#fx-meta").textContent = `Rate ${data.rate.toFixed(4)} · ${data.live ? "live" : "offline"} · ${data.as_of}`;
});

boot().catch(() => { window.location.href = "/login"; });
