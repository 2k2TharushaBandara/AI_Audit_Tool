from __future__ import annotations

import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from flask import Flask, jsonify, request

from .ai import AiAnalysisError, run_ai_analysis
from .metrics import extract_metrics
from .prompt_logging import write_prompt_log
from .scrape import fetch_html


HTML_PAGE = """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>PageLift AI Audit</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;700;800&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

    :root {
      --bg: #f5f7fb;
      --panel: #ffffff;
      --text: #1c2735;
      --muted: #64748b;
      --brand: #0e7490;
      --brand-2: #0f766e;
      --ok: #166534;
      --err: #b91c1c;
      --border: #dbe2ea;
      --info: #1d4ed8;
      --chip-bg: #eef6ff;
      --ink-soft: #334155;
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      background:
        radial-gradient(circle at 5% 0%, #dbeafe 0%, transparent 40%),
        radial-gradient(circle at 95% 10%, #ccfbf1 0%, transparent 38%),
        linear-gradient(180deg, #f8fbff 0%, #f1f5f9 100%);
      color: var(--text);
      font: 15px/1.6 "IBM Plex Sans", "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
    }
    .wrap { max-width: 1160px; margin: 0 auto; padding: 26px; }
    .hero {
      margin-bottom: 18px;
      padding: 24px;
      border: 1px solid #d7e7f7;
      border-radius: 18px;
      background: linear-gradient(120deg, #ffffff 0%, #edf7ff 56%, #ecfeff 100%);
      box-shadow: 0 18px 44px rgba(15, 23, 42, 0.08);
    }
    .hero h1 {
      margin: 0;
      font-family: "Manrope", "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
      font-size: clamp(28px, 5vw, 44px);
      line-height: 1.1;
      letter-spacing: -0.03em;
      font-weight: 800;
      color: #0f172a;
    }
    .hero p {
      margin: 10px 0 0;
      color: #35506f;
      font-size: 16px;
      max-width: 700px;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 16px;
      box-shadow: 0 12px 34px rgba(15, 23, 42, 0.07);
      padding: 18px;
      margin-bottom: 18px;
    }
    .grid { display: grid; gap: 12px; grid-template-columns: 1fr auto auto; }
    input[type=url], select {
      width: 100%;
      padding: 11px 13px;
      border: 1px solid var(--border);
      border-radius: 10px;
      font: inherit;
      background: #fff;
    }
    .btn {
      border: 0;
      border-radius: 10px;
      background: linear-gradient(130deg, var(--brand) 0%, var(--brand-2) 100%);
      color: #fff;
      padding: 11px 15px;
      font-family: "Manrope", "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
      font-weight: 700;
      cursor: pointer;
      transition: transform 120ms ease, box-shadow 120ms ease;
    }
    .btn:hover { transform: translateY(-1px); box-shadow: 0 6px 18px rgba(14, 116, 144, 0.22); }
    .btn:disabled { opacity: 0.6; cursor: not-allowed; }
    .btn.ghost {
      background: #fff;
      color: var(--text);
      border: 1px solid var(--border);
    }
    .status-card {
      margin-top: 12px;
      border: 1px solid var(--border);
      border-left: 6px solid var(--info);
      border-radius: 10px;
      background: #eff6ff;
      padding: 12px;
      display: none;
    }
    .status-card h3 {
      margin: 0 0 4px;
      font-size: 15px;
      font-family: "Manrope", "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
      font-weight: 800;
    }
    .status-card p { margin: 0; color: var(--text); }
    .status-card .meta { margin-top: 8px; font-size: 12px; color: var(--muted); }
    .status-card.running {
      display: block;
      border-left-color: var(--warn);
      background: #fff7ed;
    }
    .status-card.success {
      display: block;
      border-left-color: var(--ok);
      background: #ecfdf5;
    }
    .status-card.error {
      display: block;
      border-left-color: var(--err);
      background: #fef2f2;
    }
    .status-actions {
      margin-top: 10px;
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
    h2 {
      margin: 0 0 12px;
      font-family: "Manrope", "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
      font-size: 23px;
      line-height: 1.2;
      font-weight: 800;
      letter-spacing: -0.01em;
      color: #0f172a;
    }
    h3 {
      margin: 16px 0 8px;
      font-family: "Manrope", "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
      font-size: 16px;
      line-height: 1.2;
      font-weight: 700;
      color: #0f172a;
    }
    .metrics-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
    .metric {
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 12px;
      background: linear-gradient(160deg, #ffffff 0%, #f9fbff 100%);
    }
    .metric .k { color: var(--muted); font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.03em; }
    .metric .v {
      margin-top: 5px;
      font-family: "Manrope", "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
      font-weight: 800;
      font-size: 24px;
      color: #0f172a;
    }
    .meta-box {
      margin-top: 10px;
      border: 1px solid #d9e5f3;
      border-radius: 10px;
      background: #f8fbff;
      padding: 10px 12px;
    }
    .meta-box .label {
      color: #4b6380;
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.03em;
      margin-bottom: 4px;
    }
    .meta-box .value {
      color: #0f172a;
      font-size: 14px;
      font-weight: 600;
      word-break: break-word;
    }

    .ai-wrap {
      display: grid;
      gap: 12px;
    }
    .ai-summary {
      border: 1px solid #dbe7f5;
      border-radius: 12px;
      background: linear-gradient(125deg, #eff6ff 0%, #f0fdfa 100%);
      padding: 12px 14px;
    }
    .ai-summary .title {
      margin: 0 0 6px;
      font-family: "Manrope", "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
      font-size: 14px;
      font-weight: 800;
      color: #155e75;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    .ai-summary .text {
      margin: 0;
      color: #0f172a;
      font-size: 15px;
      font-weight: 600;
      line-height: 1.55;
    }
    .ai-buckets {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }
    .bucket-card {
      border: 1px solid #dbe3ef;
      border-radius: 12px;
      padding: 12px;
      background: #fff;
    }
    .bucket-head {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 8px;
    }
    .bucket-title {
      margin: 0;
      font-family: "Manrope", "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
      font-size: 16px;
      font-weight: 800;
      color: #0f172a;
    }
    .bucket-badge {
      font-size: 11px;
      font-weight: 700;
      color: #1e3a8a;
      border: 1px solid #bfdbfe;
      background: var(--chip-bg);
      border-radius: 999px;
      padding: 3px 8px;
    }
    .insight-item {
      border-top: 1px dashed #d8e3f0;
      padding-top: 8px;
      margin-top: 8px;
    }
    .insight-item:first-of-type {
      border-top: 0;
      margin-top: 0;
      padding-top: 0;
    }
    .insight-title {
      margin: 0 0 5px;
      font-size: 14px;
      font-weight: 700;
      color: #0f172a;
    }
    .evidence-row {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      margin: 0 0 6px;
    }
    .evidence-pill {
      display: inline-block;
      font-size: 12px;
      color: #475569;
      border: 1px solid #d5dfec;
      border-radius: 999px;
      background: #f8fafc;
      padding: 3px 8px;
      word-break: break-word;
    }
    .insight-why {
      margin: 0;
      color: var(--ink-soft);
      font-size: 13px;
      line-height: 1.55;
    }
    .recs-title {
      margin: 6px 0 2px;
      font-family: "Manrope", "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
      font-size: 17px;
      font-weight: 800;
      color: #0f172a;
    }
    .rec-grid {
      display: grid;
      gap: 10px;
    }
    .rec-card {
      border: 1px solid #dce5f1;
      border-radius: 12px;
      background: #fcfdff;
      padding: 12px;
    }
    .rec-head {
      display: flex;
      gap: 10px;
      align-items: center;
      margin-bottom: 6px;
    }
    .priority {
      min-width: 42px;
      text-align: center;
      padding: 5px 8px;
      border-radius: 9px;
      font-family: "Manrope", "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
      font-size: 12px;
      font-weight: 800;
      color: #fff;
      background: linear-gradient(135deg, #0f766e 0%, #0e7490 100%);
    }
    .rec-title {
      margin: 0;
      font-family: "Manrope", "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
      font-size: 16px;
      font-weight: 800;
      color: #0f172a;
    }
    .rec-reason {
      margin: 0 0 8px;
      color: var(--ink-soft);
      font-size: 14px;
      line-height: 1.55;
      font-weight: 600;
    }
    .actions-label, .refs-label {
      margin: 0 0 4px;
      font-size: 12px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.03em;
      color: #475569;
    }
    .actions-list {
      margin: 0 0 8px;
      padding-left: 18px;
      color: #0f172a;
      font-size: 14px;
      font-weight: 500;
    }
    .refs-row {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }
    .empty-state {
      border: 1px dashed #c5d5e9;
      border-radius: 12px;
      padding: 14px;
      background: #f8fbff;
      color: #39557a;
      font-weight: 600;
    }
    .small { color: var(--muted); font-size: 12px; }
    ul { margin: 8px 0 0 18px; padding: 0; }
    .ok { color: var(--ok); }
    .warn { color: var(--warn); }
    .err { color: var(--err); }
    @media (max-width: 760px) {
      .grid { grid-template-columns: 1fr; }
      .ai-buckets { grid-template-columns: 1fr; }
      .metrics-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"hero\">
      <h1>PageLift AI Audit</h1>
      <p>Audit your website Today & Receive grounded AI insights, and prioritized recommendations.</p>
    </div>

    <div class=\"panel\">
      <div class=\"grid\">
        <input id=\"url\" type=\"url\" placeholder=\"https://example.com\" value=\"https://example.com\" />
        <select id=\"aiMode\">
          <option value=\"with-ai\">Run with AI</option>
          <option value=\"no-ai\">Metrics only</option>
        </select>
        <button id=\"runBtn\" class=\"btn\">Analyze URL</button>
      </div>
      <div id=\"statusCard\" class=\"status-card\" role=\"status\" aria-live=\"polite\">
        <h3 id=\"statusTitle\">Ready</h3>
        <p id=\"statusText\">Start an audit to see results.</p>
        <div id=\"statusMeta\" class=\"meta\"></div>
        <div class=\"status-actions\">
          <a id=\"jsonViewerLink\" class=\"btn ghost\" href=\"/json-viewer\" target=\"_blank\" rel=\"noopener\" style=\"display:none\">Open JSON Viewer</a>
        </div>
      </div>
    </div>

    <div class=\"panel\">
      <h2>Factual Metrics</h2>
      <div id=\"facts\" class=\"small\">Run an audit to see metrics.</div>
    </div>

    <div class=\"panel\">
      <h2>AI Insights & Recommendations</h2>
      <div id=\"ai\" class=\"small\">Run with AI to see structured analysis.</div>
    </div>

  </div>

  <script>
    const runBtn = document.getElementById('runBtn');
    const urlEl = document.getElementById('url');
    const aiMode = document.getElementById('aiMode');
    const statusCard = document.getElementById('statusCard');
    const statusTitle = document.getElementById('statusTitle');
    const statusText = document.getElementById('statusText');
    const statusMeta = document.getElementById('statusMeta');
    const jsonViewerLink = document.getElementById('jsonViewerLink');
    const factsEl = document.getElementById('facts');
    const aiEl = document.getElementById('ai');

    function setStatus(state, title, text, meta = '') {
      statusCard.className = `status-card ${state}`;
      statusTitle.textContent = title;
      statusText.textContent = text;
      statusMeta.textContent = meta;
    }

    function esc(s) {
      return String(s ?? '').replace(/[&<>\"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]));
    }

    function renderFacts(out) {
      const m = out.metrics;
      factsEl.innerHTML = `
        <div class=\"metrics-grid\">
          <div class=\"metric\"><div class=\"k\">Total Word Count</div><div class=\"v\">${m.word_count}</div></div>
          <div class=\"metric\"><div class=\"k\">Headings (H1/H2/H3)</div><div class=\"v\">${m.headings.h1}/${m.headings.h2}/${m.headings.h3}</div></div>
          <div class=\"metric\"><div class=\"k\">CTAs (buttons + primary links)</div><div class=\"v\">${m.cta_count}</div></div>
          <div class=\"metric\"><div class=\"k\">Links (internal/external)</div><div class=\"v\">${m.links.internal}/${m.links.external}</div></div>
          <div class=\"metric\"><div class=\"k\">Images</div><div class=\"v\">${m.images.total_images}</div></div>
          <div class=\"metric\"><div class=\"k\">Missing Alt %</div><div class=\"v\">${m.images.missing_alt_pct}%</div></div>
        </div>
        <div class=\"meta-box\"><div class=\"label\">Meta Title</div><div class=\"value\">${esc(m.meta_title || '(none)')}</div></div>
        <div class=\"meta-box\"><div class=\"label\">Meta Description</div><div class=\"value\">${esc(m.meta_description || '(none)')}</div></div>
      `;
    }

    function bucketLabel(bucket) {
      const labels = {
        seo_structure: 'SEO Structure',
        messaging_clarity: 'Messaging Clarity',
        cta_usage: 'CTA Usage',
        content_depth: 'Content Depth',
        ux_structural_concerns: 'UX / Structural Concerns',
      };
      return labels[bucket] || bucket;
    }

    function renderAi(out) {
      if (!out.ai) {
        if (out.ai_error) {
          aiEl.innerHTML = `<div class=\"empty-state err\">AI error: ${esc(out.ai_error)}</div>`;
        } else {
          aiEl.innerHTML = '<div class=\"empty-state\">AI was not requested for this run. Switch mode to <strong>Run with AI</strong> to generate insights and recommendations.</div>';
        }
        return;
      }

      const report = out.ai;
      const buckets = ['seo_structure','messaging_clarity','cta_usage','content_depth','ux_structural_concerns'];
      const insightsHtml = buckets.map((b) => {
        const items = report.insights[b] || [];
        const itemHtml = items.map((it) => {
          const evidence = (it.evidence || []).map((e) => `<span class=\"evidence-pill\">${esc(e)}</span>`).join('');
          return `
            <article class=\"insight-item\">
              <p class=\"insight-title\">${esc(it.title || 'Insight')}</p>
              <div class=\"evidence-row\">${evidence || '<span class=\"evidence-pill\">No evidence provided</span>'}</div>
              <p class=\"insight-why\">${esc(it.why_it_matters || '')}</p>
            </article>
          `;
        }).join('');

        return `
          <section class=\"bucket-card\">
            <div class=\"bucket-head\">
              <h3 class=\"bucket-title\">${esc(bucketLabel(b))}</h3>
              <span class=\"bucket-badge\">${items.length} item${items.length === 1 ? '' : 's'}</span>
            </div>
            ${itemHtml || '<div class=\"small\">No insights returned in this bucket.</div>'}
          </section>
        `;
      }).join('');

      const recs = (report.recommendations || []).slice().sort((a,b) => a.priority - b.priority).map((r) => {
        const actions = (r.actions || []).map((a) => `<li>${esc(a)}</li>`).join('');
        const refs = (r.metric_references || []).map((m) => `<span class=\"evidence-pill\">${esc(m)}</span>`).join('');
        return `
          <article class=\"rec-card\">
            <div class=\"rec-head\">
              <span class=\"priority\">P${esc(r.priority)}</span>
              <h4 class=\"rec-title\">${esc(r.title || 'Recommendation')}</h4>
            </div>
            <p class=\"rec-reason\">${esc(r.reasoning || '')}</p>
            <p class=\"actions-label\">Actions</p>
            <ul class=\"actions-list\">${actions || '<li>No actions provided</li>'}</ul>
            <p class=\"refs-label\">Metric References</p>
            <div class=\"refs-row\">${refs || '<span class=\"evidence-pill\">No metric references provided</span>'}</div>
          </article>
        `;
      }).join('');

      aiEl.innerHTML = `
        <section class=\"ai-wrap\">
          <div class=\"ai-summary\">
            <p class=\"title\">AI Summary</p>
            <p class=\"text\">${esc(report.summary || '')}</p>
          </div>
          <div class=\"ai-buckets\">${insightsHtml}</div>
          <h3 class=\"recs-title\">Prioritized Recommendations</h3>
          <div class=\"rec-grid\">${recs || '<div class=\"small\">No recommendations returned.</div>'}</div>
        </section>
      `;
    }

    async function runAudit() {
      const url = urlEl.value.trim();
      if (!url) return;
      runBtn.disabled = true;
      jsonViewerLink.style.display = 'none';
      factsEl.innerHTML = '<div class="empty-state">Running a new audit. Previous results were cleared to avoid confusion.</div>';
      aiEl.innerHTML = '<div class="empty-state">Analyzing page content and preparing AI insights...</div>';
      setStatus('running', 'Audit in progress', 'Fetching page and calculating metrics...', 'This may take a few seconds.');

      try {
        const resp = await fetch('/api/audit', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ url, no_ai: aiMode.value === 'no-ai' })
        });
        const out = await resp.json();
        if (!resp.ok) throw new Error(out.error || 'Request failed');

        renderFacts(out);
        renderAi(out);
        localStorage.setItem('eight25-last-audit-json', JSON.stringify(out, null, 2));
        jsonViewerLink.style.display = 'inline-block';
        setStatus(
          'success',
          'Audit completed',
          `Analysis finished for ${out.final_url}.`,
          `HTTP ${out.status_code} | Prompt log: ${out.prompt_log ? out.prompt_log.id : 'none'}`,
        );
      } catch (e) {
        factsEl.innerHTML = '<div class="empty-state err">No metrics are shown because this audit run failed.</div>';
        aiEl.innerHTML = '<div class="empty-state err">No AI output is shown because this audit run failed.</div>';
        setStatus('error', 'Audit failed', String(e.message || e), 'Please verify the URL and retry.');
      } finally {
        runBtn.disabled = false;
      }
    }

    runBtn.addEventListener('click', runAudit);
    urlEl.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        runAudit();
      }
    });
  </script>
</body>
</html>
"""


