'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { T } from './tokens';
import { BackNav, HeaderStrip, Panel, Icon, MarkdownContent } from './atoms';
import { Shell, Loading, ErrorBox } from './corpus-detail';
import type { InvestigationDetail, InvestigationPhase } from '@/lib/scientific-literature';

// Canonical lifecycle order; the timeline always renders all five rows so that
// not-yet-recorded phases read as "pending" placeholders.
const PHASES: Array<{ key: string; label: string }> = [
  { key: 'discovery', label: 'Discovery' },
  { key: 'ingest', label: 'Ingest' },
  { key: 'sensemaking', label: 'Sensemaking' },
  { key: 'analysis', label: 'Analysis' },
  { key: 'report', label: 'Report' },
];

function statusColor(status?: string): string {
  switch (status) {
    case 'complete':
      return T.teal;
    case 'report':
    case 'analysis':
      return T.olive;
    case 'scoping':
      return T.fgFaint;
    default:
      return T.blue;
  }
}

export function InvestigationDetailView({ id }: { id: string }) {
  const [data, setData] = useState<InvestigationDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`/api/scientific-literature/investigation/${id}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(`API returned ${r.status}`)))
      .then((json) => {
        if (json.error || json.success === false) setError(json.error || 'Investigation not found');
        else setData(json);
      })
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  }, [id]);

  const byPhase: Record<string, InvestigationPhase> = {};
  for (const p of data?.phases || []) byPhase[p.phase] = p;

  return (
    <Shell>
      <BackNav href="/scientific-literature" label="Corpora" />
      {loading && !data && <Loading />}
      {error && <ErrorBox message={error} />}
      {data && (
        <>
          <HeaderStrip
            typeChip={{ short: 'INVESTIGATION', color: T.rust, icon: 'search' }}
            context={data.id}
            title={data.name || data.id}
            kvPairs={[
              { label: 'status', value: data.status || '—', accent: statusColor(data.status) },
              { label: 'started', value: data['created-at']?.slice(0, 10) || '—' },
              { label: 'phases', value: `${data.phases.length}/5` },
            ]}
            action={
              data.corpus ? (
                <Link
                  href={`/scientific-literature/corpus/${data.corpus.id}`}
                  style={{
                    display: 'inline-flex', alignItems: 'center', gap: 6,
                    fontFamily: T.mono, fontSize: 11, color: T.teal, textDecoration: 'none',
                    border: `1px solid ${T.borderHi}`, borderRadius: 3, padding: '4px 10px',
                  }}
                >
                  <Icon name="folder" size={13} color={T.teal} /> {data.corpus.name || data.corpus.id}
                </Link>
              ) : undefined
            }
          />

          {data.purpose && (
            <Panel title="Purpose">
              <MarkdownContent content={data.purpose} />
            </Panel>
          )}

          <Panel title="Lifecycle">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
              {PHASES.map(({ key, label }, i) => {
                const phase = byPhase[key];
                const done = !!phase;
                return (
                  <div
                    key={key}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '24px 1fr',
                      gap: 14,
                      paddingBottom: i < PHASES.length - 1 ? 18 : 0,
                    }}
                  >
                    {/* Timeline rail + node */}
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                      <div style={{
                        width: 14, height: 14, borderRadius: '50%',
                        background: done ? T.rust : 'transparent',
                        border: `1.5px solid ${done ? T.rust : T.borderHi}`,
                        marginTop: 2, flexShrink: 0,
                      }} />
                      {i < PHASES.length - 1 && (
                        <div style={{ width: 1.5, flex: 1, minHeight: 24, background: T.borderDim, marginTop: 4 }} />
                      )}
                    </div>

                    {/* Phase content */}
                    <div style={{ minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
                        <span style={{
                          fontFamily: T.mono, fontSize: 11, fontWeight: 600,
                          letterSpacing: '1px', textTransform: 'uppercase',
                          color: done ? T.fg : T.fgFaint,
                        }}>{label}</span>
                        <span style={{ fontFamily: T.mono, fontSize: 10, color: T.fgFaint }}>
                          {done ? (phase['created-at']?.slice(0, 10) || '') : 'pending'}
                        </span>
                      </div>

                      {done && phase.content && (
                        <div style={{
                          marginTop: 8, padding: '10px 14px',
                          background: T.panel, border: `1px solid ${T.borderDim}`, borderRadius: 4,
                        }}>
                          <MarkdownContent content={phase.content} />
                        </div>
                      )}

                      {key === 'analysis' && done && (phase.faceting_notes?.length ?? 0) > 0 && (
                        <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
                          {phase.faceting_notes!.map((fn) => (
                            <Link
                              key={fn.id}
                              href={`/scientific-literature/faceting-note/${fn.id}`}
                              style={{
                                display: 'inline-flex', alignItems: 'center', gap: 8,
                                fontFamily: T.mono, fontSize: 11.5, color: T.olive, textDecoration: 'none',
                                border: `1px solid ${T.oliveDim}`, borderRadius: 3, padding: '6px 10px',
                                background: T.oliveDim,
                              }}
                            >
                              <Icon name="bar-chart" size={12} color={T.olive} />
                              {fn.name || fn.id}
                            </Link>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </Panel>
        </>
      )}
    </Shell>
  );
}
