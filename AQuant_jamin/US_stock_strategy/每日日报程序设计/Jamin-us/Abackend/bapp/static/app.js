const state = {
  dashboard: null,
  activeGroup: "全部",
  selectedSymbol: null,
  timerId: null,
};

const elements = {
  refreshButton: document.getElementById("refreshButton"),
  logicButton: document.getElementById("logicButton"),
  logicCloseButton: document.getElementById("logicCloseButton"),
  generatedAt: document.getElementById("generatedAt"),
  briefingHeadline: document.getElementById("briefingHeadline"),
  briefingSummary: document.getElementById("briefingSummary"),
  briefingLists: document.getElementById("briefingLists"),
  marketContext: document.getElementById("marketContext"),
  metricsGrid: document.getElementById("metricsGrid"),
  heatmap: document.getElementById("heatmap"),
  groupTabs: document.getElementById("groupTabs"),
  cardsContainer: document.getElementById("cardsContainer"),
  detailTitle: document.getElementById("detailTitle"),
  detailContent: document.getElementById("detailContent"),
  methodologyModal: document.getElementById("methodologyModal"),
  methodologyContent: document.getElementById("methodologyContent"),
  breakdownModal: document.getElementById("breakdownModal"),
  breakdownContent: document.getElementById("breakdownContent"),
  breakdownTitle: document.getElementById("breakdownTitle"),
  breakdownCloseButton: document.getElementById("breakdownCloseButton"),
  addSymbolForm: document.getElementById("addSymbolForm"),
  addSymbolInput: document.getElementById("addSymbolInput"),
  addSymbolStatus: document.getElementById("addSymbolStatus"),
  userWatchlistChips: document.getElementById("userWatchlistChips"),
};

