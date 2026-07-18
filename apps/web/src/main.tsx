import React, {useEffect, useMemo, useState} from 'react';
import {createRoot} from 'react-dom/client';
import './styles.css';

type Event={id:string;sequence:number;type:string;actor:string;payload:Record<string,unknown>;provenance:string;sensitivity:string[];parent_id?:string|null;schema_version?:string};
type Finding={id:string;rule_id:string;title:string;severity:string;explanation:string;evidence_event_ids:string[];recommended_control:string;source?:string;status?:string};
type Run={id:string;policy_mode:string;fixture_hash:string;intent:{goal:string;allowed_tools:string[];prohibited_outcomes:string[];protected_resources?:string[];approval_required?:string[];completion_conditions?:string[]};events:Event[];findings:Finding[]};
type PromotionGate={verdict:string;reason:string;restored_clause_ids:string[];regressions:string[]};
type Comparison={left_id:string;right_id:string;fixture_hash:string;changed_decisions:{step:string;from:string;to:string}[];resolved_rules:string[];blocked_tools:string[];outcome:string;promotion_gate?:PromotionGate};
type IntentClause={id:string;kind?:string;clause_type?:string;statement?:string;text?:string;status?:string;critical?:boolean};
type IntentBinding={clause_id:string;event_id?:string;event_ids?:string[];status?:string;relationship?:string};
type DecisionRecord={event_id:string;action?:string;decision:string;summary?:string;reason?:string;clause_ids?:string[];bound_clause_ids?:string[];evidence_event_ids?:string[];alternatives_considered?:string[];confidence?:number;confidence_semantics?:string};
type ConsequentialAction=string|{event_id?:string;action?:string;reason?:string};
type IntentCausalRecord={execution_id:string;clauses:IntentClause[];bindings:IntentBinding[];causal_chain_event_ids:string[];decision_records:DecisionRecord[];first_divergence_event_id:string|null;first_divergence_reason:string|null;intent_coverage:number;coverage?:{verified_coverage_ratio:number;declaration_coverage_ratio:number;consequential_action_coverage_ratio:number;verified_clauses:number;total_clauses:number};divergence_frontier?:{event_id:string;sequence:number}[];unbound_consequential_actions:ConsequentialAction[]};
type Health={status:string;mode:string;live_analysis:string;version:string};
type Benchmark={suite_version:string;scenarios:number;true_positives:number;false_positives:number;false_negatives:number;precision:number;recall:number;specificity:number;deterministic:boolean;evidence_scope?:string;confidence_intervals?:{precision:{lower:number};recall:{lower:number};specificity:{lower:number}}};
type AssuranceSuite={eligible:boolean;verdict:string;scope:string;production_safety_certification:boolean;cases:number;distinct_fixtures:number;scenario_families:number;channels:number;pass_interval:{lower:number;upper:number;estimate:number;method?:string};provenance:{artifact_digest:string;runner_identity:string;attestation_algorithm:string;source_revision?:string;detector_version?:string;policy_version?:string};checks?:{name:string;passed:boolean;summary:string}[];limitations:string[]};
type SemanticAnalysis={mode:'live'|'recorded';model:string;requested_model?:string|null;reasoning_effort?:'medium';prompt_version:string;fixture_hash:string;response_id:string;generated_at:string;validation:'passed';findings:{finding_type:string;summary:string;reasoning_summary?:string;severity:string;confidence:number;recommended_control?:string}[]};
type RecordedAnalysis=SemanticAnalysis&{mode:'recorded'};
type AuthorizationDecision={event_id:string;decision_id:string;outcome:string;enforcement:string;reason_code:string;reason:string;tool:string;action:string;resource_type:string;data_class:string;destination:string;effects:string[];matched_policy_ids:string[];obligations:string[];permit_issued:boolean};
type AuthorizationRecord={execution_id:string;enforcement_model:string;ontology_version:string;ontology_digest:string;policy_version:string;grant_id:string|null;grant_digest:string|null;decisions:AuthorizationDecision[];allowed:number;denied:number;approval_required:number;complete_mediation:boolean;limitations:string[]};
type BusyAction='baseline'|'protected'|'reset';

const api=async<T,>(path:string,options?:RequestInit,timeoutMs=15000):Promise<T>=>{
  const controller=new AbortController();
  const timer=window.setTimeout(()=>controller.abort(),timeoutMs);
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
  if(event.type==='plan')return String(p.summary||'Application plan recorded');
  if(event.type==='decision')return String(p.summary||p.decision||'Application decision recorded');
  if(event.type==='tool_proposal')return `${String(p.tool||'Tool')} ${p.blocked?'blocked':'proposed'}`;
  if(event.type==='policy_decision')return `${titleCase(String(p.decision||'evaluated'))}: ${String(p.reason||'policy evaluated')}`;
  if(event.type==='state_mutation')return `${String(p.field||'State')} ${p.blocked?'mutation blocked':'updated'}`;
  if(event.type==='tool_result')return `${event.actor} returned ${p.result?'a simulated result':'redacted data'}`;
  if(event.type==='final_answer')return String(p.output||'Execution completed');
  return titleCase(event.type);
};
const eventTone=(type:string)=>type.includes('policy')||type==='decision'?'policy':type.includes('tool')?'tool':type==='retrieval'?'retrieval':type==='final_answer'?'complete':'neutral';
const severityRank:Record<string,number>={critical:0,high:1,medium:2,low:3};