JSON_VIEWER_PAGE = """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>PageLift Audit JSON Viewer</title>
  <style>
    :root {
      --bg: #0b1220;
      --panel: #111827;
      --text: #e5e7eb;
      --muted: #9ca3af;
      --accent: #0ea5e9;
      --border: #1f2937;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--text);
      background: radial-gradient(circle at 15% 0%, #1f2937 0%, #0b1220 42%, #030712 100%);
      font: 14px/1.5 Consolas, "Courier New", monospace;
    }
    .wrap { max-width: 1100px; margin: 0 auto; padding: 20px; }
    .panel {
      border: 1px solid var(--border);
      border-radius: 12px;
      background: rgba(17, 24, 39, 0.94);
      padding: 14px;
    }
    .head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 10px;
    }
    h1 { margin: 0; font-size: 18px; }
    .small { color: var(--muted); font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif; }
    .btn {
      display: inline-block;
      color: #fff;
      text-decoration: none;
      background: var(--accent);
      padding: 8px 10px;
      border-radius: 8px;
      font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
      font-size: 13px;
      font-weight: 600;
    }
    pre {
      margin: 0;
      border: 1px solid var(--border);
      border-radius: 10px;
      background: #030712;
      color: #d1d5db;
      padding: 12px;
      min-height: 300px;
      overflow: auto;
      white-space: pre-wrap;
      word-break: break-word;
    }
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"panel\">
      <div class=\"head\">
        <h1>PageLift JSON Viewer</h1>
        <a class=\"btn\" href=\"/\">Back to Analyzer</a>
      </div>
      <div class=\"small\">Displays the latest structured audit result captured from the analyzer screen.</div>
      <pre id=\"json\">No audit data available yet. Run an audit first.</pre>
    </div>
  </div>
  <script>
    const raw = localStorage.getItem('eight25-last-audit-json');
    if (raw) {
      document.getElementById('json').textContent = raw;
    }
  </script>
</body>
</html>
"""


