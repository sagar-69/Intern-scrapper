import React, { useCallback, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { ArrowUpRight, Pause, Play, Plus, RefreshCw, Trash2, X } from "lucide-react";
import "./style.css";

const API = "http://localhost:8000/api";

async function request(path, options) {
  const response = await fetch(`${API}${path}`, options);
  const body = await response.text();
  let data;
  try { data = body ? JSON.parse(body) : {}; } catch { data = {}; }
  if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
  return data;
}

function App() {
  const [page, setPage] = useState("dashboard");
  const [postings, setPostings] = useState({ items: [], total: 0 });
  const [targets, setTargets] = useState([]);
  const [run, setRun] = useState(null);
  const [search, setSearch] = useState("");
  const [deadline, setDeadline] = useState("");
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setError("");
      const query = `?search=${encodeURIComponent(search)}&deadline=${encodeURIComponent(deadline)}`;
      const [postingData, targetData] = await Promise.all([request(`/postings${query}`), request("/targets")]);
      setPostings(postingData);
      setTargets(targetData);
    } catch (err) { setError(err.message); }
    finally { setLoading(false); }
  }, [search, deadline]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!run?.id || ["COMPLETED", "FAILED"].includes(run.status)) return undefined;
    const timer = setInterval(async () => {
      try { setRun(await request(`/runs/${run.id}`)); } catch (err) { setError(err.message); }
    }, 1200);
    return () => clearInterval(timer);
  }, [run?.id, run?.status]);

  const start = async () => {
    if (starting || run?.status === "RUNNING") return;
    setStarting(true); setError("");
    try {
      const created = await request("/runs", { method: "POST" });
      setRun(created);
      setPage("run");
    } catch (err) { setError(err.message); }
    finally { setStarting(false); }
  };

  return <div className="shell">
    <header><div className="brand"><span>✦</span> Internship Radar</div>
      <nav><button className={page === "dashboard" ? "active" : ""} onClick={() => setPage("dashboard")}>Postings</button><button className={page === "targets" ? "active" : ""} onClick={() => setPage("targets")}>Targets</button>{run && <button className={page === "run" ? "active" : ""} onClick={() => setPage("run")}>Run Monitor</button>}</nav>
      <button className="primary" onClick={start} disabled={starting || run?.status === "RUNNING"}>{starting || run?.status === "RUNNING" ? <Spinner /> : <Play size={15} />} {starting || run?.status === "RUNNING" ? "Scraping…" : "Run"}</button>
    </header>
    {error && <div className="errorBanner"><span>{error}</span><button onClick={() => setError("")}><X size={16} /></button></div>}
    {page === "dashboard" && <Dashboard data={postings} loading={loading} search={search} setSearch={setSearch} deadline={deadline} setDeadline={setDeadline} start={start} />}
    {page === "targets" && <Targets targets={targets} reload={load} />}
    {page === "run" && <Run run={run} />}
  </div>;
}

function Spinner() { return <span className="spinner" aria-label="loading" />; }

function Dashboard({ data, loading, search, setSearch, deadline, setDeadline, start }) {
  return <main><div className="eyebrow">DISCOVER OPPORTUNITIES</div><div className="titleRow"><div><h1>Internship postings</h1><p>Fresh opportunities, extracted and organized for you.</p></div><button className="primary" onClick={start}><Play size={15} /> Start scrape</button></div>
    <div className="toolbar"><input placeholder="Search title or company" value={search} onChange={e => setSearch(e.target.value)} /><select><option>Any location</option></select><select value={deadline} onChange={e => setDeadline(e.target.value)}><option value="">Any deadline</option><option value="active">Active / upcoming</option><option value="past">Past</option></select><button onClick={() => { setSearch(""); setDeadline(""); }}><RefreshCw size={15} /> Reset</button></div>
    <section className="card table"><div className="tableHead"><span>TITLE</span><span>COMPANY</span><span>LOCATION</span><span>DEADLINE</span><span /></div>{loading ? <LoadingRows /> : data.items.map(p => <div className="row" key={p.id}><strong>{p.title}</strong><span>{p.company}</span><span>{p.location}</span><span>{p.deadline ? new Date(p.deadline).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "—"}</span><a href={p.url} target="_blank" rel="noreferrer"><ArrowUpRight size={16} /></a></div>)}{!loading && !data.items.length && <div className="empty">No postings yet. Add a target and run the scraper.</div>}<footer><span>Showing {data.items.length} of {data.total} postings</span></footer></section>
  </main>;
}

