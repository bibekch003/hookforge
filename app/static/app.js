/* Hookforge dashboard — plain JS, no build step, no CDN. */
const PLATFORMS = [
  ["youtube_shorts", "YouTube Shorts"],
  ["instagram_reel", "Reels"],
  ["tiktok", "TikTok"],
  ["linkedin_square", "LinkedIn 1:1"],
  ["youtube", "YouTube 16:9"],
];

const state = { file: null, selected: new Set(["youtube_shorts"]), report: null };

const $ = (id) => document.getElementById(id);

/* ---------- health ---------- */
fetch("/api/health").then(r => r.json()).then(h => {
  const el = $("health");
  el.classList.add("ok");
  el.textContent = `engine ok · ${h.platforms.length} presets · burn-in ${h.captions_burn_in ? "on" : "off"} · LLM ${h.llm_adapter ? "wired" : "offline"}`;
}).catch(() => { $("health").textContent = "engine unreachable"; });

/* ---------- platform chips ---------- */
const chips = $("platformChips");
PLATFORMS.forEach(([key, label]) => {
  const b = document.createElement("button");
  b.className = "chip" + (state.selected.has(key) ? " on" : "");
  b.textContent = label;
  b.onclick = () => {
    if (state.selected.has(key)) { state.selected.delete(key); b.classList.remove("on"); }
    else { state.selected.add(key); b.classList.add("on"); }
    if (state.selected.size === 0) { state.selected.add("youtube_shorts"); [...chips.children][0].classList.add("on"); }
  };
  chips.appendChild(b);
});

/* ---------- file picking ---------- */
const dz = $("dropzone"), input = $("fileInput");
$("pickBtn").onclick = () => input.click();
dz.onclick = (e) => { if (e.target === dz || e.target.classList.contains("dz-main")) input.click(); };
input.onchange = () => setFile(input.files[0]);
["dragenter", "dragover"].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add("hot"); }));
["dragleave", "drop"].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.remove("hot"); }));
dz.addEventListener("drop", e => { if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]); });

function setFile(f) {
  if (!f) return;
  state.file = f;
  $("fileLabel").textContent = `${f.name} · ${(f.size / 1048576).toFixed(1)} MB`;
}

$("nVariants").oninput = e => $("nVariantsOut").textContent = e.target.value;
$("clipSeconds").oninput = e => $("clipSecondsOut").textContent = e.target.value + "s";
$("useTranscript").onchange = e => $("transcript").hidden = !e.target.checked;

/* ---------- run ---------- */
$("runBtn").onclick = () => {
  if (!state.file) { showStatus("Pick a video first — or use the sample clip.", true); return; }
  const fd = new FormData();
  fd.append("file", state.file);
  fd.append("platforms", [...state.selected].join(","));
  fd.append("n_variants", $("nVariants").value);
  fd.append("clip_seconds", $("clipSeconds").value);
  fd.append("engine", $("engine").value);
  fd.append("burn_captions", "true");
  if ($("useTranscript").checked && $("transcript").value.trim()) fd.append("transcript", $("transcript").value);
  post("/api/analyze", fd);
};

$("demoBtn").onclick = () => {
  const q = new URLSearchParams({
    platforms: [...state.selected].join(","),
    n_variants: $("nVariants").value,
    clip_seconds: $("clipSeconds").value,
    engine: $("engine").value,
  });
  runWith(`/api/demo?${q}`, null);
};

function post(url, fd) { runWith(url, fd); }

function runWith(url, fd) {
  showStatus("Running: probe → audio → transcript → hook planner → thumbnails → captions → exports…");
  $("runBtn").disabled = $("demoBtn").disabled = true;
  const opts = fd ? { method: "POST", body: fd } : {};
  fetch(url, opts)
    .then(async r => {
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.detail || `HTTP ${r.status}`);
      return body;
    })
    .then(render)
    .catch(err => showStatus("Failed: " + err.message, true))
    .finally(() => { $("runBtn").disabled = $("demoBtn").disabled = false; });
}

function showStatus(msg, isErr) {
  const el = $("status");
  el.hidden = false;
  el.textContent = msg;
  el.classList.toggle("err", !!isErr);
}

/* ---------- render ---------- */
function render(report) {
  state.report = report;
  $("status").hidden = true;
  $("results").hidden = false;

  const m = report.meta;
  $("videoMeta").textContent =
    `${report.filename} · ${m.width}×${m.height} · ${m.fps} fps · ${m.duration}s · audio ${m.has_audio ? "yes" : "none"} · transcript: ${report.analysis.transcript_source}`;

  drawTimeline(report.analysis.energy_timeline, report.analysis.hook_windows, m.duration);

  const rec = report.recommendation;
  $("recommend").innerHTML = `
    <h3>Recommended variant</h3>
    <p class="hook">“${escapeHtml(rec.hook_text || "")}”</p>
    <p>${escapeHtml(rec.why || "")}</p>
    <p style="color:var(--muted);font-size:12.5px">${escapeHtml(rec.next_step || "")}</p>`;

  const grid = $("variants");
  grid.innerHTML = "";
  report.variants.forEach(v => grid.appendChild(card(v)));

  $("modelNote").textContent = report.disclaimer;
  drawAnalytics(report.variants);
}

