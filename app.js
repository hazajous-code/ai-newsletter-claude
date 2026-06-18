/* AI 뉴스레터 대시보드 렌더러
 * data/latest.json 을 읽어 6개 섹션을 그린다. KO/EN 토글로 표시 언어를 전환한다.
 * LLM 미적용(fallback) 항목은 표시하되 작은 배지로 구분한다.
 */
(function () {
  "use strict";

  let LANG = "ko";
  let DATA = null;

  const $ = (sel) => document.querySelector(sel);
  const el = (tag, cls, html) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html != null) n.innerHTML = html;
    return n;
  };
  const esc = (s) =>
    String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])
    );
  const has = (s) => s != null && String(s).trim() !== "";

  // 언어에 맞는 텍스트 선택 (ko 우선/원문 fallback)
  const pick = (koVal, enVal) => {
    if (LANG === "en") return has(enVal) ? enVal : koVal || "";
    return has(koVal) ? koVal : enVal || "";
  };

  const fmtDate = (iso) => {
    if (!has(iso)) return "";
    const d = new Date(iso);
    if (isNaN(d)) return "";
    return d.toLocaleDateString("ko-KR", { month: "short", day: "numeric" });
  };

  const fallbackBadge = (item) =>
    item && item.llm === false ? '<span class="fallback-note">원문 기반</span>' : "";

  const emptyBox = (msg) =>
    `<div class="empty">${msg}<br><br>터미널에서 <code>python scrape_daily.py</code> 실행 후 새로고침하세요.</div>`;

  const pointsList = (arr) =>
    Array.isArray(arr) && arr.length
      ? `<ul class="points">${arr.map((p) => `<li>${esc(p)}</li>`).join("")}</ul>`
      : "";

  // ---------------- Stats ----------------
  function renderStats(d) {
    const s = d.stats || {};
    const items = [
      ["누적", s.cumulativeDays, "일"],
      ["뉴스", s.articleCount, "건"],
      ["구루", s.guruMentionCount, "건"],
      ["유튜브", s.youtubeBriefCount, "건"],
      ["논문", s.paperCount, "건"],
      ["출처", s.sourceCount, "개"],
    ];
    const stats = items
      .map(
        ([label, val, unit]) =>
          `<div class="stat"><b>${val == null ? "-" : val}${unit || ""}</b><span>${label}</span></div>`
      )
      .join("");
    const updated = has(d.updatedAt)
      ? `<div class="updated">반영 ${esc(d.updatedAt.replace("T", " ").slice(0, 16))}</div>`
      : "";
    $("#stats").innerHTML = stats + updated;
  }

  // ---------------- 1. Insight ----------------
  function renderInsight(d) {
    const ins = d.dailyInsight || {};
    if (!has(ins.headline) && !has(ins.body)) {
      $("#insight").innerHTML = emptyBox("아직 오늘의 인사이트가 없습니다.");
      return;
    }
    const col = (title, arr) =>
      Array.isArray(arr) && arr.length
        ? `<div><h4>${title}</h4>${pointsList(arr)}</div>`
        : "";
    $("#insight").innerHTML = `
      <h3>${esc(ins.headline || "오늘의 AI 인사이트")} ${fallbackBadge(ins)}</h3>
      <p>${esc(ins.body || "")}</p>
      <div class="cols">
        ${col("연결점", ins.connections)}
        ${col("다음에 확인할 것", ins.watchNext)}
      </div>`;
  }

  // ---------------- 2. News ----------------
  function articleCard(a) {
    const c = el("article", "card");
    c.innerHTML = `
      <div class="meta"><span class="src">${esc(a.sourceName)}</span>
        ${has(a.publishedAt) ? "· " + fmtDate(a.publishedAt) : ""} ${fallbackBadge(a)}</div>
      <h3><a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(pick(a.titleKo, a.title))}</a></h3>
      <p class="summary">${esc(pick(a.summaryKo, a.description))}</p>
      ${pointsList(a.insights)}
      ${has(a.soWhat) ? `<div class="sowhat"><b>So What</b> · ${esc(a.soWhat)}</div>` : ""}
      ${has(a.execLine) ? `<div class="exec"><b>임원 보고</b> · ${esc(a.execLine)}</div>` : ""}
    `;
    return c;
  }

  // ---------------- 3. Guru ----------------
  function guruCard(g) {
    const c = el("article", "card");
    c.innerHTML = `
      <div class="meta"><span class="src">${esc(g.name)}</span>
        ${has(g.org) ? "· " + esc(g.org) : ""} ${has(g.publishedAt) ? "· " + fmtDate(g.publishedAt) : ""} ${fallbackBadge(g)}</div>
      ${has(g.title) ? `<div class="kv"><span class="k">직함</span> <span class="v">${esc(g.title)}</span></div>` : ""}
      <h3><a href="${esc(g.url)}" target="_blank" rel="noopener">${esc(g.quoteTitle)}</a></h3>
      <p class="summary">${esc(pick(g.summaryKo, g.quoteText))}</p>
      ${has(g.meaning) ? `<div class="kv"><span class="k">핵심 의미</span> <span class="v">${esc(g.meaning)}</span></div>` : ""}
      ${has(g.businessImplication) ? `<div class="sowhat"><b>비즈니스 시사점</b> · ${esc(g.businessImplication)}</div>` : ""}
      ${has(g.caution) ? `<div class="exec"><b>주의할 점</b> · ${esc(g.caution)}</div>` : ""}
    `;
    return c;
  }

  // ---------------- 4. YouTube ----------------
  function youtubeCard(y) {
    const tier = (y.trust || y.baselineTier || "medium").toLowerCase();
    const basis = y.hasTranscript ? "자막 기반" : "설명 기반";
    const c = el("article", "card");
    c.innerHTML = `
      <div class="meta"><span class="src">${esc(y.channelName)}</span>
        ${has(y.publishedAt) ? "· " + fmtDate(y.publishedAt) : ""}
        <span class="chip neutral">${basis}</span>
        <span class="trust ${tier}">신뢰도 ${tier.toUpperCase()}</span> ${fallbackBadge(y)}</div>
      <h3><a href="${esc(y.url)}" target="_blank" rel="noopener">${esc(y.videoTitle)}</a></h3>
      <p class="summary">${esc(pick(y.summaryKo, y.description))}</p>
      ${pointsList(y.keyPoints)}
      ${has(y.implication) ? `<div class="sowhat"><b>실무 시사점</b> · ${esc(y.implication)}</div>` : ""}
      ${y.needsVerification ? `<div class="verify">⚠ 검증 필요: 과장 가능성 있음</div>` : ""}
    `;
    return c;
  }

  // ---------------- 5. Paper ----------------
  function paperCard(p) {
    const c = el("article", "card");
    c.innerHTML = `
      <div class="meta"><span class="src">${esc(p.sourceName)}</span>
        ${has(p.difficulty) ? `· <span class="chip neutral">난이도 ${esc(p.difficulty)}</span>` : ""} ${fallbackBadge(p)}</div>
      <h3><a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(pick(p.titleKo, p.title))}</a></h3>
      ${has(p.topic) ? `<div class="kv"><span class="k">주제</span> <span class="v">${esc(p.topic)}</span></div>` : ""}
      <p class="summary">${esc(pick(p.contribution, p.description))}</p>
      ${has(p.applicability) ? `<div class="kv"><span class="k">실무 적용</span> <span class="v">${esc(p.applicability)}</span></div>` : ""}
      ${has(p.marketingAngle) ? `<div class="sowhat"><b>마케팅 관점</b> · ${esc(p.marketingAngle)}</div>` : ""}
    `;
    return c;
  }

  // ---------------- 6. Report ----------------
  function renderReport(d) {
    const r = d.reportSummary || {};
    const trends = Array.isArray(r.topTrends) ? r.topTrends : [];
    if (!trends.length && !(r.actions || []).length) {
      $("#report").innerHTML = emptyBox("아직 보고용 서머리가 없습니다.");
      return;
    }
    const trendHtml = trends
      .map(
        (t, i) => `
      <div class="trend">
        <h4><span class="rank">${i + 1}</span>${esc(t.title)}</h4>
        ${has(t.quote) ? `<p class="quote">“${esc(t.quote)}”</p>` : ""}
        ${has(t.soWhat) ? `<div class="kv"><span class="k">So What</span> <span class="v">${esc(t.soWhat)}</span></div>` : ""}
        ${has(t.evidenceUrl) ? `<a class="evidence" href="${esc(t.evidenceUrl)}" target="_blank" rel="noopener">근거 링크 ↗</a>` : ""}
      </div>`
      )
      .join("");
    const listCol = (title, arr) =>
      Array.isArray(arr) && arr.length
        ? `<div><h4>${title}</h4>${pointsList(arr)}</div>`
        : "";
    $("#report").innerHTML = `
      <h3 style="margin:0 0 6px;font-size:16px;">Top ${trends.length} 트렌드 ${fallbackBadge(r)}</h3>
      ${trendHtml}
      <div class="lists">
        ${listCol("실행 제안", r.actions)}
        ${listCol("리스크 / 유의점", r.risks)}
      </div>`;
  }

  // ---------------- Grid filler ----------------
  function fillGrid(id, arr, cardFn, emptyMsg) {
    const host = $("#" + id);
    host.innerHTML = "";
    if (!Array.isArray(arr) || !arr.length) {
      host.innerHTML = emptyBox(emptyMsg);
      return;
    }
    const frag = document.createDocumentFragment();
    arr.forEach((item) => frag.appendChild(cardFn(item)));
    host.appendChild(frag);
  }

  function setCount(id, n) {
    $("#" + id).textContent = n ? `${n}건` : "";
  }

  function renderAll() {
    if (!DATA) return;
    renderStats(DATA);
    renderInsight(DATA);
    fillGrid("news", DATA.articles, articleCard, "수집된 뉴스가 없습니다.");
    fillGrid("guru", DATA.guruMentions, guruCard, "수집된 구루 발언이 없습니다.");
    fillGrid("youtube", DATA.youtubeBriefs, youtubeCard, "수집된 유튜브 브리프가 없습니다.");
    fillGrid("paper", DATA.papers, paperCard, "수집된 논문이 없습니다.");
    renderReport(DATA);
    setCount("news-count", (DATA.articles || []).length);
    setCount("guru-count", (DATA.guruMentions || []).length);
    setCount("youtube-count", (DATA.youtubeBriefs || []).length);
    setCount("paper-count", (DATA.papers || []).length);
  }

  function bindToggle() {
    document.querySelectorAll(".lang-toggle button").forEach((btn) => {
      btn.addEventListener("click", () => {
        LANG = btn.dataset.lang;
        document
          .querySelectorAll(".lang-toggle button")
          .forEach((b) => b.classList.toggle("active", b === btn));
        renderAll();
      });
    });
  }

  async function init() {
    bindToggle();
    try {
      const res = await fetch("data/latest.json", { cache: "no-store" });
      if (!res.ok) throw new Error("HTTP " + res.status);
      DATA = await res.json();
    } catch (e) {
      $("#insight").innerHTML = emptyBox(
        "data/latest.json 을 불러오지 못했습니다. (" + esc(e.message) + ")"
      );
      return;
    }
    renderAll();
  }

  // 개발/검증용: 외부에서 샘플 데이터를 주입할 수 있게 노출
  window.__renderData = (d) => {
    DATA = d;
    renderAll();
  };

  document.addEventListener("DOMContentLoaded", init);
})();
