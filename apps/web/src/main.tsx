import React, {useEffect, useMemo, useState} from 'react';
import {createRoot} from 'react-dom/client';
import './styles.css';

type Event={id:string;sequence:number;type:string;actor:string;payload:Record<string,unknown>;provenance:string;sensitivity:string[];parent_id?:string|null;schema_version?:string};
type Finding={id:string;rule_id:string;title:string;severity:string;explanation:string;evidence_event_ids:string[];recommended_control:string;source?:string;status?:string};
type Run={id:string;policy_mode:string;fixture_hash:string;intent:{goal:string;allowed_tools:string[];prohibited_outcomes:string[];protected_resources?:string[];approval_required?:string[];completion_conditions?:string[]};events:Event[];findings:Finding[]};
type PromotionGate={verdict:string;reason:string;restored_clause_ids:string[];regressions:string[]};
type Comparison={left_id:string;right_id:string;fixture_hash:string;changed_decisions:{step:string;from:string;to:string}[];resolved_rules:string[];blocked_tools:string[];outcome:string;promotion_gate?:PromotionGate};
type IntentClause={id:string;kind?:string;clause_type?:string;statement?:string;text?:string;status?:string};
type IntentBinding={clause_id:string;event_id?:string;event_ids?:string[];status?:string;relationship?:string};
type DecisionRecord={event_id:string;action?:string;decision:string;summary?:string;reason?:string;clause_ids?:string[];bound_clause_ids?:string[];evidence_event_ids?:string[];alternatives_considered?:string[];confidence?:number};
type ConsequentialAction=string|{event_id?:string;action?:string;reason?:string};
type IntentFlightRecord={execution_id:string;clauses:IntentClause[];bindings:IntentBinding[];causal_chain_event_ids:string[];decision_records:DecisionRecord[];first_divergence_event_id:string|null;first_divergence_reason:string|null;intent_coverage:number;unbound_consequential_actions:ConsequentialAction[]};
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
const shortId=(value:string)=>value.length>18?`${value.slice(0,10)}â€¦${value.slice(-5)}`:value;
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
      <div className="mode-row"><Icon name="database"/><div><b>Fixture replay</b><span>Synthetic data Â· no external side effects</span></div><em>ACTIVE</em></div>
      <div className="mode-row"><Icon name="shield"/><div><b>Deterministic rules</b><span>Eight local, evidence-linked detectors</span></div><em>ACTIVE</em></div>
      <div className="mode-row muted"><Icon name="pulse"/><div><b>Live model analysis</b><span>{health?.live_analysis==='enabled'?'Server-enabled; not used automatically':'Disabled in this judge session'}</span></div><em>OFF</em></div>
      <div className="mode-note"><b>{recorded?`${recorded.model} recorded artifact available`:'Recorded analysis unavailable'}</b><span>{recorded?'Validated development evidenceâ€”never presented as a live call.':'Deterministic findings remain fully available.'}</span></div>
    </div>
  </details>;
}

function EmptyState({busy,onRun}:{busy:boolean;onRun:()=>void}){
  return <section className="empty-state" aria-labelledby="empty-title">
    <div className="empty-visual" aria-hidden="true"><span>01</span><i/><span>02</span><i/><span>03</span></div>
    <p className="kicker">NO TRACE LOADED</p>
    <h2 id="empty-title">Prove where an agent departed from intent</h2>
    <p>Build an Intent Flight Record for a seeded prompt-injection incident, locate the first unauthorized decision, then prove a control restores alignment.</p>
    <button className="button primary" onClick={onRun} disabled={busy}><Icon name="play"/>Run 9-event baseline</button>
    <ul aria-label="Scenario guarantees"><li><Icon name="check"/>No signup or API key</li><li><Icon name="check"/>No real secrets</li><li><Icon name="check"/>No external tools</li></ul>
  </section>;
}

function BenchmarkCard({benchmark,loading}:{benchmark:Benchmark|null;loading:boolean}){
  return <section className="benchmark-card" aria-labelledby="benchmark-title" aria-busy={loading}>
    <div className="card-heading"><div><p className="kicker">VALIDATION SUITE</p><h2 id="benchmark-title">Detector benchmark</h2></div><span className="verification-badge"><Icon name="check"/>{benchmark?.deterministic?'REPRODUCIBLE':'VERIFYING'}</span></div>
    {loading?<div className="metric-skeleton" aria-label="Loading benchmark"><i/><i/><i/></div>:benchmark?<>
      <div className="metric-row"><div><strong>{benchmark.scenarios}</strong><span>versioned scenarios</span></div><div><strong>{Math.round(benchmark.precision*100)}%</strong><span>suite precision</span></div><div><strong>{Math.round(benchmark.recall*100)}%</strong><span>suite recall</span></div></div>
      <p className="fine-print">{benchmark.suite_version} Â· Synthetic fixture results only; not a production performance claim.</p>
    </>:<div className="inline-state"><Icon name="warning"/><span>Benchmark unavailable. The investigation flow still works.</span></div>}
  </section>;
}

