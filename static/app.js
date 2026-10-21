const $ = (id) => document.getElementById(id);
const money = (n) => n.toLocaleString(undefined, { style: "currency", currency: "USD" });

function localToday() {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 10);
}

function show(text, isError = false) {
  const el = $("msg");
  el.textContent = text;
  el.className = isError ? "error" : "muted";
}

async function api(path, options) {
  const headers = new Headers(options && options.headers ? options.headers : {});
  headers.set("X-CSRF-Token", document.querySelector('meta[name="csrf-token"]').content);
  const res = await fetch(path, { ...options, headers });
  if (res.status === 401) {
    location.href = "/login";
    throw new Error("Please log in again.");
  }
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Something went wrong.");
  return data;
}

function line(left, sub, amount, extra, amountClass = "") {
  const li = document.createElement("li");
  const info = document.createElement("div");
  const name = document.createElement("span");
  name.textContent = left;
  info.append(name);
  if (sub) {
    const small = document.createElement("small");
    small.textContent = sub;
    info.append(small);
  }
  const amt = document.createElement("span");
  amt.className = `amount ${amountClass}`;
  amt.textContent = money(amount);
  li.append(info, amt);
  if (extra) li.append(extra);
  return li;
}

function transactionRow(e) {
  const del = document.createElement("button");
  del.className = "quiet danger";
  del.textContent = "Remove";
  del.setAttribute(
    "aria-label",
    `Remove ${e.category} ${e.type} of ${money(e.amount)}`
  );
  del.onclick = async () => {
    if (!confirm(`Remove ${e.type}: ${e.category} (${money(e.amount)})?`)) return;
    try {
      await api(`/api/expenses/${e.id}`, { method: "DELETE" });
      show("Transaction removed.");
      await refresh();
    } catch (err) { show(err.message, true); }
  };
  const sign = e.type === "income" ? "+" : "−";
  const li = line(
    `${e.category} · ${e.type}`,
    e.note ? `${e.date}, ${e.note}` : e.date,
    e.amount,
    del,
    e.type === "income" ? "positive" : "negative"
  );
  li.querySelector(".amount").textContent = `${sign}${money(e.amount)}`;
  return li;
}

function monthLabel(month) {
  return new Date(`${month}-01T00:00:00`).toLocaleDateString(undefined, {
    month: "long",
    year: "numeric",
  });
}

function comparisonText(previousAmount, currentAmount, previousMonth) {
  const difference = currentAmount - previousAmount;
  let change;
  if (difference === 0) {
    change = "no change";
  } else {
    change = `${difference > 0 ? "up" : "down"} ${money(Math.abs(difference))}`;
  }
  return `${monthLabel(previousMonth)}: ${money(previousAmount)} · ${change}`;
}

function renderSummary(summary) {
  const previousMonth = summary.previous_month;
  $("income-total").textContent = money(summary.current.income);
  $("spent-total").textContent = money(summary.current.expenses);
  $("net-total").textContent = money(summary.current.net);
  $("income-compare").textContent = comparisonText(
    summary.previous.income, summary.current.income, previousMonth
  );
  $("spent-compare").textContent = comparisonText(
    summary.previous.expenses, summary.current.expenses, previousMonth
  );
  $("net-compare").textContent = comparisonText(
    summary.previous.net, summary.current.net, previousMonth
  );
  $("by-category").replaceChildren(
    ...summary.by_category.map((c) => line(c.category, "", c.total))
  );
  if (!summary.by_category.length) {
    const li = document.createElement("li");
    li.className = "muted";
    li.textContent = "No expenses recorded for this month.";
    $("by-category").replaceChildren(li);
  }
}

async function refresh() {
  const [data, summary] = await Promise.all([
    api("/api/expenses"),
    api(`/api/monthly-summary?month=${encodeURIComponent($("month").value)}`),
  ]);
  renderSummary(summary);
  $("categories").replaceChildren(
    ...data.by_category.map((c) => {
      const o = document.createElement("option");
      o.value = c.category;
      return o;
    })
  );
  if (data.transactions.length) {
    $("list").replaceChildren(...data.transactions.map(transactionRow));
  } else {
    const li = document.createElement("li");
    li.className = "muted";
    li.textContent = "No transactions yet. Add your first one above.";
    $("list").replaceChildren(li);
  }
}

$("month").value = localToday().slice(0, 7);
$("month").addEventListener("change", () => {
  refresh().catch((err) => show(err.message, true));
});

$("amount").addEventListener("input", (ev) => {
  const input = ev.currentTarget;
  const digits = input.value.replace(/\D/g, "");
  const cents = Math.min(Number(digits), 100_000_000);
  input.value = digits ? (cents / 100).toFixed(2) : "";
});

$("add-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  try {
    await api("/api/expenses", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        type: $("type").value,
        category: $("category").value,
        amount: $("amount").value,
        date: $("date").value,
        note: $("note").value,
      }),
    });
    $("category").value = "";
    $("amount").value = "";
    $("note").value = "";
    show("Transaction added.");
    await refresh();
    $("category").focus();
  } catch (err) { show(err.message, true); }
});

$("date").value = localToday();
refresh().catch((err) => show(err.message, true));