function LoadingRows() { return <>{[1, 2, 3].map(i => <div className="row loadingRow" key={i}><span /><span /><span /><span /><span /></div>)}</>; }

function Targets({ targets, reload }) {
  const [url, setUrl] = useState(""); const [saving, setSaving] = useState(false);
  const add = async () => { if (!url || saving) return; setSaving(true); try { await request("/targets", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url }) }); setUrl(""); await reload(); } finally { setSaving(false); } };
  return <main><div className="eyebrow">CONFIGURATION</div><div className="titleRow"><div><h1>Target domains</h1><p>Manage the career pages Internship Radar watches.</p></div></div><div className="add"><input placeholder="https://company.com/careers" value={url} onChange={e => setUrl(e.target.value)} /><button className="primary" onClick={add} disabled={saving}><Plus size={15} /> {saving ? "Adding…" : "Add target"}</button></div><section className="card table"><div className="tableHead target"><span>DOMAIN</span><span>STATUS</span><span>LAST SCRAPED</span><span>ACTIONS</span></div>{targets.map(t => <div className="row target" key={t.id}><strong>{t.url}</strong><span className={t.active ? "status on" : "status"}>● {t.active ? "active" : "paused"}</span><span>{t.last_scraped_at ? new Date(t.last_scraped_at).toLocaleString() : "Never"}</span><span className="actions"><button onClick={async () => { await request(`/targets/${t.id}/toggle`, { method: "PATCH" }); reload(); }}>{t.active ? <Pause size={14} /> : <Play size={14} />} {t.active ? "Pause" : "Resume"}</button><button onClick={async () => { await request(`/targets/${t.id}`, { method: "DELETE" }); reload(); }}><Trash2 size={14} /></button></span></div>)}</section></main>;
}

function Run({ run }) {
  if (!run) return <main><section className="card empty">Preparing scraper…</section></main>;
  const active = run.status === "RUNNING";
  return <main><div className="eyebrow">LIVE PIPELINE</div><div className="titleRow"><div><h1>Run #{run.id}</h1><p>Started {new Date(run.started_at).toLocaleTimeString()}</p></div><span className={`pill ${run.status.toLowerCase()}`}>{active && <Spinner />} {active ? "SCRAPING" : run.status}</span></div>{active && <div className="scrapeHero"><div className="radar"><span /><i /><i /><i /></div><div><strong>Scraping internship postings</strong><p>Discovering links and extracting company details. This page updates live.</p></div></div>}<section className="metrics"><div><label>DISCOVERY</label><b>{run.targets_completed || 0} / {run.targets_total || 0} targets</b></div><div><label>EXTRACTION</label><b>{run.urls_completed || 0} / {run.urls_total || 0} URLs</b></div><div><label>POSTINGS FOUND</label><b>{run.postings_found || 0}</b></div><div><label>NEW / UPDATED</label><b>{run.new_count || 0} / {run.updated_count || 0}</b></div></section><section className="card log"><h3>Live scrape log</h3>{(run.logs || []).length ? run.logs.slice().reverse().map((l, i) => <div className="logrow" key={`${l.url}-${i}`}><span className={l.status === "ok" ? "ok" : "bad"}>{l.status === "ok" ? "✓" : "✕"}</span><strong>{l.company || l.worker || "scraper"}</strong><code>{l.url || l.error}</code></div>) : <div className="empty logEmpty">Waiting for the first posting link…</div>}</section></main>;
}

createRoot(document.getElementById("root")).render(<App />);
