import {readFileSync} from 'node:fs';
import {describe,expect,it} from 'vitest';

const source=readFileSync(new URL('./main.tsx',import.meta.url),'utf8');
const styles=readFileSync(new URL('./styles.css',import.meta.url),'utf8');

describe('judge UI contracts',()=>{
  it('keeps the primary workflow anonymous and fixture-backed',()=>{
    expect(source).toContain("/api/v1/demo/${mode}");
    expect(source).toContain('/api/v1/comparisons/${run.id}/${value.id}');
    expect(source).toContain('/api/v1/recorded-analysis');
    expect(source).not.toMatch(/sign[ -]?in|log[ -]?in|password/i);
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
    expect(source).toContain('Run 9-event baseline');
    expect(source).not.toContain('Run 12-event baseline');
  });

  it('presents intent evidence without implying access to hidden reasoning',()=>{
    expect(source).toContain('/intent-flight-record');
    for(const copy of ['INTENT FLIGHT RECORD','FIRST DIVERGENCE','CLAUSE REGISTER','STRUCTURED DECISIONS','CAUSAL CHAIN','UNBOUND ACTIONS']){
      expect(source).toContain(copy);
    }
    expect(source).toContain('Application-provided summaries');
    expect(source).toContain('Hidden model reasoning or chain-of-thought is not captured');
    expect(styles).toContain('.intent-flight-card');
  });

  it('shows an evidence-gated software factory promotion decision',()=>{
    for(const contract of ['promotion_gate','restored_clause_ids','regressions','SOFTWARE FACTORY GATE','Evidence-gated, not score-gated']){
      expect(source).toContain(contract);
    }
    expect(source).toContain('not a general production-safety certification');
    expect(styles).toContain('.promotion-gate');
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