function formatPercent(value) {
  if (value === null || value === undefined) return "n/a";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function formatPrice(value) {
  if (value === null || value === undefined) return "n/a";
  return Number(value).toLocaleString("zh-CN", {
    minimumFractionDigits: value >= 1000 ? 0 : 2,
    maximumFractionDigits: value >= 1000 ? 2 : 2,
  });
}

function changeClass(value) {
  if (value === null || value === undefined) return "change-flat";
  if (value > 0) return "change-positive";
  if (value < 0) return "change-negative";
  return "change-flat";
}

function createTag(label, value) {
  return `<span class="market-pill"><span class="small-label">${label}</span> ${value}</span>`;
}

function renderEarningsBadge(earnings) {
  if (!earnings || earnings.status !== "ok" || earnings.days_until === null || earnings.days_until === undefined) {
    return "";
  }
  const days = earnings.days_until;
  const bj = earnings.next_earnings_beijing || "";
  let tone = "earnings-far";
  let prefix = "";
  if (days < 0) {
    return "";
  } else if (days === 0) {
    tone = "earnings-today";
    prefix = "今日财报";
  } else if (days <= 7) {
    tone = "earnings-near";
    prefix = `${days} 天后财报`;
  } else if (days <= 30) {
    tone = "earnings-soon";
    prefix = `${days} 天后财报`;
  } else {
    prefix = `${days} 天后财报`;
  }
  return `<div class="earnings-badge ${tone}">
    <span class="earnings-icon">📅</span>
    <span class="earnings-text">${prefix} · 北京时间 ${bj}</span>
  </div>`;
}

function openBreakdownModal() {
  elements.breakdownModal.classList.remove("hidden");
  elements.breakdownModal.setAttribute("aria-hidden", "false");
}

function closeBreakdownModal() {
  elements.breakdownModal.classList.add("hidden");
  elements.breakdownModal.setAttribute("aria-hidden", "true");
}

function showBreakdownFor(symbol) {
  if (!state.dashboard) return;
  const item = state.dashboard.items.find((i) => i.symbol === symbol);
  if (!item) return;
  renderBreakdown(item);
  openBreakdownModal();
}

function formatSignedInt(value) {
  return `${value >= 0 ? "+" : ""}${value}`;
}

function formatRaw(raw) {
  if (raw === null || raw === undefined) return "—";
  if (typeof raw === "number") {
    if (Math.abs(raw) >= 100) return raw.toFixed(1);
    if (Math.abs(raw) >= 1) return raw.toFixed(2);
    return raw.toFixed(3);
  }
  return String(raw);
}

function renderBreakdown(item) {
  const signal = item.signal;
  const quote = item.quote;
  const breakdown = signal.score_breakdown || [];
  const trace = signal.label_trace || [];

  elements.breakdownTitle.textContent = `${item.symbol} · ${item.name} 打分明细`;

  const rows = breakdown
    .map((row) => {
      const contributionClass =
        row.contribution > 0 ? "contrib-positive" : row.contribution < 0 ? "contrib-negative" : "contrib-flat";
      const badge = row.is_base ? `<span class="tag-badge">起点</span>` : row.is_clamp ? `<span class="tag-badge tag-badge-warn">封顶</span>` : "";
      return `
        <div class="breakdown-row">
          <div class="breakdown-row-head">
            <strong>${row.name}</strong>
            ${badge}
            <span class="${contributionClass}">${formatSignedInt(row.contribution)}</span>
          </div>
          <p class="detail-copy">${row.detail}</p>
          <p class="small-label">原始值：${formatRaw(row.raw)}</p>
        </div>
      `;
    })
    .join("");

  const traceRows = trace
    .map((row) => {
      const icon = row.applied ? "✅" : row.matched ? "☑️" : "⬜";
      const rowClass = row.applied ? "trace-row trace-row-applied" : "trace-row";
      return `
        <div class="${rowClass}">
          <span class="trace-icon">${icon}</span>
          <div>
            <strong>${row.label}</strong>
            <p class="detail-copy">${row.condition}</p>
          </div>
        </div>
      `;
    })
    .join("");

  elements.breakdownContent.innerHTML = `
    <section class="detail-card">
      <div class="price-line">
        <span class="label-pill" style="background:${signal.style.color}">${signal.label}</span>
        <strong>${formatPrice(quote.price)} USD</strong>
        <span class="${changeClass(quote.change_pct)}">${formatPercent(quote.change_pct)}</span>
      </div>
      <p class="detail-copy">最终分数：<strong>${signal.score} / 100</strong> · 置信度 ${signal.confidence}%</p>
      <p class="detail-copy subtle">下面是从 50 分起点，各因子一项项加减到最终分的过程。</p>
    </section>

    <section class="detail-card">
      <h3>逐项贡献</h3>
      <div class="breakdown-list">${rows}</div>
    </section>

    <section class="detail-card">
      <h3>标签判定路径</h3>
      <p class="detail-copy subtle">规则自上而下，第一条命中就生效；✅ 表示最终采用的那一条。</p>
      <div class="trace-list">${traceRows}</div>
    </section>
  `;
}

function openMethodologyModal() {
  elements.methodologyModal.classList.remove("hidden");
  elements.methodologyModal.setAttribute("aria-hidden", "false");
}

function closeMethodologyModal() {
  elements.methodologyModal.classList.add("hidden");
  elements.methodologyModal.setAttribute("aria-hidden", "true");
}

function renderMethodology(methodology) {
  if (!methodology) {
    elements.methodologyContent.innerHTML = `<div class="error-box">暂时没有读取到标签计算逻辑。</div>`;
    return;
  }

  const renderLogicRows = (rows) =>
    rows
      .map(
        (row) => `
          <div class="logic-row">
            <div>
              <strong>${row.name || row.condition}</strong>
              <p class="detail-copy">${row.description || ""}</p>
            </div>
            <span class="logic-value">${row.value || row.points}</span>
          </div>
        `
      )
      .join("");

  const renderBulletList = (items) =>
    `<ul class="bullet-list">${items.map((item) => `<li>${item}</li>`).join("")}</ul>`;

  elements.methodologyContent.innerHTML = `
    <section class="detail-card">
      <h3>总原则</h3>
      <p class="detail-copy">${methodology.summary}</p>
    </section>

    <section class="methodology-grid">
      <article class="methodology-card">
        <h3>评分公式</h3>
        ${renderLogicRows(methodology.formula)}
      </article>
      <article class="methodology-card">
        <h3>当日涨跌加减分</h3>
        ${renderLogicRows(methodology.price_move_bands)}
      </article>
      <article class="methodology-card">
        <h3>相对强弱加减分</h3>
        ${renderLogicRows(methodology.relative_strength_bands)}
      </article>
    </section>

    <section class="methodology-grid">
      ${methodology.labels
        .map(
          (item) => `
            <article class="methodology-card label-rule-card" style="border-left-color:${item.color}">
              <h3>${item.label}</h3>
              <p class="detail-copy">${item.description}</p>
              ${renderBulletList(item.criteria)}
            </article>
          `
        )
        .join("")}
    </section>

    <section class="detail-card">
      <h3>口径说明</h3>
      ${renderBulletList(methodology.notes)}
    </section>
  `;
}

function renderBriefing(briefing) {
  elements.briefingHeadline.textContent = briefing.headline;
  elements.briefingSummary.textContent = briefing.summary;
  elements.marketContext.innerHTML = `
    ${createTag("QQQ", briefing.market_context.QQQ)}
    ${createTag("SOXX", briefing.market_context.SOXX)}
  `;

  const listEntries = [
    ["强烈试买", briefing.lists.strong || []],
    ["候选试买", briefing.lists.candidates],
    ["持有跟踪", briefing.lists.hold],
    ["观望", briefing.lists.watch],
    ["风险观察", briefing.lists.risk],
  ];
  elements.briefingLists.innerHTML = listEntries
    .map(
      ([title, items]) => `
        <article class="briefing-box">
          <p class="panel-kicker">${title}</p>
          <strong>${items.length ? items.join(" / ") : "暂无"}</strong>
        </article>
      `
    )
    .join("");
}

function renderMetrics(data) {
  const regime = data.market_regime || {};
  const regimeMap = { bullish: "牛市", bearish: "熊市", neutral: "震荡", unknown: "未知" };
  const regimeText = regimeMap[regime.regime] || "—";
  const regimeDetail = regime.price_vs_ma200_pct !== null && regime.price_vs_ma200_pct !== undefined
    ? `QQQ ${regime.price_vs_ma200_pct >= 0 ? "+" : ""}${regime.price_vs_ma200_pct}% vs 200D MA`
    : "";
  const metrics = [
    ["大盘", regimeText, regimeDetail],
    ["强烈试买", data.counts["强烈试买"] ?? 0],
    ["候选试买", data.counts["候选试买"] ?? 0],
    ["持有跟踪", data.counts["持有跟踪"] ?? 0],
    ["观望", data.counts["观望"] ?? 0],
    ["风险观察", data.counts["风险减仓观察"] ?? 0],
  ];

  elements.metricsGrid.innerHTML = metrics
    .map(
      (entry) => {
        const [label, value, hint] = entry;
        return `
        <article class="metric-card">
          <span class="metric-label">${label}</span>
          <strong class="metric-value">${value}</strong>
          ${hint ? `<span class="metric-hint">${hint}</span>` : ""}
        </article>
      `;
      }
    )
    .join("");
}

function renderHeatmap(items) {
  elements.heatmap.innerHTML = items
    .map((item) => {
      const signal = item.signal;
      const quote = item.quote;
      return `
        <article class="heatmap-card" style="border-left-color:${signal.style.color}">
          <div>
            <p class="panel-kicker">${item.group}</p>
            <h3>${item.symbol}</h3>
            <p class="detail-copy">${item.name}</p>
          </div>
          <div>
            <strong>${signal.label}</strong>
            <p class="${changeClass(quote.change_pct)}">${formatPercent(quote.change_pct)}</p>
            <p class="small-label">分数 ${signal.score}</p>
          </div>
        </article>
      `;
    })
    .join("");
}

function renderTabs(items) {
  const groups = ["全部", ...new Set(items.map((item) => item.group))];
  elements.groupTabs.innerHTML = groups
    .map(
      (group) => `
        <button class="tab-button ${group === state.activeGroup ? "active" : ""}" data-group="${group}">
          ${group}
        </button>
      `
    )
    .join("");

  elements.groupTabs.querySelectorAll(".tab-button").forEach((button) => {
    button.addEventListener("click", () => {
      state.activeGroup = button.dataset.group;
      renderTabs(items);
      renderCards();
    });
  });
}

function renderCards() {
  if (!state.dashboard) return;
  const items = state.dashboard.items.filter((item) => {
    if (state.activeGroup === "全部") return true;
    return item.group === state.activeGroup;
  });

  elements.cardsContainer.innerHTML = items
    .map((item) => {
      const signal = item.signal;
      const quote = item.quote;
      const isSelected = state.selectedSymbol === item.symbol;
      return `
        <article class="stock-card ${isSelected ? "selected" : ""}" data-symbol="${item.symbol}">
          <div class="stock-head">
            <div>
              <p class="panel-kicker">${item.group}</p>
              <h3>${item.symbol}</h3>
              <p class="detail-copy">${item.name}${item.industry_role ? " · " + item.industry_role : ""}</p>
            </div>
            <span class="label-pill" style="background:${signal.style.color}">
              ${signal.label}
            </span>
          </div>

          <div class="price-line">
            <span class="price-value">${formatPrice(quote.price)}</span>
            <span class="${changeClass(quote.change_pct)}">${formatPercent(quote.change_pct)}</span>
            <span class="small-label">${quote.session_label}</span>
          </div>

          ${renderEarningsBadge(item.earnings)}

          <div class="stock-meta">
            <div class="stat-box">
              <p class="small-label">评分</p>
              <strong>${signal.score} / 100</strong>
            </div>
            <div class="stat-box">
              <p class="small-label">池内排名</p>
              <strong>${signal.rank ?? "—"} / ${signal.rank_total ?? "—"}</strong>
            </div>
            <div class="stat-box">
              <p class="small-label">置信度</p>
              <strong>${signal.confidence}%</strong>
            </div>
          </div>

          <p class="detail-copy">${signal.action_hint}</p>

          <button class="breakdown-button" type="button" data-breakdown-symbol="${item.symbol}">
            查看打分明细
          </button>

          <div class="stock-footer">
            <div class="stat-box">
              <p class="small-label">相对 ${signal.benchmark_symbol}</p>
              <strong class="${changeClass(signal.relative_strength_pct)}">
                ${formatPercent(signal.relative_strength_pct)}
              </strong>
            </div>
            <div class="stat-box">
              <p class="small-label">联动</p>
              <strong>${item.chain_links.slice(0, 2).join(" / ") || "无"}</strong>
            </div>
          </div>
        </article>
      `;
    })
    .join("");

  elements.cardsContainer.querySelectorAll(".stock-card").forEach((card) => {
    card.addEventListener("click", () => {
      const { symbol } = card.dataset;
      state.selectedSymbol = symbol;
      renderCards();
      loadDetail(symbol);
    });
  });

  elements.cardsContainer.querySelectorAll(".breakdown-button").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      showBreakdownFor(button.dataset.breakdownSymbol);
    });
  });
}

