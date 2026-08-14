import React, { useCallback, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { ArrowLeft, ArrowRight, ArrowUpRight, Bolt, Pause, Play, Plus, RefreshCw, Trash2, X } from "lucide-react";
import "./style.css";

const API = `${window.location.protocol}//${window.location.hostname}:8000/api`;
const JOB_TYPES = ["All", "Full-Time", "Internship"];

async function request(path, options) {
  const response = await fetch(`${API}${path}`, options);
  const body = await response.text();
  let data = {};
  try { data = body ? JSON.parse(body) : {}; } catch { data = {}; }
  if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
  return data;
}

function App() {
  const [view, setView] = useState("dashboard");
  const [postings, setPostings] = useState({ items: [], total: 0 });
  const [targets, setTargets] = useState([]);
  const [sources, setSources] = useState([]);
  const [run, setRun] = useState(null);
  const [targetUrl, setTargetUrl] = useState("https://www.amazon.jobs/en/search?base_query=intern&loc_query=");
  const [jobType, setJobType] = useState("All");
  const [sourceSite, setSourceSite] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");

  const isScraping = run?.status === "RUNNING";

  const query = useMemo(() => {
    const params = new URLSearchParams({
      search,
      job_type: jobType,
      source_site: sourceSite,
      page: String(page),
      limit: "20",
    });
    return params.toString();
  }, [search, jobType, sourceSite, page]);

  const load = useCallback(async () => {
    try {
      setError("");
      const [postingData, targetData, sourceData] = await Promise.all([
        request(`/postings?${query}`),
        request("/targets"),
        request("/sources"),
      ]);
      setPostings(postingData);
      setTargets(targetData);
      setSources(sourceData.items || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    setPage(1);
  }, [search, jobType, sourceSite]);

  useEffect(() => {
    if (!run?.id || run.status !== "RUNNING") return undefined;
    const timer = setInterval(async () => {
      try {
        const latest = await request(`/runs/${run.id}`);
        setRun(latest);
        if (latest.status !== "RUNNING") await load();
      } catch (err) {
        setError(err.message);
      }
    }, 1200);
    return () => clearInterval(timer);
  }, [run?.id, run?.status, load]);

  const scrape = async () => {
    if (!targetUrl.trim() || starting || isScraping) return;
    setStarting(true);
    setError("");
    try {
      const created = await request("/scrape", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: targetUrl, job_type: jobType }),
      });
      setRun(created);
      setView("dashboard");
    } catch (err) {
      setError(err.message);
    } finally {
      setStarting(false);
    }
  };

  const runSavedTargets = async () => {
    if (starting || isScraping) return;
    setStarting(true);
    setError("");
    try {
      const created = await request(`/runs?job_type=${encodeURIComponent(jobType)}`, { method: "POST" });
      setRun(created);
      setView("dashboard");
    } catch (err) {
      setError(err.message);
    } finally {
      setStarting(false);
    }
  };

  return <div className="shell">
    <header className="topbar">
      <div className="brand"><span>USP</span> Universal Scraping Platform & Job Dashboard</div>
      <div className="system">System: OK</div>
      <nav>
        <button className={view === "dashboard" ? "active" : ""} onClick={() => setView("dashboard")}>Dashboard</button>
        <button className={view === "targets" ? "active" : ""} onClick={() => setView("targets")}>Targets</button>
      </nav>
    </header>

    {error && <div className="errorBanner"><span>{error}</span><button onClick={() => setError("")}><X size={16} /></button></div>}

    {view === "dashboard" && <Dashboard
      targetUrl={targetUrl}
      setTargetUrl={setTargetUrl}
      scrape={scrape}
      runSavedTargets={runSavedTargets}
      starting={starting}
      isScraping={isScraping}
      jobType={jobType}
      setJobType={setJobType}
      sourceSite={sourceSite}
      setSourceSite={setSourceSite}
      sources={sources}
      search={search}
      setSearch={setSearch}
      postings={postings}
      loading={loading}
      run={run}
      page={page}
      setPage={setPage}
    />}

    {view === "targets" && <Targets targets={targets} reload={load} setError={setError} />}
  </div>;
}

