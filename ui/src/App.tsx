import React, { useState, useEffect, useRef } from 'react';
import {
  Activity, CheckCircle, AlertTriangle, FileText,
  ExternalLink, Clock,
  Cpu, Database, Zap, TrendingUp, Terminal as TerminalIcon,
  Maximize2, Minimize2, MessageSquare,
  ChevronRight, ArrowLeft, ShieldAlert,
  ListFilter, X
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

/* Constants */
const QUICK_LINKS = [
  { label: 'Airflow Scheduler', url: 'http://localhost:8080', color: 'var(--accent-blue)', desc: 'Job Orchestration' },
  { label: 'ServiceNow',  url: 'https://dev.service-now.com', color: '#10B981', desc: 'Incident Tracking' },
  { label: 'Confluence Wiki',   url: 'https://personalinbox999.atlassian.net/wiki/spaces/MFS/pages', color: '#0052CC', desc: 'Runbook Docs' },
];

const EMPTY_STATE: UIState = {
  status: 'idle', cycle: 0, last_updated: '', next_event_in: undefined,
  current: { scenario_name: '', dag_id: '-', task_id: '-', logs: '', job_status: 'success' },
  events: [], runbook_hit: false, confidence: 0, needs_incident: false, is_transient: false,
  indexed_runbooks: 0
};

/* Sub-components */
function Terminal({ lines, title, height = 200 }: { lines: string[]; title?: string; height?: number | string }) {
  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [lines]);

  return (
    <div className="terminal-container" style={{ height }}>
      {title && <div className="terminal-header">{title}</div>}
      <div className="terminal-content" ref={scrollRef}>
        {lines.map((l, i) => (
          <div key={i} className="terminal-line">
            <span className="terminal-ln">{i + 1}</span>
            <span className="terminal-txt">{l}</span>
          </div>
        ))}
        {lines.length === 0 && <div className="text-secondary" style={{ padding: 10 }}>No logs recorded yet.</div>}
      </div>
    </div>
  );
}



/* ─── Metric Card ─── */
function MetricCard({ 
  icon, label, value, sub, colorClass, bgIcon, onClick, active 
}: { 
  icon: React.ReactNode; label: string; value: string | number; sub?: string; colorClass?: string; bgIcon: React.ReactNode;
  onClick?: () => void; active?: boolean;
}) {
  return (
    <div
      className={`metric-card ${onClick ? 'interactive' : ''}`}
      onClick={onClick}
      style={active ? { borderColor: 'var(--accent-blue)', boxShadow: 'var(--shadow-glow)' } : {}}
    >
      <div className="metric-header">
        <span className="metric-title">{label}</span>
        <div className={`metric-icon-wrap ${colorClass || ''}`}>
          {icon}
        </div>
      </div>
      <div>
        <div className="metric-value">{value}</div>
        {sub && <div className="metric-sub">{sub}</div>}
      </div>
      <div className="metric-bg-icon">{bgIcon}</div>
    </div>
  );
}

/* ─── Main App ─── */
type ViewState = 'dashboard' | 'list' | 'detail';
type FilterType = 'all' | 'incidents' | 'auto-resolved';