function renderError(message) {
  elements.detailTitle.textContent = "加载失败";
  elements.detailContent.innerHTML = `<div class="error-box">${message}</div>`;
}

function attachDetailBreakdownButton() {
  const btn = document.getElementById("detailBreakdownButton");
  if (!btn) return;
  btn.addEventListener("click", () => showBreakdownFor(btn.dataset.breakdownSymbol));
}

function renderDetail(payload) {
  const { item, detail_sections: detailSections, linked_items: linkedItems } = payload;
  const signal = item.signal;
  const quote = item.quote;
  elements.detailTitle.textContent = `${item.symbol} · ${item.name}`;
  elements.detailContent.innerHTML = `
    <section class="detail-card">
      <div class="price-line">
        <span class="label-pill" style="background:${signal.style.color}">${signal.label}</span>
        <strong>${formatPrice(quote.price)} USD</strong>
        <span class="${changeClass(quote.change_pct)}">${formatPercent(quote.change_pct)}</span>
      </div>
      <p class="detail-copy">${signal.action_hint}</p>
      <button class="breakdown-button" type="button" id="detailBreakdownButton" data-breakdown-symbol="${item.symbol}">
        查看该股票打分明细
      </button>
      <div class="detail-stat-grid">
        <div class="stat-box">
          <p class="small-label">行业角色</p>
          <strong>${item.industry_role}</strong>
        </div>
        <div class="stat-box">
          <p class="small-label">会话</p>
          <strong>${quote.session_label}</strong>
        </div>
        <div class="stat-box">
          <p class="small-label">基准</p>
          <strong>${signal.benchmark_symbol}</strong>
        </div>
        <div class="stat-box">
          <p class="small-label">相对强弱</p>
          <strong class="${changeClass(signal.relative_strength_pct)}">${formatPercent(signal.relative_strength_pct)}</strong>
        </div>
      </div>
    </section>

    ${detailSections
      .map(
        (section) => `
          <section class="detail-card">
            <h3>${section.title}</h3>
            <p class="detail-copy">${section.content}</p>
          </section>
        `
      )
      .join("")}

    <section class="detail-card">
      <h3>结论依据</h3>
      <ul class="reason-list">
        ${signal.reasons.map((reason) => `<li>${reason}</li>`).join("")}
      </ul>
      <ul class="reason-list">
        ${signal.risks.map((risk) => `<li>${risk}</li>`).join("")}
      </ul>
    </section>

    <section class="detail-card">
      <h3>联动与催化</h3>
      <p class="detail-copy">联动标的用于辅助判断产业链确认强度，催化则提示后续关注点。</p>
      <ul class="chain-links">
        ${linkedItems
          .map(
            (linked) =>
              `<li>${linked.symbol} · ${linked.signal.label} · ${linked.signal.action_hint}</li>`
          )
          .join("")}
      </ul>
      <ul class="benchmark-list">
        ${item.catalysts.map((catalyst) => `<li>${catalyst}</li>`).join("")}
      </ul>
    </section>
  `;
}

