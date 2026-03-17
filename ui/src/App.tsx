import React, { useState, useEffect, useRef } from 'react';
import {
  Activity, CheckCircle, AlertTriangle, FileText,
  ExternalLink, Clock, RefreshCw, 
  Cpu, Database, Zap, 
  Maximize2, Minimize2, MessageSquare,
  ChevronRight, ArrowLeft, ShieldAlert,
  PlusCircle, Search, X
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import './App.css';

/* Types */
interface EventRecord {
  timestamp: string;
  cycle: number;
  run_id: string;
  state: string;
  dag_id: string;
  task_id: string;
  scenario_name: string;
  logs_snippet: string;
  analysis: string;
  confidence: number;
  is_transient: boolean;
  requires_incident: boolean;
  remediation_action: string;
  remediation_source: string;
  remediation_reasoning: string;
  incident_number: string;
  incident_link: string;
  runbook_hit: boolean;
  dag_paused?: boolean;
  execution_logs?: string[];
}

interface CurrentJob {
  scenario_name: string;
  dag_id: string;
  task_id: string;
  logs: string;
  job_status: 'success' | 'failed';
}

interface RunGroup {
  run_id: string;
  dag_id: string;
  events: EventRecord[];
  latest_event: EventRecord;
  start_time: string;
  end_time: string;
  final_status: 'Incident (Paused)' | 'Incident' | 'Auto-Resolved' | 'In Progress' | 'Recovered';
}

interface UIState {
  status: 'idle' | 'polling' | 'analyzing' | 'finished' | 'watching';
  cycle: number;
  last_updated: string;
  next_event_in?: number;
  current: CurrentJob;
  events: EventRecord[];
  runbook_hit: boolean;
  confidence: number;
  needs_incident: boolean;
  is_transient: boolean;
  execution_logs?: string[];
  indexed_runbooks?: number;
  indexed_runbooks_list?: string[];
}

type ViewState = 'dashboard' | 'list' | 'detail' | 'analyze' | 'rag';
type FilterType = 'all' | 'incidents' | 'auto-resolved';

const EMPTY_STATE: UIState = {
  status: 'idle', cycle: 0, last_updated: '', next_event_in: undefined,
  current: { scenario_name: '', dag_id: '-', task_id: '-', logs: '', job_status: 'success' },
  events: [], runbook_hit: false, confidence: 0, needs_incident: false, is_transient: false,
  indexed_runbooks: 0
};

export default function App() {
  const [state, setState] = useState<UIState>(EMPTY_STATE);
  const prevJsonRef = useRef<string>('');
  
  // Routing State
  const [view, setView] = useState<ViewState>('dashboard');
  const [filter, setFilter] = useState<FilterType>('all');
  const [selectedRun, setSelectedRun] = useState<RunGroup | null>(null);

  // Manual Analyze State
  const [manualForm, setManualForm] = useState({
    jobName: '', runId: '', pipeline: '', errorCode: '', errorMessage: '',
    logExcerpt: '', errorFileContent: '', raiseIncident: true
  });

  // Chat State
  const [chatOpen, setChatOpen] = useState(false);
  const [chatMaximized, setChatMaximized] = useState(false);
  const [chatInput, setChatInput] = useState('');
  const [chatLog, setChatLog] = useState<{role: 'user'|'sys'; text: string}[]>([]);
  const [isChatting, setIsChatting] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Ingest State
  const [ingestModalOpen, setIngestModalOpen] = useState(false);
  const [ingestLogs, setIngestLogs] = useState('');
  const [ingestStatus, setIngestStatus] = useState<any>(null);
  const ingestLogEndRef = useRef<HTMLDivElement>(null);  // Data Polling
  const poll = async () => {
    try {
      const r = await fetch(`http://localhost:8766/api/state?_=${Date.now()}`);
      if (!r.ok) return;
      const data = await r.json();
      const text = JSON.stringify(data);
      if (text === prevJsonRef.current) return;
      prevJsonRef.current = text;
      setState(data);
    } catch (_) {}
  };

  const formatTime = (timeString: string, runId?: string) => {
    try {
      if (!timeString) return '';
      let dateToParse = timeString;
      if (dateToParse.includes(' ') && !dateToParse.includes('T')) {
          dateToParse = dateToParse.replace(' ', 'T');
      }
      
      // If timeString is just HH:mm:ss, it will fail new Date(). Combine it with date from runId.
      if (/^\d{2}:\d{2}:\d{2}$/.test(timeString) && runId) {
         const dateMatch = runId.match(/(\d{4}-\d{2}-\d{2})/);
         if (dateMatch) {
            dateToParse = `${dateMatch[1]}T${timeString}`;
         }
      }

      const d = new Date(dateToParse);
      if (isNaN(d.getTime())) return timeString;
      
      const opts: Intl.DateTimeFormatOptions = { 
         month: 'short', day: 'numeric', 
         hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false 
      };
      return d.toLocaleString('en-US', opts);
    } catch (e) {
      return timeString;
    }
  };

  useEffect(() => {
    poll();
    const id = setInterval(poll, 1500);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    let id: any;
    if (ingestModalOpen) {
      const fetchLogs = async () => {
        try {
          const res = await fetch('http://localhost:8766/api/logs');
          if (res.ok) {
            const data = await res.json();
            setIngestLogs(data.logs);
          }
          const sRes = await fetch('http://localhost:8766/api/status');
          if (sRes.ok) {
            setIngestStatus(await sRes.json());
          }
        } catch(e) {}
      };
      fetchLogs();
      id = setInterval(fetchLogs, 1000);
    }
    return () => clearInterval(id);
  }, [ingestModalOpen]);

  useEffect(() => {
    if (ingestModalOpen && ingestLogEndRef.current) {
      ingestLogEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [ingestLogs, ingestModalOpen]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatLog]);

  const handleChat = async (e: React.FormEvent) => {
    e.preventDefault();
    if(!chatInput.trim()) return;
    const msg = chatInput.trim();
    setChatInput('');
    setChatLog(prev => [...prev, {role: 'user', text: msg}]);
    setIsChatting(true);
    try {
      const res = await fetch('http://localhost:8766/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg })
      });
      const data = await res.json();
      const responseText = data.response || data.error;
      setChatLog(prev => [...prev, {role: 'sys', text: responseText}]);
      
      // Auto-maximize for long responses like incident tables
      if (responseText && responseText.length > 300) {
        setChatMaximized(true);
      }
    } catch (e) {
      setChatLog(prev => [...prev, {role: 'sys', text: "Error reaching chat API."}]);
    }
    setIsChatting(false);
  };

  const syncRAG = async () => {
    setIngestModalOpen(true);
    setIngestLogs('');
    setIngestStatus(null);
    try {
       await fetch('http://localhost:8766/api/ingest', { method: 'POST' });
    } catch(e) {}
  };

  const handleManualAnalyze = (e: React.FormEvent) => {
    e.preventDefault();
    alert("Triggering manual analysis for: " + manualForm.jobName + "\n\nBackend endpoint not yet fully implemented for manual scans, but UI is ready.");
  };

  const goToList = (f: FilterType) => { setFilter(f); setView('list'); };
  const goToDetail = (run: RunGroup) => { setSelectedRun(run); setView('detail'); };
  const goBack = () => { if (view === 'detail') setView('list'); else setView('dashboard'); };

  // Processing Events
  const { events, indexed_runbooks, indexed_runbooks_list } = state;
  const runGroupsMap = new Map<string, RunGroup>();
  
  events.forEach(e => {
    const key = e.run_id || `${e.dag_id}-${e.cycle}`; 
    if (!runGroupsMap.has(key)) {
      runGroupsMap.set(key, {
        run_id: e.run_id || 'unknown', dag_id: e.dag_id,
        events: [], latest_event: e,
        start_time: e.timestamp, end_time: e.timestamp, final_status: 'In Progress'
      });
    }
    const group = runGroupsMap.get(key)!;
    group.events.push(e);
    group.start_time = e.timestamp; 
  });
  
  const runGroups = Array.from(runGroupsMap.values());
  runGroups.forEach(group => {
    const latest = group.latest_event;
    let finalStatus: RunGroup['final_status'] = 'In Progress';
    if (latest.state === 'success') finalStatus = 'Auto-Resolved';
    else if (latest.requires_incident) finalStatus = latest.dag_paused ? 'Incident (Paused)' : 'Incident';
    else if (!latest.requires_incident && latest.remediation_action) finalStatus = 'Auto-Resolved';
    group.final_status = finalStatus;
  });

  const displayedRuns = runGroups.filter(g => {
    if (filter === 'incidents') return g.final_status.includes('Incident');
    if (filter === 'auto-resolved') return g.final_status === 'Auto-Resolved';
    return true;
  });

  let incCount = 0; let resolvedCount = 0; let ragHits = 0; let llmHits = 0;
  runGroups.forEach(g => {
    const l = g.latest_event;
    if (l.requires_incident) incCount++;
    else if (l.remediation_action || l.state === 'success') resolvedCount++;
    if (l.runbook_hit) ragHits++; else llmHits++;
  });

  return (
    <div className="app">
      {/* ─── Header ─── */}
      <div className="dashboard-header">
        <h1 className="dashboard-title" onClick={() => setView('dashboard')} style={{cursor:'pointer', display:'flex', alignItems:'center', gap:10}}>
           <Activity size={28} color="var(--accent-blue-pill)" /> Agentic SRE Dashboard
        </h1>
        <div style={{display: 'flex', gap: 12}}>
           {view !== 'analyze' && (
              <button className="btn-secondary" onClick={() => setView('analyze')} style={{display: 'flex', gap: 6, alignItems: 'center'}}>
                 <PlusCircle size={16} /> Analyze New Job
              </button>
           )}
        </div>
      </div>

      {/* ─── Dashboard View ─── */}
      {view === 'dashboard' && (
         <div className="animate-fade-in">
            <h2 style={{fontSize: 20, fontWeight: 700, marginBottom: 24}}>System Overview</h2>
            <div className="metrics-row" style={{display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16}}>
               <div className="metric-pill interactive" onClick={() => goToList('all')} style={{cursor: 'pointer'}}>
                 <div className="label">Total Analyzed Failures</div>
                 <div className="value" style={{marginTop: 'auto'}}>{runGroups.length}</div>
                 <div className="sub" style={{display:'flex', alignItems:'center', gap:6, marginTop:8}}><Search size={14}/> Click to view all logs</div>
               </div>
               <div className="metric-pill interactive" onClick={() => goToList('incidents')} style={{cursor: 'pointer'}}>
                 <div className="label">Open Incidents</div>
                 <div className="value" style={{marginTop: 'auto', color:'var(--status-incident)'}}>{incCount}</div>
                 <div className="sub" style={{display:'flex', alignItems:'center', gap:6, marginTop:8}}><AlertTriangle size={14} color="var(--status-incident)"/> Requires review</div>
               </div>
               <div className="metric-pill interactive" onClick={() => goToList('auto-resolved')} style={{cursor: 'pointer'}}>
                 <div className="label">Auto-Resolved Jobs</div>
                 <div className="value" style={{marginTop: 'auto', color:'var(--status-success)'}}>{resolvedCount}</div>
                 <div className="sub" style={{display:'flex', alignItems:'center', gap:6, marginTop:8}}><CheckCircle size={14} color="var(--status-success)"/> Fixed without humans</div>
               </div>
               <div className="metric-pill interactive" onClick={() => setView('rag')} style={{cursor: 'pointer'}}>
                 <div className="label">Last Synced Time</div>
                 <div className="value" style={{marginTop: 'auto', color:'var(--status-warning)', fontSize: '18px', whiteSpace: 'nowrap'}}>{state.last_updated ? formatTime(state.last_updated) : 'Never Synced'}</div>
                 <div className="sub" style={{display:'flex', alignItems:'center', gap:6, marginTop:8}}><Database size={14} color="var(--status-warning)"/> Knowledge Base</div>
               </div>
            </div>
         </div>
      )}

      {/* ─── List View ─── */}
      {view === 'list' && (
         <div className="animate-fade-in section-panel">
            <div className="section-header">
               <div style={{display:'flex', alignItems:'center', gap:16}}>
                  <button className="btn-icon" onClick={() => setView('dashboard')}><ArrowLeft size={20} /></button>
                  <h2 className="section-title">Job Failure History</h2>
               </div>
               <div style={{ display: 'flex', gap: 8 }}>
                 <button className={`btn-secondary ${filter === 'all' ? 'active-filter' : ''}`} onClick={() => setFilter('all')}>All ({runGroups.length})</button>
                 <button className={`btn-secondary ${filter === 'incidents' ? 'active-filter' : ''}`} onClick={() => setFilter('incidents')}>Incidents ({incCount})</button>
                 <button className={`btn-secondary ${filter === 'auto-resolved' ? 'active-filter' : ''}`} onClick={() => setFilter('auto-resolved')}>Auto-Resolved ({resolvedCount})</button>
               </div>
            </div>
            {displayedRuns.length === 0 ? (
               <div style={{padding: 60, textAlign: 'center', color: 'var(--text-tertiary)'}}>No jobs found matching the current filter.</div>
            ) : (
               <table className="data-table">
                  <thead>
                     <tr>
                        <th>DAG / Scenario</th><th>RUN ID</th><th>RESOLUTION</th><th>CONFIDENCE</th><th>SOURCE</th><th>INCIDENT</th><th>TIME</th><th></th>
                     </tr>
                  </thead>
                  <tbody>
                     {displayedRuns.map((g, idx) => (
                        <tr key={idx} className="clickable" onClick={() => goToDetail(g)} style={{cursor: 'pointer'}}>
                           <td style={{fontWeight: 600, color: 'var(--text-primary)', whiteSpace: 'nowrap'}}>{g.latest_event.scenario_name || g.dag_id}</td>
                           <td style={{color: 'var(--text-tertiary)', whiteSpace: 'nowrap'}}><code>{g.run_id}</code></td>
                           <td style={{whiteSpace: 'nowrap'}}>
                              {g.final_status.includes('Incident') ? <span className="badge-confidence" style={{background:'var(--status-incident)', color:'#fff'}}>Incident Logged</span> : <span className="badge-rag" style={{background:'var(--status-success)', color:'#fff'}}>Auto-Resolved</span>}
                           </td>
                           <td><span className="badge-confidence">{(g.latest_event.confidence * 100).toFixed(1)}%</span></td>
                           <td style={{whiteSpace: 'nowrap'}}>{g.latest_event.runbook_hit ? <span className="badge-rag">Knowledge Base</span> : <span className="badge-rag" style={{background:'#E0E7FF', color:'#3730A3'}}>AI Suggested</span>}</td>
                           <td style={{whiteSpace: 'nowrap'}}>
                              {g.latest_event.incident_number && !g.latest_event.incident_number.includes('N/A') ? (
                                 <a href={g.latest_event.incident_link} target="_blank" rel="noreferrer" onClick={e=>e.stopPropagation()} style={{color:'var(--accent-blue-pill)', textDecoration:'none', fontWeight: 600}}>{g.latest_event.incident_number}</a>
                              ) : (
                                 <span style={{color:'#000', fontWeight:600}}>-</span>
                              )}
                           </td>
                           <td style={{whiteSpace: 'nowrap'}}>{formatTime(g.start_time, g.run_id)}</td>
                           <td style={{textAlign:'right'}}><ChevronRight size={18} color="var(--text-tertiary)"/></td>
                        </tr>
                     ))}
                  </tbody>
               </table>
            )}
         </div>
      )}

      {/* ─── Analyze View ─── */}
      {view === 'analyze' && (
         <div className="animate-fade-in section-panel" style={{maxWidth: 800, margin: '0 auto', width: '100%'}}>
            <div className="section-header border-bottom">
               <div style={{display:'flex', alignItems:'center', gap:16}}>
                  <button className="btn-icon" onClick={() => setView('dashboard')}><ArrowLeft size={20} /></button>
                  <h2 className="section-title">Analyze New Job Failure</h2>
               </div>
            </div>
            <p style={{color:'var(--text-secondary)', marginBottom: 24}}>Manually trigger the SRE Agent to analyze a job failure outside of the automated polling cycle.</p>
            <form onSubmit={handleManualAnalyze}>
               <div className="form-grid">
                  <input className="form-input" placeholder="Job Name" required value={manualForm.jobName} onChange={e=>setManualForm({...manualForm, jobName: e.target.value})} />
                  <input className="form-input" placeholder="Run ID" value={manualForm.runId} onChange={e=>setManualForm({...manualForm, runId: e.target.value})} />
                  <input className="form-input" placeholder="Pipeline (e.g. Airflow, Control-M)" required value={manualForm.pipeline} onChange={e=>setManualForm({...manualForm, pipeline: e.target.value})} />
                  <input className="form-input" placeholder="Error Code" value={manualForm.errorCode} onChange={e=>setManualForm({...manualForm, errorCode: e.target.value})} />
                  <div style={{gridColumn: '1 / -1'}}><input className="form-input" placeholder="Error Message Summary" value={manualForm.errorMessage} onChange={e=>setManualForm({...manualForm, errorMessage: e.target.value})} /></div>
                  <div style={{gridColumn: '1 / -1'}}><textarea className="form-textarea" placeholder="Paste Error Log Excerpt..." value={manualForm.logExcerpt} onChange={e=>setManualForm({...manualForm, logExcerpt: e.target.value})} /></div>
                  <div style={{gridColumn: '1 / -1'}}><textarea className="form-textarea" placeholder="Paser Error File Content (Optional)..." value={manualForm.errorFileContent} onChange={e=>setManualForm({...manualForm, errorFileContent: e.target.value})} /></div>
               </div>
               <div style={{display:'flex', alignItems: 'center', justifyContent: 'center', gap: 8, margin: '20px 0'}}>
                  <input type="checkbox" id="raiseInc" checked={manualForm.raiseIncident} onChange={e=>setManualForm({...manualForm, raiseIncident: e.target.checked})} />
                  <label htmlFor="raiseInc" style={{fontWeight: 500}}>Raise ServiceNow Incident Automatically if unresolvable</label>
               </div>
               <button type="submit" className="btn-primary" style={{width: '100%', padding: '16px', fontSize: 16}}>Scan & Analyze Job Failure</button>
            </form>
         </div>
      )}

      {/* ─── RAG View ─── */}
      {view === 'rag' && (
         <div className="animate-fade-in section-panel" style={{maxWidth: 800, margin: '0 auto', width: '100%'}}>
            <div className="section-header border-bottom">
               <div style={{display:'flex', alignItems:'center', gap:16}}>
                  <button className="btn-icon" onClick={() => setView('dashboard')}><ArrowLeft size={20} /></button>
                  <h2 className="section-title">Knowledge Base Sync</h2>
               </div>
               <button className="btn-primary" onClick={syncRAG} style={{display:'flex', alignItems:'center', gap:8}}>
                  <RefreshCw size={16}/> Sync Confluence Now
               </button>
            </div>
            <p style={{color:'var(--text-secondary)', marginBottom: 24}}>
               The agent uses vector similarity search against these synchronized documents to resolve failures without human intervention.
            </p>
            <div style={{display: 'flex', flexDirection: 'column', gap: 16}}>
               <div style={{padding: 24, background: 'var(--panel-hover)', borderRadius: 12, border: '1px solid var(--panel-border)'}}>
                  <div style={{fontSize: 32, fontWeight: 700, color: 'var(--accent-blue-pill)'}}>{indexed_runbooks || 0}</div>
                  <div style={{fontSize: 14, fontWeight: 600}}>Documents Currently Indexed</div>
                  <div style={{fontSize: 13, color: 'var(--text-tertiary)', marginTop: 8}}>Sources: {indexed_runbooks_list ? indexed_runbooks_list.join(', ') : 'None'}</div>
               </div>
            </div>
         </div>
      )}

      {/* ─── Detail View ─── */}
      {view === 'detail' && selectedRun && (
        <div className="animate-fade-in">
          <div className="section-header" style={{background:'var(--panel)', padding: 24, borderRadius: 12, border: '1px solid var(--panel-border)', marginBottom: 24}}>
             <div style={{display:'flex', alignItems:'flex-start', justifyContent:'space-between'}}>
                <div>
                   <button className="btn-icon" onClick={goBack} style={{marginBottom: 16, display:'flex', alignItems:'center', gap:6, padding:0}}>
                      <ArrowLeft size={16} /> <span style={{fontSize:13, fontWeight:600}}>Back</span>
                   </button>
                   <h2 className="section-title" style={{fontSize: 24, marginBottom: 8}}>{selectedRun.latest_event.scenario_name || 'AI Analyzed Failure'}</h2>
                   <div style={{display:'flex', gap:12}}>
                      <span className="badge-rag" style={{background:'var(--panel-hover)', color:'var(--text-secondary)', border:'1px solid var(--panel-border)'}}><Clock size={12}/> Run ID: {selectedRun.run_id}</span>
                      <span className="badge-rag" style={{background:'var(--panel-hover)', color:'var(--text-secondary)', border:'1px solid var(--panel-border)'}}><Database size={12}/> DAG: {selectedRun.dag_id}</span>
                   </div>
                </div>
                {selectedRun.latest_event.requires_incident && selectedRun.latest_event.incident_link && (
                  <a href={selectedRun.latest_event.incident_link} target="_blank" rel="noreferrer" className="btn-primary" style={{background: 'var(--status-incident)'}}>
                    View Target ServiceNow Ticket <ExternalLink size={14}/>
                  </a>
                )}
             </div>
          </div>

          <div style={{ marginTop: 24, paddingLeft: 16 }}>
            {selectedRun.events.slice().reverse().map((ev, idx) => (
              <div key={idx} style={{ position: 'relative', paddingLeft: 32, paddingBottom: 40, borderLeft: '2px solid var(--panel-border)' }}>
                <div style={{ position: 'absolute', left: -9, top: 0, width: 16, height: 16, borderRadius: '50%', background: ev.requires_incident ? 'var(--status-incident)' : 'var(--status-success)', border: '3px solid var(--bg)' }} />
                
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
                  <span style={{ fontWeight: 700, fontSize: 16, color: 'var(--text-primary)' }}>Attempt {idx + 1}</span>
                  <span className="badge-rag" style={{background:'var(--panel)', border:'1px solid var(--panel-border)', color:'var(--text-secondary)'}}><Clock size={12}/> {formatTime(ev.timestamp, ev.run_id)}</span>
                  {ev.runbook_hit ? 
                    <span className="badge-rag" title={ev.remediation_source} style={{cursor: 'help'}}><FileText size={12}/> Mapped: {ev.remediation_source || 'Doc'}</span> : 
                    <span className="badge-rag" style={{background:'#E0E7FF', color:'#3730A3'}}><Zap size={12}/> AI Suggested</span>
                  }
                </div>
                
                <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 24 }}>
                  <div className="section-panel" style={{boxShadow: 'none'}}>
                    <h3 style={{fontSize: 14, textTransform:'uppercase', fontWeight: 700, color: 'var(--accent-blue-pill)', display:'flex', alignItems:'center', gap:8, marginBottom:16}}><Cpu size={16}/> AI Assessment</h3>
                    <p style={{fontSize: 15, lineHeight: 1.7, color: 'var(--text-secondary)'}}>{ev.analysis || "Pending..."}</p>
                    
                    {ev.remediation_action && (
                       <div style={{ marginTop: 24, padding: 20, background: 'var(--panel-hover)', borderRadius: 8, borderLeft: '4px solid var(--status-incident)' }}>
                         <span style={{ display: 'block', fontSize: 12, fontWeight: 700, color: 'var(--status-incident)', textTransform: 'uppercase', marginBottom: 12 }}>Remediation Action Taken</span>
                         <pre style={{ margin: 0, whiteSpace:'pre-wrap', fontFamily:'JetBrains Mono, monospace', fontSize: 13, color:'var(--text-primary)' }}>
                           {ev.remediation_action}
                         </pre>
                       </div>
                    )}
                  </div>
                  
                  {ev.logs_snippet && (
                    <div className="section-panel" style={{boxShadow: 'none'}}>
                      <h3 style={{fontSize: 14, textTransform:'uppercase', fontWeight: 700, display:'flex', alignItems:'center', gap:8, marginBottom:16, color:'var(--text-secondary)'}}><ShieldAlert size={16}/> Captured Error Logs</h3>
                      <pre style={{background:'#1E293B', color:'#F8FAFC', padding: 20, borderRadius: 8, overflowX:'auto', fontSize:13, fontFamily:'JetBrains Mono, monospace', margin:0}}>{ev.logs_snippet}</pre>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Shared Chat Widget */}
      <div className={`chat-widget ${chatOpen ? 'open' : ''} ${chatMaximized ? 'maximized' : ''}`}>
        {!chatOpen && (
          <button className="chat-toggle tooltip" onClick={() => setChatOpen(true)}>
            <MessageSquare size={20} />
            Ask Agent
          </button>
        )}
        {chatOpen && (
          <div className="chat-window">
             <div className="chat-header" style={{background: 'var(--accent-blue-pill)', color: '#fff', borderTopLeftRadius: 12, borderTopRightRadius: 12, padding: '14px 18px', display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                <span style={{fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8, fontSize: 15}}><Activity size={18}/> SRE AI Assistant</span>
                <div style={{display: 'flex', gap: 12}}>
                  <button type="button" onClick={() => setChatMaximized(!chatMaximized)} style={{background:'none',border:'none',color:'#fff',cursor:'pointer', display:'flex'}}>
                    {chatMaximized ? <Minimize2 size={18}/> : <Maximize2 size={18}/>}
                  </button>
                  <button type="button" onClick={() => setChatOpen(false)} style={{background:'none',border:'none',color:'#fff',cursor:'pointer', display:'flex'}}>
                    <X size={20}/>
                  </button>
                </div>
             </div>
            <div className="chat-log">
              {chatLog.map((m, i) => (
                <div key={i} className={`chat-msg ${m.role}`} style={{
                  alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
                  background: m.role === 'user' ? 'var(--accent-blue-pill)' : '#F1F5F9',
                  color: m.role === 'user' ? '#fff' : 'var(--text-primary)',
                  padding: '10px 14px', borderRadius: 12, maxWidth: '85%', marginBottom: 12, border: m.role==='sys'?'1px solid var(--panel-border)':'none'
                }}>
                  {m.role === 'sys' ? (
                     <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.text}</ReactMarkdown>
                  ) : m.text}
                </div>
              ))}
              {isChatting && <div style={{fontStyle:'italic', color:'var(--text-tertiary)', fontSize: 13}}>Agent is typing...</div>}
              <div ref={chatEndRef} />
            </div>
            <form onSubmit={handleChat} className="chat-form">
              <input type="text" value={chatInput} onChange={(e) => setChatInput(e.target.value)} placeholder="Ask about active incidents..." disabled={isChatting} />
              <button type="submit" disabled={isChatting}>Send</button>
            </form>
          </div>
        )}
      </div>

      
      {/* ─── Ingest Modal Overlay ─── */}
      {ingestModalOpen && (
        <div className="modal-overlay" style={{position:'fixed', top:0, left:0, right:0, bottom:0, background:'rgba(15,23,42,0.8)', zIndex: 10000, display:'flex', alignItems:'center', justifyContent:'center'}}>
          <div className="modal-content" style={{background:'var(--bg)', width:'80%', maxWidth: 800, borderRadius: 12, overflow:'hidden', display:'flex', flexDirection:'column', maxHeight:'80vh'}}>
            <div style={{padding: '16px 24px', background:'var(--panel)', borderBottom:'1px solid var(--panel-border)', display:'flex', justifyContent:'space-between', alignItems:'center'}}>
              <h3 style={{margin:0, display:'flex', alignItems:'center', gap:8}}><Database size={18} color="var(--accent-blue-pill)"/> Knowledge Base Sync</h3>
              <button onClick={() => setIngestModalOpen(false)} style={{background:'none', border:'none', cursor:'pointer', color:'var(--text-tertiary)'}}><X size={20}/></button>
            </div>
            <div style={{padding: 24, flex: 1, overflowY:'auto', background:'#1E293B', color:'#F8FAFC', fontFamily:'JetBrains Mono, monospace', fontSize:13, whiteSpace:'pre-wrap'}}>
              {ingestLogs || 'Starting ingestion...'}
              <div ref={ingestLogEndRef} />
            </div>
            {ingestStatus && ingestStatus.running === false && (
              <div style={{padding: 16, borderTop:'1px solid var(--panel-border)', background:'var(--panel)', textAlign:'right'}}>
                <span style={{marginRight: 16, fontWeight: 600, color: ingestStatus.last_result === 'success' ? 'var(--status-success)' : 'var(--status-incident)'}}>
                  {ingestStatus.last_result === 'success' ? 'Sync Completed Successfully' : 'Sync Failed'}
                </span>
                <button className="btn-primary" onClick={() => { setIngestModalOpen(false); poll(); }}>Close</button>
              </div>
            )}
          </div>
        </div>
      )}

    </div>
  );
}
