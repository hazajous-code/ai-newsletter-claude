/* AI 데일리 브리핑 — 임원 보고서 1페이지 렌더러
 * 오늘의 흐름(인사이트) → 핵심 트렌드(보고용) → 근거 자료(접이식, 최소 카드).
 * KO/EN 토글, 카드별 "자세히" 확장, 그룹별 상위 N + 전체 보기.
 */
(function () {
  "use strict";

  let LANG = "ko";
  let DATA = null;
  const TOP_N = 6;

  const $ = (s) => document.querySelector(s);
  const esc = (s) =>
    String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])
    );
  const has = (s) => s != null && String(s).trim() !== "";
  const pick = (ko, en) =>
    LANG === "en" ? (has(en) ? en : ko || "") : has(ko) ? ko : en || "";
  const snip = (t, n) => {
    t = (t || "").trim();
    return t.length > n ? t.slice(0, n).replace(/\s+\S*$/, "") + "…" : t;
  };
  const fmtDate = (iso) => {
    if (!has(iso)) return "";
    const d = new Date(iso);
    return isNaN(d) ? "" : d.toLocaleDateString("ko-KR", { month: "short", day: "numeric" });
  };
  const normUrl = (u) => (u || "").trim().replace(/[#?].*$/, "").replace(/\/$/, "").toLowerCase();
  const fb = (x) => (x && x.llm === false ? '<span class="fallback-note">원문 기반</span>' : "");
  const li = (arr) =>
    Array.isArray(arr) && arr.length
      ? `<ul>${arr.map((p) => `<li>${esc(p)}</li>`).join("")}</ul>`
      : "";

  // url → 한 줄 요약 (트렌드 So What 비었을 때 대체용)
  function buildSummaryMap(d) {
    const m = {};
    (d.articles || []).forEach((a) => { if (a.url) m[normUrl(a.url)] = a.summaryKo || a.description; });
    (d.papers || []).forEach((p) => { if (p.url) m[normUrl(p.url)] = p.contribution || p.description; });
    (d.guruMentions || []).forEach((g) => { if (g.url) m[normUrl(g.url)] = g.summaryKo || g.quoteText; });
    (d.youtubeBriefs || []).forEach((y) => { if (y.url) m[normUrl(y.url)] = y.summaryKo || y.description; });
    return m;
  }

  // ---------------- 1. Hero ----------------
  function renderInsight(d) {
    const ins = d.dailyInsight || {};
    if (!has(ins.headline) && !has(ins.body)) {
      $("#insight").innerHTML =
        `<div class="empty">아직 오늘의 인사이트가 없습니다. <code>python scrape_daily.py</code> 실행 후 새로고침하세요.</div>`;
      return;
    }
    const col = (title, arr) =>
      Array.isArray(arr) && arr.length ? `<div><h4>${title}</h4>${li(arr)}</div>` : "";
    const sub =
      (Array.isArray(ins.connections) && ins.connections.length) ||
      (Array.isArray(ins.watchNext) && ins.watchNext.length)
        ? `<div class="sub">${col("소스 간 연결점", ins.connections)}${col("다음에 확인할 것", ins.watchNext)}</div>`
        : "";
    $("#insight").innerHTML = `
      <div class="eyebrow">오늘의 흐름 ${fb(ins)}</div>
      <h2>${esc(ins.headline || "오늘의 AI 인사이트")}</h2>
      <p class="body">${esc(ins.body || "")}</p>
      ${sub}`;
  }

  // ---------------- 2. Trends ----------------
  function renderTrends(d) {
    const r = d.reportSummary || {};
    const trends = Array.isArray(r.topTrends) ? r.topTrends : [];
    const host = $("#trends");
    if (!trends.length && !(r.actions || []).length) {
      host.innerHTML =
        `<div class="section-head"><h2>오늘의 핵심 트렌드</h2></div>
         <div class="empty">아직 정리된 트렌드가 없습니다.</div>`;
      return;
    }
    const smap = buildSummaryMap(d);
    const items = trends
      .map((t, i) => {
        const line = has(t.soWhat)
          ? `<p class="sowhat"><b>So What</b> · ${esc(t.soWhat)}</p>`
          : (() => {
              const alt = smap[normUrl(t.evidenceUrl)];
              return has(alt) ? `<p class="sowhat">${esc(snip(alt, 150))}</p>` : "";
            })();
        return `
          <article class="trend">
            <div class="num">${i + 1}</div>
            <div class="tbody">
              <h3>${esc(t.title)}</h3>
              ${has(t.quote) ? `<p class="quote">“${esc(t.quote)}”</p>` : ""}
              ${line}
              ${has(t.evidenceUrl) ? `<a class="ev" href="${esc(t.evidenceUrl)}" target="_blank" rel="noopener">근거 보기 ↗</a>` : ""}
            </div>
          </article>`;
      })
      .join("");
    const colA =
      Array.isArray(r.actions) && r.actions.length
        ? `<div class="report-col act"><h4>✓ 실행 제안</h4>${li(r.actions)}</div>` : "";
    const colR =
      Array.isArray(r.risks) && r.risks.length
        ? `<div class="report-col risk"><h4>⚠ 리스크 / 유의점</h4>${li(r.risks)}</div>` : "";
    const cols = colA || colR ? `<div class="report-cols">${colA}${colR}</div>` : "";
    host.innerHTML = `
      <div class="section-head"><h2>오늘의 핵심 트렌드</h2><span class="hint">보고서에 그대로 활용 ${fb(r)}</span></div>
      <div class="trend-list">${items}</div>
      ${cols}`;
  }

  // ---------------- 3. Evidence cards ----------------
  function detailBlock(rows) {
    const body = rows.filter(Boolean).join("");
    return body ? `<button class="more-btn" type="button">자세히 ▾</button><div class="detail">${body}</div>` : "";
  }
  const kv = (k, v) => (has(v) ? `<div class="kv"><span class="k">${k}</span> ${esc(v)}</div>` : "");

  function articleCard(a) {
    const one = has(a.soWhat) ? a.soWhat : snip(pick(a.summaryKo, a.description), 110);
    return `
      <div class="mc">
        <div class="mmeta"><span class="src">${esc(a.sourceName)}</span>
          ${has(a.publishedAt) ? "· " + fmtDate(a.publishedAt) : ""} ${fb(a)}</div>
        <h4><a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(pick(a.titleKo, a.title))}</a></h4>
        ${has(one) ? `<p class="one">${esc(one)}</p>` : ""}
        ${detailBlock([
          li(a.insights),
          kv("So What", a.soWhat),
          kv("임원 보고", a.execLine),
        ])}
      </div>`;
  }

  function guruCard(g) {
    const one = has(g.businessImplication) ? g.businessImplication : snip(pick(g.summaryKo, g.quoteText), 110);
    return `
      <div class="mc">
        <div class="mmeta"><span class="src">${esc(g.name)}</span>
          ${has(g.org) ? "· " + esc(g.org) : ""} ${has(g.publishedAt) ? "· " + fmtDate(g.publishedAt) : ""} ${fb(g)}</div>
        <h4><a href="${esc(g.url)}" target="_blank" rel="noopener">${esc(g.quoteTitle)}</a></h4>
        ${has(one) ? `<p class="one">${esc(one)}</p>` : ""}
        ${detailBlock([
          kv("발언 요약", pick(g.summaryKo, g.quoteText)),
          kv("핵심 의미", g.meaning),
          kv("비즈니스 시사점", g.businessImplication),
          kv("주의할 점", g.caution),
        ])}
      </div>`;
  }

  function youtubeCard(y) {
    const tier = (y.trust || y.baselineTier || "medium").toLowerCase();
    const one = has(y.implication) ? y.implication : snip(pick(y.summaryKo, y.description), 110);
    return `
      <div class="mc">
        <div class="mmeta"><span class="src">${esc(y.channelName)}</span>
          ${has(y.publishedAt) ? "· " + fmtDate(y.publishedAt) : ""}
          <span class="trust ${tier}">${tier.toUpperCase()}</span>
          ${y.needsVerification ? '<span class="verify">⚠ 검증</span>' : ""} ${fb(y)}</div>
        <h4><a href="${esc(y.url)}" target="_blank" rel="noopener">${esc(y.videoTitle)}</a></h4>
        ${has(one) ? `<p class="one">${esc(one)}</p>` : ""}
        ${detailBlock([
          kv("요약", pick(y.summaryKo, y.description)),
          li(y.keyPoints),
          kv("실무 시사점", y.implication),
        ])}
      </div>`;
  }

  function paperCard(p) {
    const one = has(p.marketingAngle) ? p.marketingAngle : snip(pick(p.contribution, p.description), 110);
    return `
      <div class="mc">
        <div class="mmeta"><span class="src">${esc(p.sourceName)}</span>
          ${has(p.difficulty) ? `· <span class="chip">난이도 ${esc(p.difficulty)}</span>` : ""} ${fb(p)}</div>
        <h4><a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(pick(p.titleKo, p.title))}</a></h4>
        ${has(one) ? `<p class="one">${esc(one)}</p>` : ""}
        ${detailBlock([
          kv("연구 주제", p.topic),
          kv("핵심 기여", pick(p.contribution, p.description)),
          kv("실무 적용", p.applicability),
          kv("마케팅 관점", p.marketingAngle),
        ])}
      </div>`;
  }

  const GROUPS = [
    { icon: "📰", label: "핵심 뉴스", key: "articles", card: articleCard, open: true },
    { icon: "🧠", label: "AI 구루 언급", key: "guruMentions", card: guruCard },
    { icon: "▶", label: "테크 유튜버", key: "youtubeBriefs", card: youtubeCard },
    { icon: "📄", label: "논문 / 리서치", key: "papers", card: paperCard },
  ];

  function renderEvidence(d) {
    const host = $("#evidence-groups");
    host.innerHTML = "";
    let total = 0;
    GROUPS.forEach((g) => {
      const items = d[g.key] || [];
      total += items.length;
      if (!items.length) return;
      const det = document.createElement("details");
      det.className = "group";
      if (g.open) det.open = true;
      const top = items.slice(0, TOP_N).map(g.card).join("");
      const restCount = items.length - TOP_N;
      det.innerHTML = `
        <summary><span class="chev">▶</span><span class="gicon">${g.icon}</span>
          ${g.label} <span class="gcount">${items.length}건</span></summary>
        <div class="group-body">
          ${top}
          ${restCount > 0 ? `<button class="show-all" type="button">나머지 ${restCount}건 모두 보기</button>` : ""}
        </div>`;
      // 전체 보기
      if (restCount > 0) {
        det.querySelector(".show-all").addEventListener("click", function () {
          this.insertAdjacentHTML("beforebegin", items.slice(TOP_N).map(g.card).join(""));
          this.remove();
          bindMore(det);
        });
      }
      bindMore(det);
      host.appendChild(det);
    });
    $("#evidence-stat").textContent =
      `뉴스 ${(d.articles || []).length} · 구루 ${(d.guruMentions || []).length} · 유튜브 ${(d.youtubeBriefs || []).length} · 논문 ${(d.papers || []).length} · 출처 ${(d.stats && d.stats.sourceCount) || 0}개`;
    if (!total) host.innerHTML = `<div class="empty">아직 수집된 자료가 없습니다.</div>`;
  }

  // "자세히" 토글 바인딩 (이벤트 위임이 아닌 직접 — 동적 추가분 대응)
  function bindMore(scope) {
    scope.querySelectorAll(".mc .more-btn").forEach((btn) => {
      if (btn.dataset.bound) return;
      btn.dataset.bound = "1";
      btn.addEventListener("click", () => {
        const mc = btn.closest(".mc");
        const open = mc.classList.toggle("open");
        btn.textContent = open ? "접기 ▴" : "자세히 ▾";
      });
    });
  }

  function renderAll() {
    if (!DATA) return;
    $("#updated").textContent = has(DATA.updatedAt)
      ? "반영 " + DATA.updatedAt.replace("T", " ").slice(0, 16)
      : "";
    renderInsight(DATA);
    renderTrends(DATA);
    renderEvidence(DATA);
  }

  function bindToggle() {
    document.querySelectorAll(".lang-toggle button").forEach((btn) => {
      btn.addEventListener("click", () => {
        LANG = btn.dataset.lang;
        document.querySelectorAll(".lang-toggle button").forEach((b) => b.classList.toggle("active", b === btn));
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
      $("#insight").innerHTML = `<div class="empty">data/latest.json 을 불러오지 못했습니다. (${esc(e.message)})</div>`;
      return;
    }
    renderAll();
  }

  window.__renderData = (d) => { DATA = d; renderAll(); };
  document.addEventListener("DOMContentLoaded", init);
})();
