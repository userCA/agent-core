import * as Collapsible from '@radix-ui/react-collapsible';
import React, { useState, useEffect, useRef, useMemo } from 'react';
import { useSkillStore } from '../../stores/skill-store';
import TooltipWrap from '../shared/TooltipWrap';
import type { EvolutionProposal, EvolutionAuditEntry } from '../../api/client';
import './EvolutionPanel.css';

interface Props { skillName: string }

const OP_LABELS: Record<string, string> = {
  add: '\u6dfb\u52a0', modify: '\u4fee\u6539', delete: '\u5220\u9664', merge: '\u5408\u5e76',
};
const OP_ICONS: Record<string, string> = {
  add: '+', modify: '\u270e', delete: '\u00d7', merge: '\u2194',
};

function confidenceTier(c: number): string {
  if (c >= 0.8) return 'tier-high';
  if (c >= 0.6) return 'tier-mid';
  return 'tier-low';
}

function confidenceLabel(c: number): string {
  if (c >= 0.8) return 'Strong signal';
  if (c >= 0.6) return 'Moderate';
  return 'Weak signal';
}

/* ── Diff syntax highlighter ────────────────────────────────── */

interface DiffLine {
  type: 'meta' | 'add' | 'del' | 'ctx';
  text: string;
}

function parseDiff(raw: string): DiffLine[] {
  return raw.split('\n').map((line) => {
    if (!line) return { type: 'ctx', text: '' };
    if (line[0] === '#' || line.startsWith('//')) return { type: 'meta', text: line };
    if (line[0] === '+') return { type: 'add', text: line };
    if (line[0] === '-') return { type: 'del', text: line };
    return { type: 'ctx', text: line };
  });
}

/* ── Animated counter hook ──────────────────────────────────── */

function useAnimatedCounter(target: number, duration = 600) {
  const [val, setVal] = useState(0);
  const frame = useRef(0);

  useEffect(() => {
    if (target === 0) { setVal(0); return; }
    const start = val > target ? target : val;
    const startTime = performance.now();
    const step = (now: number) => {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - (1 - progress) ** 3;
      setVal(Math.round(start + (target - start) * eased));
      if (progress < 1) frame.current = requestAnimationFrame(step);
    };
    frame.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame.current);
  }, [target, duration]);

  return val;
}

/* ── Main component ──────────────────────────────────────────── */