function IntentCard({run}:{run:Run}){
  return <details className="intent-card"ßÍ6êÚ$z{-®éÜj×76VC×&–v‡E÷&V6÷&Bæ6÷fW&vRæ6÷fW&vU÷&F–òãÒÆVgE÷&V6÷&Bæ6÷fW&vRæ6÷fW&vU÷&F–òÀ¢7VÖÖ'“Ò$–çFVçBÖ6ÆW6R6÷fW&vRFöW2æ÷B&Vw&W72–âF†R&÷FV7FVB6æF–FFRâ"À¢’À¢Ð¢ÆVgE÷f–öÆFVBÒ°¢&–æF–æræ6ÆW6Uö–Bf÷"&–æF–ær–âÆVgE÷&V6÷&Bæ&–æF–æw2–b&–æF–ærç7FGW2çfÇVRÓÒ'f–öÆFVB ¢Ð¢&–v‡E÷6F—6f–VBÒ°¢&–æF–æræ6ÆW6Uö–Bf÷"&–æF–ær–â&–v‡E÷&V6÷&Bæ&–æF–æw2–b&–æF–ærç7FGW2çfÇVRÓÒ'6F—6f–VB ¢Ð¢&W7F÷&VBÒ6÷'FVB†ÆVgE÷f–öÆFVBb&–v‡E÷6F—6f–VB¢6†V6·2æW‡FVæB…°¢&öÖ÷F–öä6†V6²€¢æÖSÒ&ÆÅöF—fW&vVçEö6ÆW6W5÷&W7F÷&VB"À¢76VCÖÆVgE÷f–öÆFVBÃÒ&–v‡E÷6F—6f–VBÀ¢7VÖÖ'“Ò$WfW'’&6VÆ–æRÖF—fW&vVçB6ÆW6R†2&V†f–÷"×7V6–f–26F—6f–VBWf–FVæ6R–âF†R6æF–FFRâ"À¢’À¢&öÖ÷F–öä6†V6²€¢æÖSÒ&æõ÷Væ&÷VæEö6öç6WVVçF–Åö7F–öç2"À¢76VCÖæ÷B&–v‡E÷&V6÷&BçVæ&÷VæEö6öç6WVVçF–Åö7F–öç2À¢7VÖÖ'“Ò$WfW'’6öç6WVVçF–Â6æF–FFR7F–öâ—2&÷VæBFòâ–çFVçB6ÆW6Râ"À¢’À¢Ò¢VÆ–v–&ÆRÒÆÂ†6†V6²ç76VBf÷"6†V6²–â6†V6·2¢æWu÷'VÆW2Ò6÷'FVB‡&–v‡E÷'VÆW2ÒÆVgE÷'VÆW2¢&Vw&W76–öç2Ò¶6†V6²ææÖRf÷"6†V6²–â6†V6·2–bæ÷B6†V6²ç76VEÐ¢&Vw&W76–öç2æW‡FVæB†b&æWu÷'VÆS§·'VÆWÒ"f÷"'VÆR–âæWu÷'VÆW2¢vFRÒ&öÖ÷F–öävFR€¢VÆ–v–&ÆSÖVÆ–v–&ÆRÀ¢6†V6·3Ö6†V6·2À¢fW&F–7CÒ'&öÖ÷FR"–bVÆ–v–&ÆRVÇ6R&†öÆB"À¢&V6öãÒ€¢$6æF–FFR&W7F÷&VBF†RFWFV7FVB–çFVçBF—fW&vVæ6RöâF†R–FVçF–6Âf—‡GW&Rv—F‚æòæWrFWFW&Ö–æ—7F–2f–æF–æw2â ¢–bVÆ–v–&ÆP¢VÇ6R$6æF–FFRF–Bæ÷B6F—6g’WfW'’FWFW&Ö–æ—7F–2–çFVçB×&W7F÷&F–öâæB&Vw&W76–öâ6†V6²â ¢’À¢&W7F÷&VEö6ÆW6Uö–G3×&W7F÷&VBÀ¢&Vw&W76–öç3×&Vw&W76–öç2À¢¢&WGW&â6ö×&—6öâ†ÆVgEö–CÖÆVgBæ–BÂ&–v‡Eö–C×&–v‡Bæ–BÂf—‡GW&Uö†6ƒÖÆVgBæf—‡GW&Uö†6‚÷"""À¢6†ævVEöFV6—6–öç3ÖFV6—6–öç2Â&Æö6¶VE÷FööÇ3Ö&Æö6¶VBÀ¢&W6öÇfVE÷'VÆW3×6÷'FVB†ÆVgE÷'VÆW2Ò&–v‡E÷'VÆW2’Â÷WF6öÖSÒ%&÷FV7FVB&WÆ’&Æö6¶VB7–çF†WF–2Vw&W72"À¢&öÖ÷F–öåövFSÖvFR