async function loadDetail(symbol) {
  elements.detailContent.innerHTML = `<div class="loading">正在加载 ${symbol} 的详情...</div>`;
  try {
    const response = await fetch(`/api/watchlist/${symbol}`);
    if (!response.ok) {
      throw new Error(`详情接口返回 ${response.status}`);
    }
    const payload = await response.json();
    renderDetail(payload);
    attachDetailBreakdownButton();
  } catch (error) {
    renderError(`读取 ${symbol} 详情失败：${error.message}`);
  }
}

function installAutoRefresh(seconds) {
  if (state.timerId) {
    clearInterval(state.timerId);
  }
  state.timerId = window.setInterval(() => {
    loadDashboard(false);
  }, seconds * 1000);
}

async function loadDashboard(showLoading = true) {
  if (showLoading) {
    elements.cardsContainer.innerHTML = `<div class="loading">正在加载看板...</div>`;
  }

  try {
    const response = await fetch("/api/dashboard");
    if (!response.ok) {
      throw new Error(`看板接口返回 ${response.status}`);
    }

    const payload = await response.json();
    state.dashboard = payload;
    const freshnessLabel = payload.is_stale ? "当前显示的是上次成功数据" : "最近刷新";
    elements.generatedAt.textContent = `${freshnessLabel}：${payload.generated_at} | ${payload.status_message}`;

    renderMethodology(payload.methodology);
    renderBriefing(payload.briefing);
    renderMetrics(payload);
    renderHeatmap(payload.items);
    renderTabs(payload.items);

    if (!state.selectedSymbol && payload.items.length) {
      state.selectedSymbol = payload.items[0].symbol;
    }
    renderCards();
    if (state.selectedSymbol) {
      loadDetail(state.selectedSymbol);
    }

    installAutoRefresh(payload.refresh_hint_seconds || 20);
  } catch (error) {
    const message = `看板加载失败：${error.message}`;
    elements.cardsContainer.innerHTML = `<div class="error-box">${message}</div>`;
    renderError(message);
  }
}