function Dashboard(props) {
  const pageCount = Math.max(1, Math.ceil((props.postings.total || 0) / 20));
  return <main>
    <section className="urlBand">
      <input
        value={props.targetUrl}
        onChange={event => props.setTargetUrl(event.target.value)}
        onKeyDown={event => event.key === "Enter" && props.scrape()}
        placeholder="Target URL: https://company.com/careers"
      />
      <button className="primary" onClick={props.scrape} disabled={props.starting || props.isScraping}>
        {props.starting || props.isScraping ? <Spinner /> : <Bolt size={17} />} {props.isScraping ? "Scraping" : "Scrape"}
      </button>
    </section>

    <section className="filters">
      <div className="sectionLabel">FILTERS & CONTROLS</div>
      <div className="filterGrid">
        <div className="toggleGroup" aria-label="Job type">
          <span>Job Type:</span>
          {JOB_TYPES.map(type => <button key={type} className={props.jobType === type ? "selected" : ""} onClick={() => props.setJobType(type)}>
            <i /> {type === "All" ? "All Jobs" : type}
          </button>)}
        </div>
        <label>Site Filter:
          <select value={props.sourceSite} onChange={event => props.setSourceSite(event.target.value)}>
            <option value="">All Domains</option>
            {props.sources.map(source => <option key={source} value={source}>{source}</option>)}
          </select>
        </label>
        <label>Search Postings:
          <input placeholder="Search title/city..." value={props.search} onChange={event => props.setSearch(event.target.value)} />
        </label>
        <button className="ghost" onClick={props.runSavedTargets}><RefreshCw size={15} /> Run saved targets</button>
      </div>
    </section>

    {props.isScraping && <ScrapeStatus run={props.run} />}

    <section className="postings">
      <div className="postingsTitle">POSTINGS <span>(Showing {props.postings.total || 0} Results)</span></div>
      <div className="table">
        <div className="tableHead"><span>TITLE</span><span>COMPANY</span><span>LOCATION</span><span>TYPE</span><span>ACTION</span></div>
        {props.loading ? <LoadingRows /> : props.postings.items.map(posting => <div className="row" key={posting.id}>
          <strong>{posting.job_title || posting.title}</strong>
          <span>{posting.company}</span>
          <span>{posting.location}</span>
          <span className={posting.job_type === "Internship" ? "type internship" : "type"}>{posting.job_type || posting.employment_type}</span>
          <a href={posting.apply_link || posting.url} target="_blank" rel="noreferrer">Apply <ArrowUpRight size={15} /></a>
        </div>)}
        {!props.loading && props.postings.items.length === 0 && <div className="empty">No postings yet. Submit a target URL and start scraping.</div>}
      </div>
      <footer className="pager">
        <button disabled={props.page <= 1} onClick={() => props.setPage(value => value - 1)}><ArrowLeft size={15} /> Previous</button>
        <span>Page {props.page} of {pageCount}</span>
        <button disabled={props.page >= pageCount} onClick={() => props.setPage(value => value + 1)}>Next <ArrowRight size={15} /></button>
      </footer>
    </section>
  </main>;
}

function ScrapeStatus({ run }) {
  const logs = run?.logs || [];
  return <section className="scrapeStatus" aria-live="polite">
    <div className="radar"><span /><i /><i /><i /></div>
    <div>
      <strong>Scraping in progress</strong>
      <p>{run?.urls_completed || 0} / {run?.urls_total || 0} postings processed. New: {run?.new_count || 0}, Updated: {run?.updated_count || 0}</p>
      <div className="miniLog">
        {logs.slice(-3).map((log, index) => <code key={`${log.url}-${index}`}>{log.tier || "scraper"}: {log.title || log.url || log.error}</code>)}
      </div>
    </div>
  </section>;
}

function Targets({ targets, reload, setError }) {
  const [url, setUrl] = useState("");
  const [saving, setSaving] = useState(false);

  const add = async () => {
    if (!url.trim() || saving) return;
    setSaving(true);
    setError("");
    try {
      await request("/targets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      setUrl("");
      await reload();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return <main>
    <section className="targetsPanel">
      <h1>Manage Target Domains</h1>
      <div className="addTarget">
        <input placeholder="https://company.com/careers" value={url} onChange={event => setUrl(event.target.value)} onKeyDown={event => event.key === "Enter" && add()} />
        <button className="primary" onClick={add} disabled={saving || !url.trim()}><Plus size={15} /> Add Target</button>
      </div>
      <div className="targetTable">
        <div className="targetHead"><span>DOMAIN</span><span>STATUS</span><span>LAST SCRAPED</span><span>ACTIONS</span></div>
        {targets.map(target => <div className="targetRow" key={target.id}>
          <strong>{target.url}</strong>
          <span className={target.active ? "status activeStatus" : "status"}>{target.active ? "active" : "paused"}</span>
          <span>{target.last_scraped_at ? new Date(target.last_scraped_at).toLocaleString() : "Never"}</span>
          <span className="actions">
            <button onClick={async () => { await request(`/targets/${target.id}/toggle`, { method: "PATCH" }); await reload(); }}>{target.active ? <Pause size={14} /> : <Play size={14} />}{target.active ? "Pause" : "Resume"}</button>
            <button onClick={async () => { await request(`/targets/${target.id}`, { method: "DELETE" }); await reload(); }}><Trash2 size={14} /></button>
          </span>
        </div>)}
      </div>
    </section>
  </main>;
}

function Spinner() { return <span className="spinner" aria-label="loading" />; }

function LoadingRows() {
  return <>{[1, 2, 3].map(index => <div className="row loadingRow" key={index}><span /><span /><span /><span /><span /></div>)}</>;
}

createRoot(document.getElementById("root")).render(<App />);
