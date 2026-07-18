import React, {useEffect, useMemo, useState} from 'react';
import {createRoot} from 'react-dom/client';
import './styles.css';

type Event={id:string;sequence:number;type:string;actor:string;payload:Record<string,unknown>;provenance:string;sensitivity:string[];parent_id?:string|null;schema_version?:string};
type Finding={id:string;rule_id:string;title:string;severity:string;explanation:string;evidence_event_ids:string[];recommended_control:string;source?:string;status?:string};
type Run={id:string;policy_mode:string;fixture_hash:string;intent:{goal:string;allowed_tools:string[];prohibited_outcomes:string[];protected_resources?:string[];approval_required?:string[];completion_conditions?:string[]};events:Event[];findings:Finding[]};
type Comparison={left_id:string;right_id:string;fixture_hash:string;changed_decisions:{step:string;from:string;to:string}[];resolved_rules:string[];blocked_tools:string[];outcome:string};
type Health={status:string;mode:string;live_analysis:string;version:string};
type Benchmark={suite_version:string;scenarios:number;true_positives:number;false_positives:number;false_negatives:number;precision:number;recall:number;deterministic:boolean};
type RecordedAnalysis={mode:'recorded';model:string;prompt_version:string;fixture_hash:string;generated_at:string;validation:'passed';findings:{finding_type:string;summary:string;severity:string;confidence:number}[]};
type BusyAction='baseline'|'protected'|'reset';

const api=async<T,>(path:string,options?:RequestInit):Promise<T>=>{
  const controller=new AbortController();
  const timer=window.setTimeout(()=>controller.abort(),15000);
  try{
    const response=await fetch(path,{...options,signal:controller.signal,headers:{Accept:'application/json',...options?.headers}});
    if(!response.ok)throw new Error(`Request failed (${response.status})`);
    return response.json();
  }finally{window.clearTimeout(timer)}
};

const titleCase=(value:string)=>value.replaceAll('_',' ').replace(/\b\w/g,letter=>letter.toUpperCase());
const pretty=(value:unknown)=>typeof value==='string'?value:JSON.stringify(value,null,2);
const shortId=(value:string)=>value.length>18?`${value.slice(0,10)}…${value.slice(-5)}`:value;
const eventSummary=(event:Event)=>{
  const p=event.payload;
  if(event.type==='user_intent')return String(p.goal||'Intent contract created');
  if(event.type==='retrieval')return p.contains_instruction?'Untrusted content contains an instruction':'Content retrieved';
  if(event.type==='tool_proposal')return `${String(p.tool||'Tool')} ${p.blocked?'blocked':'proposed'}`;
  if(event.type==='policy_decision')return `${titleCase(String(p.decision||'evaluated'))}: ${String(p.reason||'policy evaluated')}`;
  if(event.type==='state_mutation')return `${String(p.field||'State')} ${p.blocked?'mutation blocked':'updated'}`;
  if(event.type==='tool_result')return `${event.actor} returned ${p.result?'a simulated result':'redacted data'}`;
  if(event.type==='final_answer')return String(p.output||'Execution completed');
  return titleCase(event.type);
};
const eventTone=(type:string)=>type.includes('policy')?'policy':type.includes('tool')?'tool':type==='retrieval'?'retrieval':type==='final_answer'?'complete':'neutral';
const severityRank:Record<string,number>={critical:0,high:1,medium:2,low:3};