function card(v) {
  const el = document.createElement("article");
  el.className = "card" + (v.rank === 1 ? " winner" : "");
  const ts = v.thumbnail_score || {};
  const p = v.prediction || {};
  const downloads = (v.exports || []).filter(e => e.download_url)
    .map(e => `<a href="${e.download_url}" download>${escapeHtml(e.label)} · ${e.size_mb}MB</a>`)
    .join("") || `<span class="why">no render produced</span>`;

  el.innerHTML = `
    <div class="thumb">
      <img src="${v.thumb_url}" alt="thumbnail variant ${v.rank}" loading="lazy" />
      <span class="badge">${escapeHtml(v.archetype)}</span>
      <span class="badge rank">#${v.rank}</span>
    </div>
    <div class="body">
      <div class="hook">“${escapeHtml(v.text)}”</div>
      <div class="why">${escapeHtml(v.rationale || "")}</div>
      <div class="scores">
        <div class="score"><span>thumb</span><b>${ts.score ?? "–"}/100</b>
          <div class="bar"><i style="width:${ts.score ?? 0}%"></i></div></div>
        <div class="score"><span>watch-through</span><b>${fmtPct(p.predicted_watch_through)}</b>
          <div class="bar"><i style="width:${(p.predicted_watch_through || 0) * 100}%"></i></div></div>
        <div class="score"><span>energy match</span><b>${fmtPct(v.energy_match)}</b></div>
        <div class="score"><span>copy strength</span><b>${fmtPct(v.copy_strength)}</b></div>
      </div>
      <div class="why">${escapeHtml((ts.reasons || []).join(" · ") || "balanced composition")}</div>
      <div class="why">in ${v.start}s · ${v.duration}s · ${v.caption_count} caption cues · ${escapeHtml(v.style)}</div>
      <div class="downloads">${downloads}</div>
    </div>`;
  return el;
}

function drawTimeline(tl, windows, duration) {
  const svg = $("timeline");
  const W = 800, H = 120, pad = 6;
  if (!tl || !tl.length) { svg.innerHTML = ""; return; }
  const maxT = Math.max(duration, tl[tl.length - 1].t + 1);
  const x = t => pad + (t / maxT) * (W - 2 * pad);
  const y = e => H - pad - e * (H - 2 * pad);

  let area = `M ${pad} ${H - pad} `;
  tl.forEach(b => area += `L ${x(b.t).toFixed(1)} ${y(b.energy).toFixed(1)} `);
  area += `L ${x(tl[tl.length - 1].t).toFixed(1)} ${H - pad} Z`;

  let line = tl.map((b, i) => `${i ? "L" : "M"} ${x(b.t).toFixed(1)} ${y(b.energy).toFixed(1)}`).join(" ");

  const marks = (windows || []).slice(0, 6).map(w =>
    `<polygon points="${x(w.start)},${pad + 8} ${x(w.start) - 5},${pad + 18} ${x(w.start) + 5},${pad + 18}" fill="#ffd23d" opacity="0.9"/>`
  ).join("");

  svg.innerHTML = `
    <defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#3ddc97" stop-opacity="0.45"/>
      <stop offset="100%" stop-color="#3ddc97" stop-opacity="0.02"/>
    </linearGradient></defs>
    <path d="${area}" fill="url(#g)"/>
    <path d="${line}" fill="none" stroke="#3ddc97" stroke-width="1.6"/>
    ${marks}`;
}

function drawAnalytics(variants) {
  const head = `<tr><th>#</th><th>variant</th><th>hook</th><th>thumb</th><th>watch-through</th><th>thumb CTR</th><th>engagement</th></tr>`;
  const rows = variants.map(v => `
    <tr class="${v.rank === 1 ? "top" : ""}">
      <td class="num">${v.rank}</td>
      <td>${escapeHtml(v.variant_id)}</td>
      <td>${escapeHtml(v.text)}</td>
      <td class="num">${v.thumbnail_score.score}</td>
      <td class="num">${fmtPct(v.prediction.predicted_watch_through)}</td>
      <td class="num">${fmtPct(v.prediction.predicted_thumb_ctr)}</td>
      <td class="num">${fmtPct(v.prediction.predicted_engagement_rate)}</td>
    </tr>`).join("");
  $("analytics").innerHTML = head + rows;
}

/* ---------- telemetry ---------- */
$("telemetryInput").onchange = async (e) => {
  const f = e.target.files[0];
  if (!f || !state.report) return;
  const fd = new FormData();
  fd.append("file", f);
  try {
    const r = await fetch(`/api/videos/${state.report.video_id}/telemetry`, { method: "POST", body: fd });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "upload failed");
    const rows = data.rows.map(x => `<tr><td class="num">${x.rank}</td><td>${escapeHtml(x.variant_id)}</td>
      <td class="num">${fmtPct(x.measured_watch_through)}</td>
      <td class="num">${fmtPct(x.predicted_watch_through)}</td>
      <td class="num">${(x.watch_through_lift * 100).toFixed(1)}%</td></tr>`).join("");
    $("telemetryOut").innerHTML = `<div class="table-wrap"><table>
      <tr><th>#</th><th>variant</th><th>measured WT</th><th>predicted WT</th><th>lift</th></tr>
      ${rows}</table></div>
      <p style="color:var(--accent);font-size:13px">Winner by measurement: ${escapeHtml(data.winner || "–")}</p>`;
  } catch (err) {
    $("telemetryOut").innerHTML = `<p class="why">${escapeHtml(err.message)}</p>`;
  }
};

/* ---------- helpers ---------- */
const fmtPct = (v) => (v == null ? "–" : (v * 100).toFixed(1) + "%");
function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