def create_app() -> Flask:
    load_dotenv()

    app = Flask(__name__)

    @app.get("/")
    def index() -> str:
        return HTML_PAGE

    @app.get("/json-viewer")
    def json_viewer() -> str:
      return JSON_VIEWER_PAGE

    @app.post("/api/audit")
    def api_audit():
        body = request.get_json(silent=True) or {}
        url = str(body.get("url") or "").strip()
        if not url:
            return jsonify({"error": "url is required"}), 400

        no_ai = bool(body.get("no_ai", False))
        model = str(body.get("model") or os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
        log_dir = str(body.get("log_dir") or "logs/prompt-logs")
        insecure = bool(body.get("insecure", False))

        if not bool(body.get("no_truststore", False)):
            use_truststore = os.getenv("EIGHT25_USE_TRUSTSTORE", "1") not in {"0", "false", "False"}
            if use_truststore:
                try:
                    import truststore  # type: ignore

                    truststore.inject_into_ssl()
                except Exception:
                    pass

        try:
            fetch = fetch_html(url, verify_tls=not insecure)
            if fetch.blocked_reason:
                return (
                    jsonify(
                        {
                            "error": fetch.blocked_reason,
                            "requested_url": fetch.requested_url,
                            "final_url": fetch.final_url,
                            "status_code": fetch.status_code,
                            "fetch_error": fetch.blocked_reason,
                        }
                    ),
                    502,
                )

            metrics = extract_metrics(fetch.html, page_url=fetch.final_url)

            ai_report = None
            prompt_log = None
            ai_error = None

            if not no_ai:
                if not os.getenv("OPENAI_API_KEY"):
                    return jsonify({"error": "OPENAI_API_KEY is not set"}), 400

                try:
                    ai_report, system_prompt, user_prompt, structured_input, raw_model_output = run_ai_analysis(
                        url=fetch.final_url,
                        metrics=metrics,
                        model=model,
                    )
                    prompt_log = write_prompt_log(
                        log_dir=log_dir,
                        model=model,
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        structured_input=structured_input,
                        raw_model_output=raw_model_output,
                        parsed_output=ai_report.model_dump(),
                        error=None,
                    )
                except AiAnalysisError as e:
                    ai_error = str(e)
                    prompt_log = write_prompt_log(
                        log_dir=log_dir,
                        model=model,
                        system_prompt=e.system_prompt,
                        user_prompt=e.user_prompt,
                        structured_input=e.structured_input,
                        raw_model_output=e.raw_model_output,
                        parsed_output=None,
                        error=str(e),
                    )

            output = {
                "requested_url": fetch.requested_url,
                "final_url": fetch.final_url,
                "status_code": fetch.status_code,
                "fetched_at": fetch.fetched_at.isoformat(),
                "metrics": metrics.model_dump(mode="json"),
                "ai": ai_report.model_dump(mode="json") if ai_report else None,
                "ai_error": ai_error,
                "prompt_log": prompt_log.model_dump(mode="json") if prompt_log else None,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            return jsonify(output)
        except Exception as e:  # noqa: BLE001
            return jsonify({"error": str(e)}), 500

    return app


app = create_app()


def main() -> None:
    host = os.getenv("EIGHT25_WEB_HOST", "127.0.0.1")
    port = int(os.getenv("EIGHT25_WEB_PORT", "8000"))
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