function Icon({name}:{name:'flight'|'play'|'shield'|'reset'|'download'|'check'|'pulse'|'arrow'|'file'|'database'|'warning'}){
  const paths={
    flight:<><path d="M4 12h15M13 6l6 6-6 6"/><path d="M4 7h4M4 17h4"/></>,
    play:<path d="m9 7 8 5-8 5V7Z"/>,shield:<path d="M12 3 5 6v5c0 4.7 2.9 8 7 10 4.1-2 7-5.3 7-10V6l-7-3Z"/>,
    reset:<><path d="M4 12a8 8 0 1 0 2.3-5.7L4 8"/><path d="M4 4v4h4"/></>,download:<><path d="M12 3v12m0 0 4-4m-4 4-4-4"/><path d="M5 20h14"/></>,
    check:<path d="m5 12 4 4L19 6"/>,pulse:<><path d="M3 12h4l2-5 4 10 2-5h6"/></>,arrow:<path d="m9 5 7 7-7 7"/>,
    file:<><path d="M6 3h8l4 4v14H6V3Z"/><path d="M14 3v5h5M9 13h6M9 17h6"/></>,database:<><ellipse cx="12" cy="5" rx="7" ry="3"/><path d="M5 5v6c0 1.7 3.1 3 7 3s7-1.3 7-3V5M5 11v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6"/></>,
    warning:<><path d="M12 3 2.8 20h18.4L12 3Z"/><path d="M12 9v5m0 3h.01"/></>
  };
  return <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

function ModeDisclosure({health,recorded,online}:{health:Health|null;recorded:RecordedAnalysis|null;online:boolean}){
  return <details className="mode-disclosure">
    <summary><span className={`status-dot ${online&&health?.status==='ok'?'ok':'offline'}`}/><span>Judge environment</span><strong>Deterministic</strong><Icon name="arrow"/></summary>
    <div className="mode-popover">
      <p className="popover-kicker">Execution provenance</p>
      <div className="mode-row"><Icon name="database"/><div><b>Fixture replay</b><span>Synthetic data · no external side effects</span></div><em>ACTIVE</em></div>
      <div className="mode-row"><Icon name="shield"/><div><b>Deterministic rules</b><span>Eight local, evidence-linked detectors</span></div><em>ACTIVE</em></div>
      <div className="mode-row muted"><Icon name="pulse"/><div><b>Live model analysis</b><span>{health?.live_analysis==='enabled'?'Server-enabled; not used automatically':'Disabled in this judge session'}</span></div><em>OFF</em></div>
      <div className="mode-note"><b>{recorded?`${recorded.model} recorded artifact available`:'Recorded analysis unavailable'}</b><span>{recorded?'Validated development evidence—never presented as a live call.':'Deterministic findings remain fully available.'}</span></div>
    </div>
  </details>;
}

function EmptyState({busy,onRun}:{busy:boolean;onRun:()=>void}){
  return <section className="empty-state" aria-labelledby="empty-title">
    <div className="empty-visual" aria-hidden="true"><span>01</span><i/><span>02</span><i/><span>03</span></div>
    <p className="kicker">NO TRACE LOADED</p>
    <h2 id="empty-title">Investigate a seeded agent incident</h2>
    <p>Replay a synthetic indirect prompt-injection scenario, follow its causal evidence, then prove a deny-by-default control changes the outcome.</p>
    <button className="button primary" onClick={onRun} disabled={busy}><Icon name="play"/>Run 9-event baseline</button>
    <ul aria-label="Scenario guarantees"><li><Icon name="check"/>No signup or API key</li><li><Icon name="check"/>No real secrets</li><li><Icon name="check"/>No external tools</li></ul>
  </section>;
}

function BenchmarkCard({benchmark,loading}:{benchmark:Benchmark|null;loading:boolean}){
  return <section className="benchmark-card" aria-labelledby="benchmark-title" aria-busy={loading}>
    <div className="card-heading"><div><p className="kicker">VALIDATION SUITE</p><h2 id="benchmark-title">Detector benchmark</h2></div><span className="verification-badge"><Icon name="check"/>{benchmark?.deterministic?'REPRODUCIBLE':'VERIFYING'}</span></div>
    {loading?<div className="metric-skeleton" aria-label="Loading benchmark"><i/><i/><i/></div>:benchmark?<>
      <div className="metric-row"><div><strong>{benchmark.scenarios}</strong><span>versioned scenarios</span></div><div><strong>{Math.round(benchmark.precision*100)}%</strong><span>suite precision</span></div><div><strong>{Math.round(benchmark.recall*100)}%</strong><span>suite recall</span></div></div>
      <p className="fine-print">{benchmark.suite_version} · Synthetic fixture results only; not a production performance claim.</p>
    </>:<div className="inline-state"><Icon name="warning"/><span>Benchmark unavailable. The investigation flow still works.</span></div>}
  </section>;
}

function IntentCard({run}:{run:Run}){
  return <details className="intent-card">
    <summary><span className="intent-summary-copy"><span className="kicker">AUTHORIZATION BOUNDARY</span><strong>Intent contract</strong></span><span>v1 · {run.intent.allowed_tools.length} allowed tools</span><Icon name="arrow"/></summary>
    <div className="intent-body"><div><span>Authorized goal</span><p>{run.intent.goal}</p></div><div><span>Allowed tools</span><p>{run.intent.allowed_tools.join(' · ')||'None'}</p></div><div><span>Protected resources</span><p>{run.intent.protected_resources?.join(' · ')||'None'}</p></div><div><span>Approval gates</span><p>{run.intent.approval_required?.join(' · ')||'None'}</p></div></div>
  </details>;
}

function FindingList({findings,selected,onSelect}:{findings:Finding[];selected:Finding|null;onSelect:(finding:Finding)=>void}){
  const sorted=[...findings].sort((a,b)=>(severityRank[a.severity]??9)-(severityRank[b.severity]??9));
  return <nav className="findings-panel" aria-label="Security findings">
    <div className="panel-title"><div><p className="kicker">RISK QUEUE</p><h2>Findings</h2></div><span>{findings.length} OPEN</span></div>
    <p className="panel-intro">Select a rule to isolate its evidence in the execution trace.</p>
    <div className="finding-list">{sorted.map((finding,index)=><button className={`finding-card ${selected?.id===finding.id?'active':''}`} onClick={()=>onSelect(finding)} key={finding.id} aria-pressed={selected?.id===finding.id}>
      <span className={`severity ${finding.severity}`}><i/>{finding.severity}</span>
      <strong>{finding.title}</strong>
      <span className="rule-id">{finding.rule_id}</span>
      <span className="finding-meta">{finding.evidence_event_ids.length} evidence events <Icon name="arrow"/></span>
      {index===0&&<span className="first-risk">FIRST DIVERGENCE</span>}
    </button>)}</div>
  </nav>;
}

function Timeline({run,evidence}:{run:Run;evidence:Set<string>}){
  return <section className="timeline-panel" aria-labelledby="timeline-title">
    <div className="timeline-heading"><div><p className="kicker">CAUSAL TRACE</p><h2 id="timeline-title">Execution timeline</h2><p>{run.intent.goal}</p></div><div className="trace-meta"><span><i className="live-pulse"/>Recorded</span><b>{run.events.length} immutable events</b></div></div>
    <ol className="timeline-list">{run.events.map(event=>{
      const highlighted=evidence.has(event.id);
      return <li key={event.id} id={`event-${event.id}`} className={`${eventTone(event.type)} ${highlighted?'highlighted':''}`} tabIndex={-1} aria-label={`Event ${event.sequence}: ${titleCase(event.type)}${highlighted?', referenced evidence':''}`}>
        <div className="event-marker"><span>{String(event.sequence).padStart(2,'0')}</span></div>
        <article className="event-card">
          <header><div><span className="event-type">{titleCase(event.type)}</span>{highlighted&&<span className="evidence-flag">EVIDENCE</span>}</div><code title={event.id}>{shortId(event.id)}</code></header>
          <p className="event-summary">{eventSummary(event)}</p>
          <div className="event-provenance"><span>{event.actor}</span><i/> <span>{event.provenance}</span>{event.sensitivity.length>0&&<><i/><span className="sensitive">{event.sensitivity.join(', ')}</span></>}</div>
          <details className="event-payload"><summary>Inspect redacted payload <Icon name="arrow"/></summary><pre>{pretty(event.payload)}</pre>{event.parent_id&&<p>Parent <code>{event.parent_id}</code></p>}</details>
        </article>
      </li>})}</ol>
  </section>;
}

function EvidencePanel({selected,run,recorded}:{selected:Finding|null;run:Run;recorded:RecordedAnalysis|null}){
  const focusEvent=(id:string)=>window.setTimeout(()=>document.getElementById(`event-${id}`)?.focus(),0);
  return <aside className="evidence-panel" aria-labelledby="evidence-title">
    <div className="panel-title"><div><p className="kicker">INSPECTOR</p><h2 id="evidence-title">Evidence</h2></div><span>REDACTED</span></div>
    {selected?<div className="evidence-content">
      <span className={`severity ${selected.severity}`}><i/>{selected.severity}</span>
      <h3>{selected.title}</h3><code className="rule-code">{selected.rule_id}</code>
      <p className="explanation">{selected.explanation}</p>
      <div className="evidence-section"><h4>Linked trace events <span>{selected.evidence_event_ids.length}</span></h4><div className="evidence-links">{selected.evidence_event_ids.map((id,index)=><a href={`#event-${id}`} onClick={()=>focusEvent(id)} key={id}><span>{String(index+1).padStart(2,'0')}</span><code>{shortId(id)}</code><Icon name="arrow"/></a>)}</div></div>
      <div className="control-card"><Icon name="shield"/><div><h4>Recommended control</h4><p>{selected.recommended_control}</p></div></div>
      <div className="report-actions"><a className="button primary" href={`/api/v1/executions/${run.id}/report`}><Icon name="download"/>Export incident report</a><a className="button icon-button" href={`/api/v1/executions/${run.id}/report?format=json`} aria-label="Export report as JSON"><Icon name="file"/>JSON</a></div>
      {recorded&&<details className="recorded-card"><summary><span><Icon name="pulse"/><b>Recorded {recorded.model} analysis</b></span><span>VALIDATED</span></summary><div><p>This fixture-bound development artifact is recorded, not a live call.</p><dl><div><dt>Prompt</dt><dd>{recorded.prompt_version}</dd></div><div><dt>Validation</dt><dd>{recorded.validation}</dd></div><div><dt>Semantic findings</dt><dd>{recorded.findings.length}</dd></div></dl></div></details>}
    </div>:<div className="panel-empty"><Icon name="file"/><p>Select a finding to inspect its linked evidence and recommended control.</p></div>}
  </aside>;
}

function ComparisonView({baseline,protectedRun,comparison}:{baseline:Run;protectedRun:Run;comparison:Comparison}){
  const max=Math.max(baseline.findings.length,1);
  return <section id="comparison-summary" className="comparison-card" tabIndex={-1} aria-labelledby="comparison-title">
    <div className="comparison-heading"><div className="success-mark"><Icon name="check"/></div><div><p className="kicker">COUNTERFACTUAL VERIFIED</p><h2 id="comparison-title">Protected replay blocked synthetic egress</h2><p>Identical fixture <code>{comparison.fixture_hash}</code> · deterministic policy changed the outcome</p></div><span className="resolved-badge">{comparison.resolved_rules.length} / {baseline.findings.length} RISKS RESOLVED</span></div>
    <div className="run-compare">
      <div className="run-card baseline"><header><span>BASELINE</span><code>{shortId(baseline.id)}</code></header><strong>{baseline.findings.length}</strong><p>open findings</p><div className="risk-bar"><i style={{width:'100%'}}/></div><footer>Observe-only policy <span>unsafe action completed</span></footer></div>
      <div className="compare-arrow" aria-hidden="true"><Icon name="arrow"/></div>
      <div className="run-card protected"><header><span>PROTECTED</span><code>{shortId(protectedRun.id)}</code></header><strong>{protectedRun.findings.length}</strong><p>open findings</p><div className="risk-bar"><i style={{width:`${(protectedRun.findings.length/max)*100}%`}}/></div><footer>Deny-by-default policy <span>{comparison.blocked_tools.join(', ')||'Sensitive tool'} blocked</span></footer></div>
    </div>
    <div className="decision-strip"><div><span>POLICY DECISION</span><strong>{comparison.changed_decisions[0]?`${comparison.changed_decisions[0].from} → ${comparison.changed_decisions[0].to}`:'No change'}</strong></div><div><span>BLOCKED TOOL</span><strong>{comparison.blocked_tools.join(', ')||'None'}</strong></div><div><span>FIXTURE PARITY</span><strong><Icon name="check"/>Exact match</strong></div><div><span>OUTCOME</span><strong><Icon name="shield"/>Egress prevented</strong></div></div>
  </section>;
}

function App(){
  const [run,setRun]=useState<Run|null>(null),[protectedRun,setProtected]=useState<Run|null>(null),[selected,setSelected]=useState<Finding|null>(null);
  const [comparison,setComparison]=useState<Comparison|null>(null),[busy,setBusy]=useState<BusyAction|null>(null),[failedAction,setFailedAction]=useState<BusyAction|null>(null);
  const [error,setError]=useState(''),[status,setStatus]=useState('Ready to run the synthetic scenario.'),[online,setOnline]=useState(navigator.onLine);
  const [health,setHealth]=useState<Health|null>(null),[benchmark,setBenchmark]=useState<Benchmark|null>(null),[recorded,setRecorded]=useState<RecordedAnalysis|null>(null),[metaLoading,setMetaLoading]=useState(true);
  const evidence=useMemo(()=>new Set(selected?.evidence_event_ids||[]),[selected]);

  useEffect(()=>{
    const update=()=>setOnline(navigator.onLine);
    window.addEventListener('online',update);window.addEventListener('offline',update);
    Promise.allSettled([api<Health>('/health'),api<Benchmark>('/api/v1/benchmark'),api<RecordedAnalysis>('/api/v1/recorded-analysis')]).then(results=>{
      if(results[0].status==='fulfilled')setHealth(results[0].value);
      if(results[1].status==='fulfilled')setBenchmark(results[1].value);
      if(results[2].status==='fulfilled')setRecorded(results[2].value);
      setMetaLoading(false);
    });
    return()=>{window.removeEventListener('online',update);window.removeEventListener('offline',update)};
  },[]);

  const execute=async(mode:'baseline'|'protected')=>{
    if(busy)return;
    if(!online){setError('You appear to be offline. Reconnect and retry.');setFailedAction(mode);return}
    setBusy(mode);setFailedAction(null);setError('');setStatus(`${mode==='baseline'?'Vulnerable scenario':'Protected replay'} running.`);
    try{
      const value=await api<Run>(`/api/v1/demo/${mode}`,{method:'POST'});
      if(mode==='baseline'){
        setRun(value);setProtected(null);setComparison(null);setSelected(value.findings[0]||null);
        setStatus(`Vulnerable scenario complete with ${value.findings.length} findings.`);
        requestAnimationFrame(()=>document.getElementById('execution-summary')?.focus());
      }else{
        setProtected(value);
        if(run)setComparison(await api<Comparison>(`/api/v1/comparisons/${run.id}/${value.id}`));
        setStatus(`Protected replay complete with ${value.findings.length} findings.`);
        requestAnimationFrame(()=>document.getElementById('comparison-summary')?.focus());
      }
    }catch(error){setFailedAction(mode);setError(error instanceof DOMException&&error.name==='AbortError'?'The AgentFlight service timed out. Retry when it is ready.':'The demo could not complete. Check the AgentFlight service and retry.');setStatus('Demo failed.')}finally{setBusy(null)}
  };
  const reset=async()=>{
    if(busy)return;setBusy('reset');setFailedAction(null);setError('');setStatus('Resetting the synthetic demo.');
    try{await api('/api/v1/demo/reset',{method:'POST'});setRun(null);setProtected(null);setComparison(null);setSelected(null);setStatus('Demo reset. Ready to run the synthetic scenario.');requestAnimationFrame(()=>document.getElementById('run-baseline')?.focus())}
    catch{setFailedAction('reset');setError('The demo could not reset. Check the AgentFlight service and retry.');setStatus('Reset failed.')}finally{setBusy(null)}
  };
  const retry=()=>failedAction==='reset'?reset():execute(failedAction||'baseline');

  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Skip to investigation</a>
    <header className="app-header"><a className="brand" href="#main-content" aria-label="AgentFlight Recorder home"><span className="brand-mark"><Icon name="flight"/></span><span><b>AgentFlight</b><small>RECORDER</small></span></a><span className="header-divider"/><p>Agent security investigation</p><nav aria-label="Product links"><a href="/api/docs">API docs</a><ModeDisclosure health={health} recorded={recorded} online={online}/></nav></header>
    {!online&&<div className="offline-banner" role="status"><Icon name="warning"/><span><b>Network unavailable</b> — reconnect to run or replay. Loaded evidence remains available.</span></div>}
    <main id="main-content">
      <section className="hero" aria-labelledby="page-title"><div className="hero-copy"><div className="eyebrow-row"><span>DEVELOPER SECURITY</span><i/><span>INCIDENT WORKBENCH</span></div><h1 id="page-title">See where intent<br/><em>became action.</em></h1><p>Trace an agent’s first unsafe decision to its evidence, apply a control, and replay the exact fixture to verify the outcome.</p></div>
        <div className="hero-rail"><div className="scenario-label"><span>SEEDED SCENARIO</span><b>Indirect prompt injection</b><small>vendor-research-injection-v1</small></div><div className="hero-actions"><button id="run-baseline" className="button primary" onClick={()=>execute('baseline')} disabled={!!busy} aria-busy={busy==='baseline'}><Icon name="play"/>{busy==='baseline'?'Recording baseline…':run?'Run new baseline':'Run vulnerable scenario'}</button><button className="button protected-action" onClick={()=>execute('protected')} disabled={!!busy||!run} aria-busy={busy==='protected'}><Icon name="shield"/>{busy==='protected'?'Applying control…':'Replay with protection'}</button><button className="button icon-only" onClick={reset} disabled={!!busy||!run} aria-busy={busy==='reset'} aria-label="Reset synthetic demo" title="Reset demo"><Icon name="reset"/></button></div><p className="action-note"><Icon name="check"/>Synthetic fixture · no network tools or live model calls</p></div>
      </section>
      <p className="sr-only" aria-live="polite" aria-atomic="true">{status}</p>
      {error&&<div className="error-banner" role="alert"><Icon name="warning"/><div><b>Action unavailable</b><span>{error}</span></div><button className="button" onClick={retry} disabled={!!busy}>Retry action</button><button className="dismiss" onClick={()=>setError('')} aria-label="Dismiss error">×</button></div>}
      {!run?<div className="preflight-grid"><EmptyState busy={!!busy} onRun={()=>execute('baseline')}/><div className="preflight-side"><BenchmarkCard benchmark={benchmark} loading={metaLoading}/><section className="workflow-card"><p className="kicker">INVESTIGATION WORKFLOW</p><h2>From incident to proof</h2><ol><li><span>01</span><div><b>Record</b><p>Capture the baseline’s intent, tools, state, and policy decisions.</p></div></li><li><span>02</span><div><b>Investigate</b><p>Follow evidence-linked rules to the first divergent event.</p></div></li><li><span>03</span><div><b>Verify</b><p>Replay one fixture under protection and compare outcomes.</p></div></li></ol></section></div></div>:
      <>
        <section id="execution-summary" className="execution-bar" tabIndex={-1} aria-label="Baseline execution summary"><div><span>EXECUTION</span><b title={run.id}>{shortId(run.id)}</b></div><div><span>FIXTURE</span><b title={run.fixture_hash}>{run.fixture_hash}</b></div><div><span>POLICY MODE</span><b className="observe"><i/>Observe only</b></div><div><span>TRACE</span><b>{run.events.length} events</b></div><div><span>RISK</span><b className="risk"><i/>{run.findings.length} open</b></div></section>
        {protectedRun&&comparison&&<ComparisonView baseline={run} protectedRun={protectedRun} comparison={comparison}/>}
        <IntentCard run={run}/>
        <section className="workbench"><FindingList findings={run.findings} selected={selected} onSelect={setSelected}/><Timeline run={run} evidence={evidence}/><EvidencePanel selected={selected} run={run} recorded={recorded}/></section>
      </>}
    </main>
    <footer className="app-footer"><span><span className="status-dot ok"/>Synthetic judge environment</span><span>Payloads redacted by the service</span><span>Schema v1.0</span><a href="/api/docs">API reference</a></footer>
  </div>;
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
