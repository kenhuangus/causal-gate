import {readFileSync} from 'node:fs';
import {describe,expect,it} from 'vitest';

const source=readFileSync(new URL('./main.tsx',import.meta.url),'utf8');
const styles=readFileSync(new URL('./styles.css',import.meta.url),'utf8');

describe('judge UI contracts',()=>{
  it('keeps the primary workflow anonymous and fixture-backed',()=>{
    expect(source).toContain("/api/v1/demo/${mode}");
    expect(source).toContain('/api/v1/comparisons/${run.id}/${value.id}');
    expect(source).toContain('/api/v1/recorded-analysis');
    expect(source).toContain('/api/v1/assurance-suite');
    expect(source).not.toMatch(/sign[ -]?in|log[ -]?in/i);
  });

  it('discloses deterministic, recorded, and live-analysis provenance',()=>{
    expect(source).toContain('Deterministic');
    expect(source).toContain('Recorded');
    expect(source).toContain('Live model analysis');
    expect(source).toContain('not a live call');
    expect(source).toContain('no external side effects');
  });

  it('provides semantic navigation and async announcements',()=>{
    expect(source).toContain('Skip to investigation');
    expect(source).toContain('aria-live="polite"');
    expect(source).toContain('role="alert"');
    expect(source).toContain('aria-busy={busy');
    expect(source).toContain('aria-pressed={selected?.id===finding.id}');
    expect(source).toContain('aria-label="Security findings"');
  });

  it('supports offline, empty, loading, error, and busy states',()=>{
    for(const state of ['Network unavailable','NO TRACE LOADED','Loading benchmark','Action unavailable','Recording baseline…']){
      expect(source).toContain(state);
    }
    expect(source).toContain('Run 13-event baseline');
  });

  it('presents intent evidence without implying access to hidden reasoning',()=>{
    expect(source).toContain('/intent-causal-record');
    for(const copy of ['INTENT CAUSAL RECORD','DIVERGENCE FRONTIER','CLAUSE REGISTER','STRUCTURED DECISIONS','CAUSAL PROVENANCE','UNBOUND ACTIONS']){
      expect(source).toContain(copy);
    }
    expect(source).toContain('Application-provided summaries');
    expect(source).toContain('Hidden model reasoning or chain-of-thought is not captured');
    expect(styles).toContain('.intent-causal-card');
  });

  it('shows an evidence-gated software factory promotion decision',()=>{
    for(const contract of ['promotion_gate','restored_clause_ids','regressions','FIXTURE REPLAY GATE','Evidence-gated, not score-gated']){
      expect(source).toContain(contract);
    }
    expect(source).toContain('production-safety certification');
    expect(styles).toContain('.promotion-gate');
  });

  it('makes intent-based authorization and the bounded Sol investigator judge-visible',()=>{
    for(const copy of ['INTENT-BASED ACCESS CONTROL','COMPLETE MEDIATION','INTENT GRANT','LEAST PRIVILEGE','Single-use permit','GPT‑5.6 Sol','medium reasoning','cannot authorize a tool']){
      expect(source).toContain(copy);
    }
    expect(source).toContain('/authorization-record');
    expect(source).toContain('/analyze/live');
    expect(source).toContain('BRING YOUR OWN KEY');
    expect(source).toContain('never persisted');
    expect(source).toContain("'X-OpenAI-API-Key':apiKey");
    expect(styles).toContain('.authorization-card');
    expect(styles).toContain('.live-judge-card');
  });

  it('makes mathematical assurance legible to judges',()=>{
    for(const copy of ['AUTHENTICATED RELEASE EVIDENCE','UNCERTAINTY BOUND','RUNNER ATTESTATION','GATE CONDITIONS','Behavioral verification, separated from declarations','self-reported confidence']){
      expect(source).toContain(copy);
    }
    for(const contract of ['assurance-suite-card','confidence-track','coverage-breakdown','frontier-links','critical-clause']){
      expect(styles).toContain(`.${contract}`);
    }
    expect(source).toContain('Scoped evidence—not a general production-safety certificate.');
  });

  it('is self-contained and includes resilient accessibility media rules',()=>{
    expect(styles).not.toMatch(/@import|https?:\/\//);
    expect(styles).toContain('min-width:320px');
    expect(styles).toContain('@media(max-width:480px)');
    expect(styles).toContain('@media(prefers-reduced-motion:reduce)');
    expect(styles).toContain('@media(forced-colors:active)');
    expect(styles).toContain(':focus-visible');
  });
});