export default function EvolutionPanel({ skillName }: Props) {
  const evolutionSummary = useSkillStore((s) => s.evolutionSummary);
  const evolutionLoading = useSkillStore((s) => s.evolutionLoading);
  const proposals = useSkillStore((s) => s.evolutionProposals[skillName] || []);
  const evolutionAudit = useSkillStore((s) => s.evolutionAudit);
  const analyzeEvolution = useSkillStore((s) => s.analyzeEvolution);
  const loadEvolutionProposals = useSkillStore((s) => s.loadEvolutionProposals);
  const acceptProposal = useSkillStore((s) => s.acceptProposal);
  const rejectProposal = useSkillStore((s) => s.rejectProposal);
  const loadEvolutionAudit = useSkillStore((s) => s.loadEvolutionAudit);
  const loadEvolutionSummary = useSkillStore((s) => s.loadEvolutionSummary);

  const [expanded, setExpanded] = useState(false);
  const [loadingProposals, setLoadingProposals] = useState(false);
  const [rejectReason, setRejectReason] = useState('');

  const traces = evolutionSummary?.trace_counts?.[skillName];
  const skillAudit = useMemo(
    () => evolutionAudit.filter((e) => e.skill_name === skillName).slice(0, 12),
    [evolutionAudit, skillName],
  );

  const total = useAnimatedCounter(traces?.total ?? 0);
  const succ = useAnimatedCounter(traces?.success ?? 0);
  const fail = useAnimatedCounter(traces?.failure ?? 0);
  const hasTraces = traces && traces.total > 0;
  const failRate = hasTraces ? Math.round((traces.failure / traces.total) * 100) : 0;

  useEffect(() => {
    if (evolutionSummary === null) loadEvolutionSummary();
  }, [evolutionSummary, loadEvolutionSummary]);

  const handleAnalyze = async () => {
    setLoadingProposals(true);
    await analyzeEvolution(skillName);
    setLoadingProposals(false);
    handleExpand(true);
  };

  const handleExpand = (next: boolean) => {
    setExpanded(next);
    if (next) {
      loadEvolutionProposals(skillName);
      loadEvolutionAudit(skillName);
    }
  };

  const handleAccept = async (id: string) => {
    await acceptProposal(id, skillName);
    await loadEvolutionAudit(skillName);
  };

  const handleReject = async (id: string) => {
    await rejectProposal(id, skillName, rejectReason || undefined);
    setRejectReason('');
    await loadEvolutionAudit(skillName);
  };

  return (
    <div className={`evo-root${expanded ? ' evo-open' : ''}`}>
      <div className="evo-bg-noise" />
      <div className="evo-bg-scan" />

      <Collapsible.Root open={expanded} onOpenChange={handleExpand}>
        <Collapsible.Trigger asChild>
          <div className="evo-trigger" aria-label="展开 Evolution">
            <div className="evo-trigger-left">
              <span className="evo-chevron" />
              <span className="evo-trigger-label">Evolution</span>
              {hasTraces && <span className={`evo-pulse${failRate > 30 ? ' evo-pulse-warn' : ''}`} />}
            </div>

            {hasTraces ? (
              <div className="evo-trigger-stats">
                <span className="evo-stat">
                  <span className="evo-stat-val">{total}</span>
                  <span className="evo-stat-lbl">traces</span>
                </span>
                <span className="evo-stat-divider" />
                <span className="evo-stat evo-stat-ok">
                  <span className="evo-stat-val">{succ}</span>
                  <span className="evo-stat-lbl">pass</span>
                </span>
                <span className="evo-stat-divider" />
                <span className={`evo-stat${fail > 0 ? ' evo-stat-err' : ''}`}>
                  <span className="evo-stat-val">{fail}</span>
                  <span className="evo-stat-lbl">fail</span>
                </span>
              </div>
            ) : (
              <span className="evo-trigger-empty">Awaiting data</span>
            )}
          </div>
        </Collapsible.Trigger>

        <Collapsible.Content className="evo-body">
          {/* Empty state */}
          {!hasTraces && proposals.length === 0 && (
            <div className="evo-empty">
              <div className="evo-empty-orbs">
                <span className="evo-orb" /><span className="evo-orb" /><span className="evo-orb" />
              </div>
              <p className="evo-empty-title">No execution traces yet</p>
              <p className="evo-empty-desc">
                Traces are captured automatically when skills are loaded during agent runs.
                Once enough data accumulates, the evolution system can analyse patterns and
                suggest rule improvements.
              </p>
            </div>
          )}

          {/* Actions */}
          <div className="evo-actions">
            <button
              className="evo-btn-analyze"
              disabled={evolutionLoading || loadingProposals || !hasTraces}
              onClick={(e) => { e.stopPropagation(); handleAnalyze(); }}
            >
              {loadingProposals ? (
                <><span className="evo-spinner" />Analysing traces&hellip;</>
              ) : (
                <><span className="evo-btn-icon">\u2699</span>Analyse traces</>
              )}
            </button>
            {hasTraces && proposals.length === 0 && !loadingProposals && (
              <span className="evo-hint">
                {traces.total < 10
                  ? `Need ${10 - traces.total} more traces before analysis (min. 10)`
                  : 'Ready for analysis'}
              </span>
            )}
          </div>

          {/* Proposals */}
          {proposals.length > 0 && (
            <div className="evo-proposals">
              <div className="evo-section-head">
                <span className="evo-section-icon">\u25c6</span>
                Proposals
                <span className="evo-badge">{proposals.length}</span>
              </div>
              {proposals.map((p, i) => (
                <ProposalCard
                  key={p.proposal_id}
                  proposal={p}
                  index={i}
                  onAccept={() => handleAccept(p.proposal_id)}
                  onReject={() => handleReject(p.proposal_id)}
                  rejectReason={rejectReason}
                  onRejectReasonChange={setRejectReason}
                />
              ))}
            </div>
          )}

          {/* Audit trail */}
          {skillAudit.length > 0 && (
            <div className="evo-audit">
              <div className="evo-section-head evo-section-head-sub">
                <span className="evo-section-icon">\u25cb</span>
                Audit trail
                <span className="evo-badge evo-badge-ghost">{skillAudit.length}</span>
              </div>
              {skillAudit.map((entry) => (
                <AuditEntry key={entry.audit_id} entry={entry} />
              ))}
            </div>
          )}
        </Collapsible.Content>
      </Collapsible.Root>
    </div>
  );
}

/* ── Proposal card ──────────────────────────────────────────── */