function Icon({name}:{name:'gate'|'play'|'shield'|'reset'|'download'|'check'|'pulse'|'arrow'|'file'|'database'|'warning'}){
  const paths={
    gate:<><path d="M5 20V5l7-2 7 2v15"/><path d="M9 20v-7h6v7M3 20h18"/></>,
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
      <div className="mode-row muted"><Icon name="pulse"/><div><b>Live model analysis</b><span>{health?.live_analysis==='byok_required'?'Ready for an ephemeral judge-supplied key':health?.live_analysis==='server_configured'?'Self-hosted server key configured':'Disabled in this judge session'}</span></div><em>OPT-IN</em></div>
      <div className="mode-note"><b>{recorded?`${recorded.model} recorded artifact available`:'Recorded analysis unavailable'}</b><span>{recorded?'Validated development evidence—never presented as a live call.':'Deterministic findings remain fully available.'}</span></div>
    </div>
  </details>;
}

function EmptyState({busy,onRun}:{busy:boolean;onRun:()=>void}){
  return <section className="empty-state" aria-labelledby="empty-title">
    <div className="empty-visual" aria-hidden="true"><span>01</span><i/><span>02</span><i/><span>03</span></div>
    <p className="kicker">NO TRACE LOADED</p>
    <h2 id="empty-title">Find the earliest detected intent divergence</h2>
    <p>Build an Intent Causal Record for a seeded prompt-injection incident, locate the causal-minimal violation, then test whether a control restores alignment.</p>
    <button className="button primary" onClick={onRun} disabled={busy}><Icon name="play"/>Run 13-event baseline</button>
    <ul aria-label="Scenario guarantees"><li><Icon name="check"/>No signup or API key</li><li><Icon name="check"/>No real secrets</li><li><Icon name="check"/>No external tools</li></ul>
  </section>;
}

function BenchmarkCard({benchmark,loading}:{benchmark:Benchmark|null;loading:boolean}){
  return <section className="benchmark-card" aria-labelledby="benchmark-title" aria-busy={loading}>
    <div className="card-heading"><div><p className="kicker">VALIDATION SUITE</p><h2 id="benchmark-title">Detector benchmark</h2></div><span className="verification-badge"><Icon name="check"/>{benchmark?.deterministic?'REPRODUCIBLE':'VERIFYING'}</span></div>
    {loading?<div className="metric-skeleton" aria-label="Loading benchmark"><i/><i/><i/></div>:benchmark?<>
      <div className="metric-row"><div><strong>{benchmark.scenarios}</strong><span>versioned scenarios</span></div><div><strong>{Math.round(benchmark.precision*100)}%</strong><span>precision · 95% lower {Math.round((benchmark.confidence_intervals?.precision.lower||0)*100)}%</span></div><div><strong>{Math.round(benchmark.recall*100)}%</strong><span>recall · 95% lower {Math.round((benchmark.confidence_intervals?.recall.lower||0)*100)}%</span></div></div>
      <p className="fine-print">{benchmark.suite_version} · Two-sided Wilson intervals · synthetic regression evidence only, not production validation.</p>
      <p className="fine-print">Every point estimate is paired with uncertainty. Results describe this synthetic regression corpus only.</p>
    </>:<div className="inline-state"><Icon name="warning"/><span>Benchmark unavailable. The investigation flow still works.</span></div>}
  </section>;
}

function AssuranceSuiteCard({suite,loading,compact=false}:{suite:AssuranceSuite|null;loading:boolean;compact?:boolean}){
  const lower=suite?Math.round(suite.pass_interval.lower*100):0;
  const checks=suite?.checks||[];
  const passed=checks.filter(check=>check.passed).length;
  return <section className={`assurance-suite-card ${compact?'compact':''} ${suite?.eligible?'eligible':'pending'}`} aria-labelledby={compact?'assurance-suite-title-compact':'assurance-suite-title'} aria-busy={loading}>
    <header className="assurance-suite-heading">
      <div className="assurance-mark"><Icon name={suite?.eligible?'check':'shield'}/></div>
      <div><p className="kicker">AUTHENTICATED RELEASE EVIDENCE</p><h2 id={compact?'assurance-suite-title-compact':'assurance-suite-title'}>{suite?.eligible?'Suite recommendation: eligible':'Suite evidence pending'}</h2><p>{suite?'Bound to this verifier artifact, policy version, runner, and fixture manifest.':'Configure runner attestation to unlock the multi-fixture release recommendation.'}</p></div>
      <span className="assurance-verdict">{suite?.eligible?'ELIGIBLE':'WITHHELD'}</span>
    </header>
    {loading?<div className="assurance-skeleton"><i/><i/><i/></div>:suite?<>
      <div className="assurance-metrics">
        <div><strong>{suite.distinct_fixtures}</strong><span>content-addressed fixtures</span></div>
        <div><strong>{suite.scenario_families}</strong><span>task families</span></div>
        <div><strong>{suite.channels}</strong><span>action channels</span></div>
        <div><strong>{passed}/{checks.length}</strong><span>gate checks passed</span></div>
      </div>
      <div className="confidence-panel">
        <div className="confidence-copy"><div><p className="kicker">UNCERTAINTY BOUND</p><h3>Observed 100% · 95% lower bound {lower}%</h3></div><span>Threshold 70%</span></div>
        <div className="confidence-track" role="img" aria-label={`Suite pass estimate 100 percent with a 95 percent lower bound of ${lower} percent and threshold of 70 percent`}><i className="threshold"/><i className="interval" style={{left:`${lower}%`}}/><i className="estimate"/></div>
        <div className="confidence-axis"><span>0</span><span>50</span><span>70 threshold</span><span>100%</span></div>
      </div>
      {!compact&&<div className="assurance-details">
        <div className="assurance-checks"><p className="kicker">GATE CONDITIONS</p><ul>{checks.map(check=><li key={check.name}><span><Icon name={check.passed?'check':'warning'}/></span><div><b>{titleCase(check.name)}</b><p>{check.summary}</p></div></li>)}</ul></div>
        <div className="attestation-panel"><p className="kicker">RUNNER ATTESTATION</p><dl><div><dt>Artifact</dt><dd title={suite.provenance.artifact_digest}>{shortId(suite.provenance.artifact_digest)}</dd></div><div><dt>Runner</dt><dd>{suite.provenance.runner_identity}</dd></div><div><dt>Signature</dt><dd>{suite.provenance.attestation_algorithm}</dd></div><div><dt>Detector</dt><dd>{suite.provenance.detector_version||'versioned'}</dd></div></dl><p><Icon name="database"/>Scoped evidence—not a general production-safety certificate.</p></div>
      </div>}
    </>:<div className="assurance-empty"><Icon name="warning"/><div><b>Attestation is not configured</b><p>The deterministic investigation remains available. Configure <code>CAUSALGATE_ATTESTATION_KEY</code> to produce signed suite evidence.</p></div></div>}
  </section>;
}

function IntentCard({run}:{run:Run}){
  return <details className="intent-card">
    <summary><span className="intent-summary-copy"><span className="kicker">AUTHORIZATION BOUNDARY</span><strong>Intent contract</strong></span><span>v1 · {run.intent.allowed_tools.length} allowed tools</span><Icon name="arrow"/></summary>
    <div className="intent-body"><div><span>Authorized goal</span><p>{run.intent.goal}</p></div><div><span>Allowed tools</span><p>{run.intent.allowed_tools.join(' · ')||'None'}</p></div><div><span>Protected resources</span><p>{run.intent.protected_resources?.join(' · ')||'None'}</p></div><div><span>Approval gates</span><p>{run.intent.approval_required?.join(' · ')||'None'}</p></div></div>
  </details>;
}

function AuthorizationCard({record,loading,error}:{record:AuthorizationRecord|null;loading:boolean;error:string}){
  if(loading)return <section className="authorization-card authorization-loading" aria-busy="true"><div className="intent-causal-skeleton"><i/><i/><i/></div><span>Verifying complete mediation and signed authority…</span></section>;
  if(error)return <section className="authorization-card authorization-error"><Icon name="warning"/><div><p className="kicker">INTENT-BASED ACCESS CONTROL</p><h2>Authorization evidence unavailable</h2><p>{error}</p></div></section>;
  if(!record)return null;
  return <section className="authorization-card" aria-labelledby="authorization-title">
    <header className="authorization-heading"><div><p className="kicker">INTENT-BASED ACCESS CONTROL</p><h2 id="authorization-title">Authority is an intersection, not a model opinion</h2><p>Every mapped tool proposal is normalized through the same deterministic policy path before execution.</p></div><span className={`mediation-seal ${record.complete_mediation?'complete':'incomplete'}`}><Icon name={record.complete_mediation?'check':'warning'}/>{record.complete_mediation?'COMPLETE MEDIATION':'REVIEW REQUIRED'}</span></header>
    <div className="authority-equation"><span>IDENTITY</span><b>∩</b><span>AGENT</span><b>∩</b><span>INTENT GRANT</span><b>∩</b><span>ORGANIZATION</span><b>∩</b><span>RUNTIME</span><strong>→ LEAST PRIVILEGE</strong></div>
    <div className="authorization-meta"><div><span>ONTOLOGY</span><b>{record.ontology_version}</b><code title={record.ontology_digest}>{shortId(record.ontology_digest)}</code></div><div><span>SIGNED GRANT</span><b>{record.grant_id?shortId(record.grant_id):'Unavailable'}</b><code title={record.grant_digest||''}>{record.grant_digest?shortId(record.grant_digest):'No digest'}</code></div><div><span>DECISIONS</span><b>{record.allowed} allow · {record.denied} deny</b><code>{record.approval_required} approval step-up</code></div></div>
    <div className="authorization-decisions" role="list" aria-label="Deterministic authorization decisions">{record.decisions.map(item=><article key={item.event_id} className={`authorization-decision ${item.outcome}`} role="listitem"><div className="decision-outcome"><span><Icon name={item.outcome==='allow'?'check':'shield'}/></span><div><b>{item.tool}</b><small>{item.action}</small></div><em>{item.outcome.toUpperCase()}</em></div><p>{item.reason}</p><dl><div><dt>Resource</dt><dd>{item.resource_type}</dd></div><div><dt>Data</dt><dd>{item.data_class}</dd></div><div><dt>Destination</dt><dd>{item.destination}</dd></div></dl><footer><code>{item.reason_code}</code><span className={item.enforcement}>{titleCase(item.enforcement)}</span>{item.permit_issued&&<span>Single-use permit</span>}</footer></article>)}</div>
    <p className="authorization-disclosure"><Icon name="database"/>The closed ontology, signed grant, exact-action approvals, short-lived permits, and replay ledger are deterministic. Natural-language or model output can only propose a candidate contract.</p>
  </section>;
}

function LiveJudgeAnalysis({health,analysis,busy,error,onAnalyze}:{health:Health|null;analysis:SemanticAnalysis|null;busy:boolean;error:string;onAnalyze:(apiKey:string)=>Promise<void>}){
  const [apiKey,setApiKey]=useState('');
  const enabled=health?.live_analysis==='byok_required'||health?.live_analysis==='server_configured';
  const serverConfigured=health?.live_analysis==='server_configured';
  const submit=async()=>{const supplied=apiKey;setApiKey('');await onAnalyze(supplied)};
  return <section className="live-judge-card" aria-labelledby="live-judge-title">
    <div className="live-judge-copy"><p className="kicker">OPTIONAL · BRING YOUR OWN KEY</p><h2 id="live-judge-title">GPT‑5.6 Sol, bounded by deterministic evidence</h2><p>Use medium reasoning to find semantic intent drift in a minimized, redacted trace. The result adds investigative evidence; it cannot authorize a tool or change the promotion gate.</p><div className="model-spec"><span>REQUESTED MODEL <b>gpt-5.6-sol</b></span><span>REASONING <b>medium</b></span><span>API <b>Responses</b></span></div></div>
    <div className="live-judge-action">{!serverConfigured&&<label className="byok-field"><span>OPENAI API KEY</span><input type="password" value={apiKey} onChange={event=>setApiKey(event.target.value)} placeholder="Paste a restricted project key" autoComplete="off" spellCheck={false} disabled={!enabled||busy}/><small>Sent once over same-origin HTTPS · never persisted · cleared immediately</small></label>}<button className="button primary" onClick={submit} disabled={!enabled||busy||(!serverConfigured&&!apiKey.trim())} aria-busy={busy}><Icon name="pulse"/>{busy?'Analyzing redacted trace…':analysis?.mode==='live'?'Run live analysis again':'Investigate with GPT‑5.6 Sol'}</button><span className={`availability ${enabled?'enabled':'disabled'}`}><i/>{serverConfigured?'Server key configured':enabled?'Ephemeral BYOK ready':'Runtime disabled'}</span>{error&&<p role="alert">{error}</p>}</div>
    {analysis?.mode==='live'&&<div className="live-result"><header><div><span>VALIDATED LIVE RESPONSE</span><b>{analysis.model}</b></div><code title={analysis.response_id}>{shortId(analysis.response_id)}</code></header><div>{analysis.findings.length?analysis.findings.map((finding,index)=><article key={`${finding.finding_type}-${index}`}><span className={`severity ${finding.severity}`}><i/>{finding.severity}</span><div><h3>{finding.summary}</h3><p>{finding.reasoning_summary||'Evidence-linked semantic finding.'}</p></div><strong>{Math.round(finding.confidence*100)}%</strong></article>):<p>No semantic findings were returned.</p>}</div><footer>Requested {analysis.requested_model||'gpt-5.6-sol'} · resolved {analysis.model} · {analysis.reasoning_effort||'medium'} reasoning · prompt {analysis.prompt_version}</footer></div>}
  </section>;
}

const focusEvent=(id:string)=>window.setTimeout(()=>document.getElementById(`event-${id}`)?.focus(),0);
const clauseCopy=(clause:IntentClause)=>clause.statement||clause.text||titleCase(clause.kind||clause.clause_type||clause.id);
const coveragePercent=(value:number)=>Math.max(0,Math.min(100,Math.round(value<=1?value*100:value)));

function TraceEventLink({id,label}:{id:string;label?:string}){
  return <a className="trace-event-link" href={`#event-${id}`} onClick={()=>focusEvent(id)} title={id}><span>{label||shortId(id)}</span><Icon name="arrow"/></a>;
}

function IntentCausalRecordView({record,loading,error}:{record:IntentCausalRecord|null;loading:boolean;error:string}){
  if(loading)return <section className="intent-causal-card intent-causal-loading" aria-label="Loading Intent Causal Record" aria-busy="true"><div className="intent-causal-skeleton"><i/><i/><i/></div><span>Binding intent clauses to trace evidence…</span></section>;
  if(error)return <section className="intent-causal-card intent-causal-unavailable" aria-labelledby="intent-causal-title"><Icon name="warning"/><div><p className="kicker">INTENT CAUSAL RECORD</p><h2 id="intent-causal-title">Intent analysis unavailable</h2><p>{error} The recorded trace and deterministic findings remain available.</p></div></section>;
  if(!record)return null;
  const coverage=coveragePercent(record.coverage?.verified_coverage_ratio??record.intent_coverage);
  const declarationCoverage=coveragePercent(record.coverage?.declaration_coverage_ratio??0);
  const actionCoverage=coveragePercent(record.coverage?.consequential_action_coverage_ratio??0);
  const frontierCount=record.divergence_frontier?.length||0;
  const bindingsByClause=new Map<string,IntentBinding[]>();
  for(const binding of record.bindings||[])bindingsByClause.set(binding.clause_id,[...(bindingsByClause.get(binding.clause_id)||[]),binding]);
  return <section className="intent-causal-card" aria-labelledby="intent-causal-title">
    <header className="intent-causal-heading"><div><p className="kicker">INTENT CAUSAL RECORD</p><h2 id="intent-causal-title">From declared contract to verified behavior</h2><p>A clause-by-clause conformance record with versioned verifier evidence and a causal-minimal divergence frontier.</p></div><div className="coverage-seal"><strong>{coverage}%</strong><span>verified coverage</span></div></header>
    <div className="intent-causal-summary">
      <article className="divergence-card"><span className="summary-icon"><Icon name="warning"/></span><div><p className="kicker">DIVERGENCE FRONTIER</p><h3>{record.first_divergence_event_id?`${frontierCount||1} causal-minimal violation${frontierCount===1?'':'s'}`:'No detected violation'}</h3><p>{record.first_divergence_reason||'No configured verifier classified an event as violating the declared contract.'}</p>{frontierCount>0&&<div className="frontier-links">{record.divergence_frontier?.map((item,index)=><TraceEventLink id={item.event_id} key={item.event_id} label={`F${index+1} · event ${item.sequence}`}/>)}</div>}</div></article>
      <article className="coverage-card"><div className="coverage-row"><div><p className="kicker">EVIDENCE COVERAGE</p><h3>Behavioral verification, separated from declarations</h3></div><b>{record.coverage?.verified_clauses ?? record.bindings?.length ?? 0} / {record.coverage?.total_clauses ?? record.clauses.length}</b></div><div className="coverage-breakdown"><div><span><b>Verified</b><em>{coverage}%</em></span><progress max="100" value={coverage}>{coverage}%</progress></div><div><span><b>Declared</b><em>{declarationCoverage}%</em></span><progress max="100" value={declarationCoverage}>{declarationCoverage}%</progress></div><div><span><b>Actions bound</b><em>{actionCoverage}%</em></span><progress max="100" value={actionCoverage}>{actionCoverage}%</progress></div></div><p>Each measure answers a different question; none is a safety score.</p></article>
      <article className={`unbound-card ${(record.unbound_consequential_actions||[]).length?'has-risk':''}`}><p className="kicker">UNBOUND ACTIONS</p><strong>{(record.unbound_consequential_actions||[]).length}</strong><h3>Consequential actions without an intent clause</h3><p>{(record.unbound_consequential_actions||[]).length?'Review these before promotion.':'Every consequential action has an explicit intent binding.'}</p></article>
    </div>
    <div className="intent-causal-body">
      <section className="clause-register" aria-labelledby="clause-register-title"><div className="causal-section-heading"><div><p className="kicker">CLAUSE REGISTER</p><h3 id="clause-register-title">Authorized boundaries</h3></div><span>{record.clauses?.length||0} clauses</span></div><ol>{(record.clauses||[]).map((clause,index)=>{
        const bindings=bindingsByClause.get(clause.id)||[];
        const eventIds=bindings.flatMap(binding=>binding.event_ids||[binding.event_id].filter((id):id is string=>Boolean(id)));
        const status=clause.status||bindings[0]?.status||(eventIds.length?'bound':'unbound');
        return <li key={clause.id} className={`clause-${status}`}><span className="clause-index">{String(index+1).padStart(2,'0')}</span><div><div className="clause-title"><b>{clauseCopy(clause)}</b><code title={clause.id}>{shortId(clause.id)}</code></div><p><span className={`clause-status ${status}`}>{titleCase(status)}</span><span>{titleCase(clause.kind||clause.clause_type||'intent clause')}</span>{clause.critical&&<span className="critical-clause">Critical</span>}</p><div className="clause-events">{eventIds.length?eventIds.map(id=><TraceEventLink id={id} key={id}/>):<span>No behavior-specific evidence</span>}</div></div></li>})}</ol></section>
      <section className="decision-register" aria-labelledby="decision-register-title"><div className="causal-section-heading"><div><p className="kicker">STRUCTURED DECISIONS</p><h3 id="decision-register-title">Application decision record</h3></div><span>{record.decision_records?.length||0} decisions</span></div><p className="reasoning-disclosure"><Icon name="database"/><span><b>Application-provided summaries.</b> CausalGate records structured decision fields and evidence links. Hidden model reasoning or chain-of-thought is not captured.</span></p><ol>{(record.decision_records||[]).map((decision,index)=>{
        const clauseIds=decision.bound_clause_ids||decision.clause_ids||[];
        return <li key={`${decision.event_id}-${index}`}><div className="decision-marker"><span>{String(index+1).padStart(2,'0')}</span><i/></div><div className="decision-copy"><div><span className={`decision-verdict ${decision.decision.toLowerCase()}`}>{titleCase(decision.decision)}</span><code>{decision.action||'application decision'}</code>{typeof decision.confidence==='number'&&<code>{Math.round(decision.confidence*100)}% self-reported confidence</code>}</div><p>{decision.summary||decision.reason||'No application summary was supplied.'}</p>{decision.alternatives_considered?.length&&<p className="decision-alternatives"><b>Alternatives considered:</b> {decision.alternatives_considered.join(' · ')}</p>}<footer><TraceEventLink id={decision.event_id}/><span>{clauseIds.length?`Bound to ${clauseIds.join(', ')}`:'No clause binding'}</span></footer></div></li>})}</ol></section>
    </div>
    <div className="causal-chain"><div><p className="kicker">CAUSAL PROVENANCE</p><h3>Recorded dependency path</h3></div><ol>{(record.causal_chain_event_ids||[]).map((id,index)=><li key={id}><TraceEventLink id={id} label={String(index+1).padStart(2,'0')}/></li>)}</ol></div>
    {(record.unbound_consequential_actions||[]).length>0&&<details className="unbound-detail"><summary><span><Icon name="warning"/><b>Review unbound consequential actions</b></span><span>{record.unbound_consequential_actions.length}</span></summary><ul>{record.unbound_consequential_actions.map((item,index)=>typeof item==='string'?<li key={index}>{item}</li>:<li key={index}><b>{item.action||'Consequential action'}</b><span>{item.reason||'No intent-clause binding was recorded.'}</span>{item.event_id&&<TraceEventLink id={item.event_id}/>}</li>)}</ul></details>}
  </section>;
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
      {index===0&&<span className="first-risk">TOP PRIORITY</span>}
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

function PromotionGateView({gate}:{gate?:PromotionGate}){
  const verdict=(gate?.verdict||'pending').toLowerCase();
  const passed=['pass','passed','promote','approved'].includes(verdict);
  const review=['review','manual_review'].includes(verdict);
  const tone=passed?'passed':review?'review':'blocked';
  const title=passed?'Evidence gate passed':review?'Human review required':gate?'Promotion blocked':'Promotion evidence pending';
  return <section className={`promotion-gate ${tone}`} aria-labelledby="promotion-gate-title">
    <div className="gate-verdict"><span className="gate-icon"><Icon name={passed?'check':review?'warning':'shield'}/></span><div><p className="kicker">FIXTURE REPLAY GATE</p><h3 id="promotion-gate-title">{passed?'Fixture evidence passed':title}</h3><p>{gate?.reason||'No replay recommendation was returned. Keep this candidate out of the release path until comparison evidence is complete.'}</p></div></div>
    <div className="gate-status"><span>VERDICT</span><strong>{titleCase(gate?.verdict||'pending')}</strong><small>Evidence-gated, not score-gated</small></div>
    <div className="gate-evidence"><div><span>RESTORED CLAUSES</span><strong>{gate?.restored_clause_ids?.length||0}</strong></div><div className="gate-chips">{gate?.restored_clause_ids?.length?gate.restored_clause_ids.map(id=><code key={id}>{id}</code>):<span>None reported</span>}</div></div>
    <div className="gate-regressions"><div><span>REGRESSIONS</span><strong>{gate?.regressions?.length||0}</strong></div>{gate?.regressions?.length?<ul>{gate.regressions.map((item,index)=><li key={`${item}-${index}`}><Icon name="warning"/>{item}</li>)}</ul>:<p><Icon name="check"/>No comparison regressions reported.</p>}</div>
    <p className="gate-disclosure"><Icon name="database"/>This recommendation applies only to this fixture. Release promotion requires the authenticated multi-fixture assurance suite and remains distinct from production-safety certification.</p>
  </section>;
}

function ComparisonView({baseline,protectedRun,comparison}:{baseline:Run;protectedRun:Run;comparison:Comparison}){
  const max=Math.max(baseline.findings.length,1);
  return <section id="comparison-summary" className="comparison-card" tabIndex={-1} aria-labelledby="comparison-title">
    <div className="comparison-heading"><div className="success-mark"><Icon name="check"/></div><div><p className="kicker">COUNTERFACTUAL REPLAY</p><h2 id="comparison-title">Protected replay blocked synthetic egress</h2><p>Identical fixture <code>{comparison.fixture_hash}</code> · deterministic policy changed the recorded outcome</p></div><span className="resolved-badge">{comparison.resolved_rules.length} / {baseline.findings.length} RISKS RESOLVED</span></div>
    <div className="run-compare">
      <div className="run-card baseline"><header><span>BASELINE</span><code>{shortId(baseline.id)}</code></header><strong>{baseline.findings.length}</strong><p>open findings</p><div className="risk-bar"><i style={{width:'100%'}}/></div><footer>Observe-only policy <span>unsafe action completed</span></footer></div>
      <div className="compare-arrow" aria-hidden="true"><Icon name="arrow"/></div>
      <div className="run-card protected"><header><span>PROTECTED</span><code>{shortId(protectedRun.id)}</code></header><strong>{protectedRun.findings.length}</strong><p>open findings</p><div className="risk-bar"><i style={{width:`${(protectedRun.findings.length/max)*100}%`}}/></div><footer>Deny-by-default policy <span>{comparison.blocked_tools.join(', ')||'Sensitive tool'} blocked</span></footer></div>
    </div>
    <div className="decision-strip"><div><span>POLICY DECISION</span><strong>{comparison.changed_decisions[0]?`${comparison.changed_decisions[0].from} → ${comparison.changed_decisions[0].to}`:'No change'}</strong></div><div><span>BLOCKED TOOL</span><strong>{comparison.blocked_tools.join(', ')||'None'}</strong></div><div><span>FIXTURE PARITY</span><strong><Icon name="check"/>Exact match</strong></div><div><span>OUTCOME</span><strong><Icon name="shield"/>Egress prevented</strong></div></div>
    <PromotionGateView gate={comparison.promotion_gate}/>
  </section>;
}

function App(){
  const [run,setRun]=useState<Run|null>(null),[protectedRun,setProtected]=useState<Run|null>(null),[selected,setSelected]=useState<Finding|null>(null);
  const [comparison,setComparison]=useState<Comparison|null>(null),[busy,setBusy]=useState<BusyAction|null>(null),[failedAction,setFailedAction]=useState<BusyAction|null>(null);
  const [error,setError]=useState(''),[status,setStatus]=useState('Ready to run the synthetic scenario.'),[online,setOnline]=useState(navigator.onLine);
  const [health,setHealth]=useState<Health|null>(null),[benchmark,setBenchmark]=useState<Benchmark|null>(null),[assurance,setAssurance]=useState<AssuranceSuite|null>(null),[recorded,setRecorded]=useState<RecordedAnalysis|null>(null),[metaLoading,setMetaLoading]=useState(true);
  const [intentRecord,setIntentRecord]=useState<IntentCausalRecord|null>(null),[intentLoading,setIntentLoading]=useState(false),[intentError,setIntentError]=useState('');
  const [authorization,setAuthorization]=useState<AuthorizationRecord|null>(null),[authorizationLoading,setAuthorizationLoading]=useState(false),[authorizationError,setAuthorizationError]=useState('');
  const [liveAnalysis,setLiveAnalysis]=useState<SemanticAnalysis|null>(null),[liveBusy,setLiveBusy]=useState(false),[liveError,setLiveError]=useState('');
  const evidence=useMemo(()=>new Set(selected?.evidence_event_ids||[]),[selected]);

  useEffect(()=>{
    const update=()=>setOnline(navigator.onLine);
    window.addEventListener('online',update);window.addEventListener('offline',update);
    Promise.allSettled([api<Health>('/health'),api<Benchmark>('/api/v1/benchmark'),api<RecordedAnalysis>('/api/v1/recorded-analysis'),api<AssuranceSuite>('/api/v1/assurance-suite')]).then(results=>{
      if(results[0].status==='fulfilled')setHealth(results[0].value);
      if(results[1].status==='fulfilled')setBenchmark(results[1].value);
      if(results[2].status==='fulfilled')setRecorded(results[2].value);
      if(results[3].status==='fulfilled')setAssurance(results[3].value);
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
        setIntentRecord(null);setIntentError('');setIntentLoading(true);setAuthorization(null);setAuthorizationError('');setAuthorizationLoading(true);setLiveAnalysis(null);setLiveError('');
        const records=await Promise.allSettled([api<IntentCausalRecord>(`/api/v1/executions/${value.id}/intent-causal-record`),api<AuthorizationRecord>(`/api/v1/executions/${value.id}/authorization-record`)]);
        if(records[0].status==='fulfilled')setIntentRecord(records[0].value);else setIntentError('The Intent Causal Record could not be loaded.');
        if(records[1].status==='fulfilled')setAuthorization(records[1].value);else setAuthorizationError('The authorization record could not be loaded.');
        setIntentLoading(false);setAuthorizationLoading(false);
      }else{
        setProtected(value);
        if(run)setComparison(await api<Comparison>(`/api/v1/comparisons/${run.id}/${value.id}`));
        setStatus(`Protected replay complete with ${value.findings.length} findings.`);
        requestAnimationFrame(()=>document.getElementById('comparison-summary')?.focus());
      }
    }catch(error){setFailedAction(mode);setError(error instanceof DOMException&&error.name==='AbortError'?'The CausalGate service timed out. Retry when it is ready.':'The demo could not complete. Check the CausalGate service and retry.');setStatus('Demo failed.')}finally{setBusy(null)}
  };
  const reset=async()=>{
    if(busy)return;setBusy('reset');setFailedAction(null);setError('');setStatus('Resetting the synthetic demo.');
    try{await api('/api/v1/demo/reset',{method:'POST'});setRun(null);setProtected(null);setComparison(null);setSelected(null);setIntentRecord(null);setIntentError('');setIntentLoading(false);setAuthorization(null);setAuthorizationError('');setAuthorizationLoading(false);setLiveAnalysis(null);setLiveError('');setStatus('Demo reset. Ready to run the synthetic scenario.');requestAnimationFrame(()=>document.getElementById('run-baseline')?.focus())}
    catch{setFailedAction('reset');setError('The demo could not reset. Check the CausalGate service and retry.');setStatus('Reset failed.')}finally{setBusy(null)}
  };
  const analyzeWithSol=async(apiKey:string)=>{
    if(!run||liveBusy)return;
    setLiveBusy(true);setLiveError('');setStatus('GPT-5.6 Sol is analyzing the minimized redacted trace.');
    try{const result=await api<SemanticAnalysis>(`/api/v1/executions/${run.id}/analyze/live`,{method:'POST',headers:apiKey?{'X-OpenAI-API-Key':apiKey}:{}} ,70000);setLiveAnalysis(result);setStatus(`Live semantic analysis completed with ${result.findings.length} findings.`)}
    catch{setLiveError('Live analysis is unavailable. Deterministic authorization and findings remain valid.');setStatus('Live semantic analysis unavailable.')}finally{setLiveBusy(false)}
  };
  const retry=()=>failedAction==='reset'?reset():execute(failedAction||'baseline');

  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Skip to investigation</a>
    <header className="app-header"><a className="brand" href="#main-content" aria-label="CausalGate home"><span className="brand-mark"><Icon name="gate"/></span><span><b>CausalGate</b><small>INTENT CONTROL</small></span></a><span className="header-divider"/><p>Intent assurance for agent systems</p><nav aria-label="Product links"><a href="/api/docs">API docs</a><ModeDisclosure health={health} recorded={recorded} online={online}/></nav></header>
    {!online&&<div className="offline-banner" role="status"><Icon name="warning"/><span><b>Network unavailable</b> — reconnect to run or replay. Loaded evidence remains available.</span></div>}
    <main id="main-content">
      <section className="hero" aria-labelledby="page-title"><div className="hero-copy"><div className="eyebrow-row"><span>INTENT ASSURANCE</span><i/><span>SOFTWARE FACTORY EVIDENCE</span></div><h1 id="page-title">Find where intent<br/><em>diverged.</em></h1><p>Evaluate consequential actions against a declared contract, preserve concurrent divergence, and test a candidate control before release review.</p></div>
        <div className="hero-rail"><div className="scenario-label"><span>SEEDED SCENARIO</span><b>Indirect prompt injection</b><small>vendor-research-injection-v1</small></div><div className="hero-actions"><button id="run-baseline" className="button primary" onClick={()=>execute('baseline')} disabled={!!busy} aria-busy={busy==='baseline'}><Icon name="play"/>{busy==='baseline'?'Recording baseline…':run?'Run new baseline':'Run vulnerable scenario'}</button><button className="button protected-action" onClick={()=>execute('protected')} disabled={!!busy||!run} aria-busy={busy==='protected'}><Icon name="shield"/>{busy==='protected'?'Applying control…':'Replay with protection'}</button><button className="button icon-only" onClick={reset} disabled={!!busy||!run} aria-busy={busy==='reset'} aria-label="Reset synthetic demo" title="Reset demo"><Icon name="reset"/></button></div><p className="action-note"><Icon name="check"/>Synthetic fixture · simulated tools · live analysis only when explicitly requested</p></div>
      </section>
      <p className="sr-only" aria-live="polite" aria-atomic="true">{status}</p>
      {error&&<div className="error-banner" role="alert"><Icon name="warning"/><div><b>Action unavailable</b><span>{error}</span></div><button className="button" onClick={retry} disabled={!!busy}>Retry action</button><button className="dismiss" onClick={()=>setError('')} aria-label="Dismiss error">×</button></div>}
      {!run?<div className="preflight-grid"><EmptyState busy={!!busy} onRun={()=>execute('baseline')}/><div className="preflight-side"><BenchmarkCard benchmark={benchmark} loading={metaLoading}/><AssuranceSuiteCard suite={assurance} loading={metaLoading} compact/><section className="workflow-card"><p className="kicker">INTENT-TO-RELEASE LOOP</p><h2>From divergence to evidence</h2><ol><li><span>01</span><div><b>Evaluate</b><p>Apply versioned verifier rules to plans, decisions, tools, state, and outcomes.</p></div></li><li><span>02</span><div><b>Locate</b><p>Return every causal-minimal detected violation, including concurrent branches.</p></div></li><li><span>03</span><div><b>Gate</b><p>Require an authenticated multi-fixture suite before issuing a scoped release recommendation.</p></div></li></ol></section></div></div>:
      <>
        <section id="execution-summary" className="execution-bar" tabIndex={-1} aria-label="Baseline execution summary"><div><span>EXECUTION</span><b title={run.id}>{shortId(run.id)}</b></div><div><span>FIXTURE</span><b title={run.fixture_hash}>{run.fixture_hash}</b></div><div><span>POLICY MODE</span><b className="observe"><i/>Observe only</b></div><div><span>TRACE</span><b>{run.events.length} events</b></div><div><span>RISK</span><b className="risk"><i/>{run.findings.length} open</b></div></section>
        {protectedRun&&comparison&&<><ComparisonView baseline={run} protectedRun={protectedRun} comparison={comparison}/><AssuranceSuiteCard suite={assurance} loading={metaLoading}/></>}
        <IntentCard run={run}/>
        <AuthorizationCard record={authorization} loading={authorizationLoading} error={authorizationError}/>
        <IntentCausalRecordView record={intentRecord} loading={intentLoading} error={intentError}/>
        <LiveJudgeAnalysis health={health} analysis={liveAnalysis} busy={liveBusy} error={liveError} onAnalyze={analyzeWithSol}/>
        <section className="workbench"><FindingList findings={run.findings} selected={selected} onSelect={setSelected}/><Timeline run={run} evidence={evidence}/><EvidencePanel selected={selected} run={run} recorded={recorded}/></section>
      </>}
    </main>
    <footer className="app-footer"><span><span className="status-dot ok"/>Synthetic judge environment</span><span>Payloads redacted by the service</span><span>Schema v1.0</span><a href="/api/docs">API reference</a></footer>
  </div>;
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