async function loadUserWatchlist() {
  try {
    const response = await fetch("/api/user-watchlist");
    if (!response.ok) throw new Error(`状态码 ${response.status}`);
    const payload = await response.json();
    renderUserWatchlist(payload);
  } catch (error) {
    elements.userWatchlistChips.innerHTML = `<span class="error-box">自选股列表读取失败：${error.message}</span>`;
  }
}

function renderUserWatchlist(payload) {
  const builtinChips = (payload.builtin || [])
    .map(
      (item) => `
        <span class="chip chip-builtin" title="内置研究标的，无法移除">
          ${item.symbol}
        </span>
      `
    )
    .join("");

  const userChips = (payload.user || [])
    .map(
      (symbol) => `
        <span class="chip chip-user" data-symbol="${symbol}">
          ${symbol}
          <button class="chip-remove" data-symbol="${symbol}" type="button" aria-label="移除 ${symbol}">×</button>
        </span>
      `
    )
    .join("");

  const emptyHint = !payload.user || payload.user.length === 0
    ? `<span class="chip chip-empty">还没添加自选股</span>`
    : "";

  elements.userWatchlistChips.innerHTML = builtinChips + userChips + emptyHint;

  elements.userWatchlistChips.querySelectorAll(".chip-remove").forEach((button) => {
    button.addEventListener("click", async () => {
      const symbol = button.dataset.symbol;
      await removeUserSymbol(symbol);
    });
  });
}