function ProposalCard({
  proposal: p, onAccept, onReject, rejectReason, onRejectReasonChange, index,
}: {
  proposal: EvolutionProposal;
  onAccept: () => void;
  onReject: () => void;
  rejectReason: string;
  onRejectReasonChange: (v: string) => void;
  index: number;
}) {
  const [showRejectInput, setShowRejectInput] = useState(false);
  const confPct = Math.round(p.confidence * 100);
  const tier = confidenceTier(p.confidence);
  const diffLines = useMemo(() => parseDiff(p.diff), [p.diff]);
  const totalAdd = diffLines.filter((l) => l.type === 'add').length;
  const totalDel = diffLines.filter((l) => l.type === 'del').length;

  return (
    <div
      className={`pp-card pp-op-${p.operation}`}
      style={{ animationDelay: `${index * 60}ms` }}
    >
      {/* Header */}
      <div className="pp-head">
        <div className="pp-head-left">
          <span className={`pp-op-badge op-${p.operation}`}>
            <span className="pp-op-icon">{OP_ICONS[p.operation]}</span>
            {OP_LABELS[p.operation]}
          </span>
          {p.target_rule_id && <span className="pp-rule">{p.target_rule_id}</span>}
        </div>

        <TooltipWrap label={`${confPct}% — ${confidenceLabel(p.confidence)}`}>
          <div className="pp-conf">
          <svg className="pp-conf-ring" viewBox="0 0 36 36">
            <defs>
              <filter id={`glow-${p.proposal_id}`}>
                <feGaussianBlur stdDeviation="1.5" result="blur" />
                <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
              </filter>
            </defs>
            <circle className="pp-conf-track" cx="18" cy="18" r="14" fill="none" strokeWidth="2.5" />
            <circle
              className={`pp-conf-arc ${tier}`}
              cx="18" cy="18" r="14" fill="none" strokeWidth="2.5"
              strokeDasharray={`${(confPct / 100) * 88} 88`}
              strokeLinecap="round"
              transform="rotate(-90 18 18)"
              filter={`url(#glow-${p.proposal_id})`}
            />
          </svg>
          <span className={`pp-conf-text ${tier}`}>{confPct}<small>%</small></span>
        </div>
        </TooltipWrap>
      </div>

      {/* Rationale */}
      {p.rationale && <p className="pp-rationale">{p.rationale}</p>}

      {/* Diff terminal */}
      <div className="pp-diff-wrap">
        <div className="pp-diff-header">
          <span className="pp-diff-dots">
            <span className="pp-dot" /><span className="pp-dot" /><span className="pp-dot" />
          </span>
          <span className="pp-diff-label">diff</span>
          <span className="pp-diff-stats">
            <span className="pp-diff-stat-add">+{totalAdd}</span>
            <span className="pp-diff-stat-del">-{totalDel}</span>
          </span>
        </div>
        <div className="pp-diff">
          <table className="pp-diff-table">
            <tbody>
              {diffLines.map((l, i) => (
                <tr key={i} className={`pp-dl-${l.type}`}>
                  <td className="pp-dl-num" />
                  <td className="pp-dl-sign">{l.type === 'add' ? '+' : l.type === 'del' ? '-' : l.type === 'meta' ? '#' : ''}</td>
                  <td className="pp-dl-text">{l.text.replace(/^[#+\-]\s?/, '')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Footer actions */}
      <div className="pp-footer">
        <button className="pp-btn pp-btn-accept" onClick={onAccept}>
          <span className="pp-btn-mark">\u2713</span>Accept
        </button>
        {!showRejectInput ? (
          <button className="pp-btn pp-btn-reject" onClick={() => setShowRejectInput(true)}>
            <span className="pp-btn-mark">\u2717</span>Reject
          </button>
        ) : (
          <span className="pp-reject-row">
            <input
              className="pp-reject-input"
              placeholder="Reason (optional)"
              value={rejectReason}
              onChange={(e) => onRejectReasonChange(e.target.value)}
              autoFocus
            />
            <button className="pp-btn pp-btn-reject" onClick={onReject}>Confirm</button>
            <button
              className="pp-btn pp-btn-cancel"
              onClick={() => { setShowRejectInput(false); onRejectReasonChange(''); }}
            >
              Cancel
            </button>
          </span>
        )}
      </div>
    </div>
  );
}

/* ── Audit entry ────────────────────────────────────────────── */

function AuditEntry({ entry }: { entry: EvolutionAuditEntry }) {
  const date = new Date(entry.timestamp * 1000);
  const timeStr = date.toLocaleString(undefined, {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  });
  const isAccept = entry.action === 'accept';

  return (
    <div className={`ae-row ae-${entry.action}`}>
      <span className={`ae-mark${isAccept ? ' ae-ok' : ' ae-err'}`}>
        {isAccept ? '\u2714' : '\u2718'}
      </span>
      <span className="ae-op">{OP_LABELS[entry.operation] || entry.operation}</span>
      <span className="ae-time">{timeStr}</span>
      {entry.reject_reason && <span className="ae-reason">&mdash; {entry.reject_reason}</span>}
      <span className="ae-preview">{entry.diff_summary.slice(0, 50)}</span>
    </div>
  );
}