export default function App() {
  const [state, setState] = useState<UIState>(EMPTY_STATE);
  const prevJsonRef = useRef<string>('');

  // Routing State
  const [view, setView] = useState<ViewState>('dashboard');
  const [filter, setFilter] = useState<FilterType>('all');
  const [selectedRun, setSelectedRun] = useState<RunGroup | null>(null);
  const [showRunbooksModal, setShowRunbooksModal] = useState(false);

  useEffect(() => {
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
    poll();
    const id = setInterval(poll, 1500);
    return () => clearInterval(id);
  }, []);

  const { status, events, indexed_runbooks } = state;
  
  // Computed Metrics (Grouped by Run)
  // Events come from backend in DESC order (most recent first)
  const runGroupsMap = new Map<string, RunGroup>();
  
  events.forEach(e => {
    // Fallback composite key if run_id is missing on older events
    const key = e.run_id || `${e.dag_id}-${e.cycle}`; 
    if (!runGroupsMap.has(key)) {
      runGroupsMap.set(key, {
        run_id: e.run_id || 'unknown',
        dag_id: e.dag_id,
        events: [],
        latest_event: e, // First one we see is the latest because of DESC order
        start_time: e.timestamp,
        end_time: e.timestamp,
        final_status: e.requires_incident ? 'Incident' : 'Auto-Resolved'
      });
    }
    const group = runGroupsMap.get(key)!;
    group.events.push(e);
    // Update start time to the oldest event
    group.start_time = e.timestamp; 
  });
  
  const runGroups = Array.from(runGroupsMap.values());

  // Determine final status for each run group
  runGroups.forEach(group => {
    const latest = group.latest_event;
    let finalStatus: RunGroup['final_status'] = 'In Progress';
    if (latest.state === 'success') {
      finalStatus = 'Auto-Resolved';
    } else if (latest.requires_incident) {
      finalStatus = latest.dag_paused ? 'Incident (Paused)' : 'Incident';
    } else if (!latest.requires_incident && latest.remediation_action) {
      finalStatus = 'Auto-Resolved';
    }
    group.final_status = finalStatus;
  });

  const totalFailures = runGroups.length;
  const incCount      = runGroups.filter(g => g.final_status === 'Incident' || g.final_status === 'Incident (Paused)').length;
  const autoResCount  = runGroups.filter(g => g.final_status === 'Auto-Resolved').length;
  
  // Filtering
  const displayedRuns = runGroups.filter(g => {
    if (filter === 'incidents') return g.final_status === 'Incident' || g.final_status === 'Incident (Paused)';
    if (filter === 'auto-resolved') return g.final_status === 'Auto-Resolved';
    return true;
  });

  // Navigation Handlers
  const goToList = (newFilter: FilterType) => {
    setFilter(newFilter);
    setView('list');
  };

  const goToDetail = (run: RunGroup) => {
    setSelectedRun(run);
    setView('detail');
  };

  const goBack = () => {
    if (view === 'detail') setView('list');
    else setView('dashboard');
  };

  // Chat State
  const [chatOpen, setChatOpen] = useState(false);
  const [chatMaximized, setChatMaximized] = useState(false);
  const [chatInput, setChatInput] = useState('');
  const [chatLog, setChatLog] = useState<{role: 'user'|'sys'; text: string}[]>([]);
  const [isChatting, setIsChatting] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);
  
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
      setChatLog(prev => [...prev, {role: 'sys', text: data.response || data.error}]);
    } catch (e) {
      setChatLog(prev => [...prev, {role: 'sys', text: "Error reaching chat API."}]);
    }
    setIsChatting(false);
  };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand" onClick={() => setView('dashboard')} style={{cursor: 'pointer'}}>
          <Activity size={28} className="brand-icon" />
          <h1 className="brand-title">Synchrony SRE Dashboard</h1>
        </div>
        <div className="topbar-right">
          <div className="quick-links">
            {QUICK_LINKS.map(l => (
              <a key={l.label} href={l.url} target="_blank" rel="noreferrer" className="quick-link">
                <span style={{ color: l.color }}><ExternalLink size={14} /></span>
                {l.label}
              </a>
            ))}
          </div>
          <div className="live-status">
            <div className={`pulse-dot ${['polling','analyzing'].includes(status) ? 'polling' : ''}`} />
            <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)' }}>
              {status === 'idle' ? 'System Idle' : status === 'watching' ? 'Watching Airflow' : 'AI Active'}
            </span>
          </div>
        </div>
      </header>

      {view === 'dashboard' && (
        <div className="animate-fade-in">
          <div className="metrics-grid">
            <MetricCard 
              icon={<ShieldAlert size={20} />} 
              bgIcon={<ShieldAlert size={120} />}
              label="Total Failures Analyzed" 
              value={totalFailures} 
              sub="Extracted via Webhook"
              colorClass="badge-blue"
              onClick={() => goToList('all')}
            />
            <MetricCard 
              icon={<AlertTriangle size={20} />} 
              bgIcon={<AlertTriangle size={120} />}
              label="Active Incidents Logged" 
              value={incCount} 
              sub="Awaiting manual review"
              colorClass="badge-incident"
              onClick={() => goToList('incidents')}
            />
            <MetricCard 
              icon={<TrendingUp size={20} />} 
              bgIcon={<TrendingUp size={120} />}
              label="Auto-Resolved Jobs" 
              value={autoResCount} 
              sub="Zero human touch needed"
              colorClass="badge-success"
              onClick={() => goToList('auto-resolved')}
            />
            <MetricCard 
              icon={<Database size={20} />} 
              bgIcon={<Database size={120} />}
              label="Ingested Runbooks" 
              value={indexed_runbooks ?? 0} 
              sub="Indexed in Oracle Vector DB"
              colorClass="badge-warning"
              onClick={() => setShowRunbooksModal(true)}
            />
          </div>

          <div style={{ marginTop: 40, textAlign: 'center' }}>
            <button className="btn" onClick={() => goToList('all')} style={{ padding: '12px 24px', fontSize: 15 }}>
              <ListFilter size={18} /> View All Analyzed Jobs
            </button>
          </div>
        </div>
      )}

      {view === 'list' && (
        <div className="animate-fade-in">
          <div className="section-header">
            <div className="section-title">
              <button className="btn-icon" onClick={goBack}><ArrowLeft size={20} /></button>
              AI-Analyzed Job History
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className={`btn ${filter === 'all' ? 'active' : ''}`} onClick={() => setFilter('all')}>All</button>
              <button className={`btn ${filter === 'incidents' ? 'active' : ''}`} onClick={() => setFilter('incidents')}>Incidents ({incCount})</button>
              <button className={`btn ${filter === 'auto-resolved' ? 'active' : ''}`} onClick={() => setFilter('auto-resolved')}>Auto-Resolved ({autoResCount})</button>
            </div>
          </div>

          {displayedRuns.length === 0 ? (
            <div className="empty-state">
              <CheckCircle size={48} style={{ color: 'var(--status-success)', opacity: 0.5 }} />
              <div>
                <h3 style={{ fontSize: 18, color: 'var(--text-primary)', marginBottom: 4 }}>All Clear</h3>
                <p>No jobs found matching the current filter.</p>
              </div>
            </div>
          ) : (
            <div style={{ background: 'var(--panel)', borderRadius: 12, border: '1px solid var(--panel-border)', overflow: 'hidden' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th style={{ width: '15%' }}>Time / Frequency</th>
                    <th style={{ width: '25%' }}>Failing DAG & Task</th>
                    <th style={{ width: '40%' }}>AI Analysis Summary</th>
                    <th style={{ width: '15%' }}>Resolution</th>
                    <th style={{ width: '5%', textAlign: 'right' }}></th>
                  </tr>
                </thead>
                <tbody>
                  {displayedRuns.map((run, i) => {
                    const latest = run.latest_event;
                    return (
                      <tr key={i} className="clickable" onClick={() => goToDetail(run)}>
                        <td>
                          <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{run.start_time}</div>
                          <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginTop: 4 }}>
                            {run.events.length} event{run.events.length !== 1 ? 's' : ''}
                          </div>
                        </td>
                        <td>
                          <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>{latest.scenario_name || run.dag_id}</div>
                          <code style={{ background: 'rgba(255,255,255,0.05)', padding: '2px 6px', borderRadius: 4, fontSize: 11, color: 'var(--text-secondary)' }}>
                            {run.dag_id} :: {latest.task_id || 'unknown'}
                          </code>
                        </td>
                        <td>
                          <div style={{ fontSize: 13, color: 'var(--text-secondary)', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                            {latest.analysis || "Analysis pending..."}
                          </div>
                        </td>
                        <td>
                          {run.final_status === 'Incident (Paused)' ? (
                            <span className="badge badge-incident"><AlertTriangle size={12} /> Paused & Escalated</span>
                          ) : run.final_status === 'Incident' ? (
                            <span className="badge badge-incident"><AlertTriangle size={12} /> SNOW Incident</span>
                          ) : (
                            <span className="badge badge-success"><CheckCircle size={12} /> Auto-Resolved</span>
                          )}
                        </td>
                        <td style={{ textAlign: 'right' }}>
                          <ChevronRight size={18} style={{ color: 'var(--text-tertiary)' }} />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {view === 'detail' && selectedRun && (
        <div className="animate-fade-in">
          <div className="detail-nav">
            <button className="btn-icon" onClick={goBack}><ArrowLeft size={18} /></button>
            <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)' }}>Back to List</span>
          </div>

          <div className="detail-header">
            <div className="detail-title-row">
              <div>
                <h2 className="detail-title">{selectedRun.latest_event.scenario_name || 'AI Analyzed Failure'}</h2>
                <div style={{ display: 'flex', gap: 12, marginTop: 8 }}>
                  <span className="badge badge-neutral"><Clock size={12}/> Run ID: {selectedRun.run_id}</span>
                  {selectedRun.final_status.includes('Incident') ? 
                    <span className="badge badge-incident"><AlertTriangle size={12}/> Requires Manual Review</span> : 
                    <span className="badge badge-success"><CheckCircle size={12}/> Automatable Fix</span>
                  }
                </div>
              </div>
              {selectedRun.latest_event.requires_incident && selectedRun.latest_event.incident_link && (
                <a href={selectedRun.latest_event.incident_link} target="_blank" rel="noreferrer" className="btn" style={{ borderColor: 'var(--status-incident)', color: 'var(--status-incident)' }}>
                  View ServiceNow Ticket <ExternalLink size={14}/>
                </a>
              )}
            </div>
            
            <div className="detail-meta-grid">
              <div className="meta-item">
                <span className="meta-label">DAG ID</span>
                <span className="meta-value">{selectedRun.dag_id}</span>
              </div>
              <div className="meta-item">
                <span className="meta-label">Total Retries</span>
                <span className="meta-value">{selectedRun.events.length}</span>
              </div>
              <div className="meta-item">
                <span className="meta-label">Final Status</span>
                <span className="meta-value">{selectedRun.final_status}</span>
              </div>
            </div>
          </div>

          <div className="timeline-container" style={{ marginTop: 24, paddingLeft: 16 }}>
            {selectedRun.events.slice().reverse().map((ev, idx) => (
              <div key={idx} className="timeline-event" style={{ position: 'relative', paddingLeft: 24, paddingBottom: 32, borderLeft: '2px solid var(--panel-border)' }}>
                <div style={{ position: 'absolute', left: -7, top: 0, width: 12, height: 12, borderRadius: '50%', background: ev.requires_incident ? 'var(--status-incident)' : 'var(--status-success)', border: '2px solid var(--bg-dark)' }} />
                
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
                  <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Attempt {idx + 1}</span>
                  <span className="badge badge-neutral"><Clock size={12}/> {ev.timestamp}</span>
                  {ev.runbook_hit ? 
                    <span className="badge badge-blue"><FileText size={12}/> Runbook Mapped</span> : 
                    <span className="badge badge-warning"><Zap size={12}/> Zero-Shot Reasoning</span>
                  }
                </div>
                
                <div className="detail-body-grid" style={{ gridTemplateColumns: 'minmax(0, 1fr)', marginTop: 16 }}>
                  <div className="detail-panel">
                    <h3 className="panel-heading text-secondary"><Cpu size={16}/> AI Assessment</h3>
                    <p className="analysis-text">{ev.analysis || "Pending..."}</p>
                    
                    <div style={{ marginTop: 16, padding: 16, background: 'rgba(0,0,0,0.2)', borderRadius: 8, borderLeft: '3px solid var(--accent-purple)' }}>
                      <span style={{ display: 'block', fontSize: 11, fontWeight: 600, color: 'var(--accent-purple)', textTransform: 'uppercase', marginBottom: 8 }}>Remediation Action Taken</span>
                      <pre className="code-block" style={{ background: 'transparent', padding: 0, margin: 0, border: 'none' }}>
                        {ev.remediation_action}
                      </pre>
                    </div>
                  </div>
                  
                  {ev.logs_snippet && (
                    <div className="detail-panel">
                      <h3 className="panel-heading text-secondary"><ShieldAlert size={16}/> Captured Error Logs</h3>
                      <pre className="code-block">{ev.logs_snippet}</pre>
                    </div>
                  )}
                  
                  {idx === selectedRun.events.length - 1 && ev.execution_logs && ev.execution_logs.length > 0 && (
                    <div className="detail-panel">
                      <h3 className="panel-heading text-secondary"><TerminalIcon size={16}/> Background Agent Trace</h3>
                      <Terminal lines={ev.execution_logs} height={300} />
                    </div>
                  )}
                </div>
              </div>
            ))}

            {/* Final Conclusion Node */}
            {selectedRun.latest_event.state === 'success' && (
              <div className="timeline-event" style={{ position: 'relative', paddingLeft: 24, paddingBottom: 16 }}>
                 <div style={{ position: 'absolute', left: -7, top: 0, width: 12, height: 12, borderRadius: '50%', background: 'var(--status-success)', border: '2px solid var(--bg-dark)', zIndex: 10 }} />
                 <div style={{ padding: '16px 20px', background: 'rgba(16, 185, 129, 0.1)', borderRadius: 8, border: '1px solid rgba(16, 185, 129, 0.3)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                       <CheckCircle size={20} style={{ color: 'var(--status-success)' }} />
                       <div>
                         <h4 style={{ margin: 0, color: 'var(--status-success)' }}>DAG Run Recovered & Succeeded</h4>
                         <p style={{ margin: '4px 0 0 0', fontSize: 13, color: 'var(--text-secondary)' }}>The AI-triggered retry successfully resolved the issue and the Pipeline finished execution.</p>
                       </div>
                    </div>
                 </div>
              </div>
            )}

            {selectedRun.latest_event.dag_paused && (
              <div className="timeline-event" style={{ position: 'relative', paddingLeft: 24, paddingBottom: 16 }}>
                 <div style={{ position: 'absolute', left: -7, top: 0, width: 12, height: 12, borderRadius: '50%', background: 'var(--status-warning)', border: '2px solid var(--bg-dark)', zIndex: 10 }} />
                 <div style={{ padding: '16px 20px', background: 'rgba(234, 179, 8, 0.1)', borderRadius: 8, border: '1px solid rgba(234, 179, 8, 0.3)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                       <AlertTriangle size={20} style={{ color: 'var(--status-warning)' }} />
                       <div>
                         <h4 style={{ margin: 0, color: 'var(--status-warning)' }}>DAG Execution Paused</h4>
                         <p style={{ margin: '4px 0 0 0', fontSize: 13, color: 'var(--text-secondary)' }}>The agent actively paused the Airflow DAG schedule to prevent an incident storm while the engineering team investigates.</p>
                       </div>
                    </div>
                 </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Shared Chat Widget */}
      <div className={`chat-widget ${chatOpen ? 'open' : ''} ${chatMaximized ? 'maximized' : ''}`}>
        <button className="chat-toggle" onClick={() => setChatOpen(!chatOpen)}>
          <MessageSquare size={18} />
          {chatOpen ? 'SRE AI Assistant' : 'Ask AI'}
          {chatOpen && (
             <div className="chat-actions" style={{position: 'absolute', right: 20, display: 'flex', gap: 10}}>
               <button type="button" onClick={(e) => { e.stopPropagation(); setChatMaximized(!chatMaximized); }} style={{background:'none',border:'none',color:'#fff',cursor:'pointer'}}>
                 {chatMaximized ? <Minimize2 size={16}/> : <Maximize2 size={16}/>}
               </button>
             </div>
          )}
        </button>
        {chatOpen && (
          <div className="chat-window">
            <div className="chat-log">
              {chatLog.map((m, i) => (
                <div key={i} className={`chat-msg ${m.role}`}>
                  {m.role === 'sys' ? (
                     <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.text}</ReactMarkdown>
                  ) : m.text}
                </div>
              ))}
              {isChatting && <div className="chat-msg sys typing">Agent is typing...</div>}
              <div ref={chatEndRef} />
            </div>
            <form onSubmit={handleChat} className="chat-form">
              <input 
                type="text" 
                value={chatInput} 
                onChange={(e) => setChatInput(e.target.value)}
                placeholder="Ask about active incidents..." 
                disabled={isChatting}
              />
              <button type="submit" disabled={isChatting}>Send</button>
            </form>
          </div>
        )}
      </div>
      {/* Runbooks Modal */}
      {showRunbooksModal && (
        <div className="modal-overlay" onClick={() => setShowRunbooksModal(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: 600 }}>
            <div className="modal-header">
              <h3 style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <Database size={18} color="var(--status-warning)" />
                Vectorized Runbooks
              </h3>
              <button className="btn-icon" onClick={() => setShowRunbooksModal(false)}><X size={18}/></button>
            </div>
            <div className="modal-body">
              <p style={{ color: 'var(--text-secondary)', marginBottom: 20, fontSize: 14 }}>
                The following troubleshooting guides have been ingested from Confluence directly into Oracle 23ai AI Vector Search. The AI agent uses these immediately when zero-shot remediation is insufficient.
              </p>
              
              {(!state.indexed_runbooks_list || state.indexed_runbooks_list.length === 0) ? (
                <div className="empty-state">
                  <FileText size={48} opacity={0.3} />
                  <p>No runbooks have been indexed yet.</p>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10, maxHeight: 400, overflowY: 'auto' }}>
                  {state.indexed_runbooks_list.map((filename: string, idx: number) => (
                    <div key={idx} style={{ 
                      display: 'flex', alignItems: 'center', gap: 12, 
                      padding: 16, background: 'var(--panel-hover)', 
                      border: '1px solid var(--panel-border)', borderRadius: 8 
                    }}>
                      <div style={{ padding: 8, background: 'rgba(59, 130, 246, 0.1)', color: 'var(--accent-blue)', borderRadius: 6 }}>
                        <FileText size={16} />
                      </div>
                      <span style={{ fontWeight: 500, fontSize: 14, color: 'var(--text-primary)' }}>
                        {filename}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