function setAddSymbolStatus(message, tone = "info") {
  elements.addSymbolStatus.textContent = message || "";
  elements.addSymbolStatus.dataset.tone = tone;
}

async function addUserSymbol(symbol) {
  const normalized = symbol.trim().toUpperCase();
  if (!normalized) return;
  setAddSymbolStatus(`正在校验 ${normalized} ...`, "info");
  try {
    const response = await fetch("/api/user-watchlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol: normalized }),
    });
    const payload = await response.json();
    if (!response.ok) {
      setAddSymbolStatus(payload.detail || "添加失败", "error");
      return;
    }
    setAddSymbolStatus(payload.message || `${normalized} 已加入`, "success");
    elements.addSymbolInput.value = "";
    await loadUserWatchlist();
    await loadDashboard(false);
  } catch (error) {
    setAddSymbolStatus(`请求失败：${error.message}`, "error");
  }
}

async function removeUserSymbol(symbol) {
  try {
    const response = await fetch(`/api/user-watchlist/${symbol}`, { method: "DELETE" });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      setAddSymbolStatus(payload.detail || `移除 ${symbol} 失败`, "error");
      return;
    }
    setAddSymbolStatus(`${symbol} 已移除`, "success");
    if (state.selectedSymbol === symbol) {
      state.selectedSymbol = null;
    }
    await loadUserWatchlist();
    await loadDashboard(false);
  } catch (error) {
    setAddSymbolStatus(`请求失败：${error.message}`, "error");
  }
}

elements.addSymbolForm.addEventListener("submit", (event) => {
  event.preventDefault();
  addUserSymbol(elements.addSymbolInput.value);
});

elements.refreshButton.addEventListener("click", () => loadDashboard(true));
elements.logicButton.addEventListener("click", openMethodologyModal);
elements.logicCloseButton.addEventListener("click", closeMethodologyModal);
elements.methodologyModal.addEventListener("click", (event) => {
  if (event.target === elements.methodologyModal) {
    closeMethodologyModal();
  }
});
elements.breakdownCloseButton.addEventListener("click", closeBreakdownModal);
elements.breakdownModal.addEventListener("click", (event) => {
  if (event.target === elements.breakdownModal) {
    closeBreakdownModal();
  }
});
window.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeMethodologyModal();
    closeBreakdownModal();
  }
});

loadUserWatchlist();
loadDashboard(true);
// app.js 启动时调用
(async function decorateDailyButton() {
  try {
    const res = await fetch("/api/daily-reports");
    if (!res.ok) return;
    const data = await res.json();
    if (data.latest) {
      const btn = document.getElementById("btn-daily-report");
      if (btn) {
        btn.textContent = `📰 港美股日报 · ${data.latest.date}`;
        btn.href = data.latest.html_url; // 直接跳到最新一期
      }
    }
  } catch (_) {
    /* 静默失败，保留默认 /daily/ 跳转 */
  }
})();
