import React, { useState } from 'react';
import Icon from '../shared/Icon';
import './WorkflowCard.css';

interface Props {
  name?: string;
  status?: 'running' | 'done';
  workflowStatus?: string;
  phase?: string | null;
  phases?: string[];
  log?: string[];
  completedAgents?: number;
  totalAgents?: number;
  isError?: boolean;
}

/** Determine phase status: completed / current / pending */
function phaseStatus(
  p: string,
  currentPhase: string | null | undefined,
  phases: string[],
  workflowDone: boolean,
): string {
  if (workflowDone) return 'completed';
  if (p === currentPhase) return 'current';
  const idx = phases.indexOf(p);
  const curIdx = currentPhase ? phases.indexOf(currentPhase) : -1;
  if (curIdx >= 0 && idx < curIdx) return 'completed';
  return 'pending';
}

/** Human-readable status label */
function statusLabel(s: string): string {
  switch (s) {
    case 'completed': return '完成';
    case 'current': return '执行中';
    case 'pending': return '等待';
    default: return s;
  }
}

export default function WorkflowCard({
  name,
  status,
  workflowStatus,
  phase,
  phases = [],
  log = [],
  completedAgents = 0,
  totalAgents = 0,
  isError,
}: Props) {
  const [open, setOpen] = useState(status === 'running');
  const running = status === 'running';
  const agentProgress =
    totalAgents > 0 ? `${completedAgents}/${totalAgents}` : '';
  const workflowDone = !running && !isError;

  const stateClass = isError ? 'done-error' : running ? 'active' : 'done-ok';
  const label = isError
    ? '工作流失败'
    : running
      ? (name ? `工作流 · ${name}` : '工作流执行中')
      : workflowStatus === 'aborted'
        ? '工作流已中止'
        : workflowStatus === 'failed'
          ? '工作流失败'
          : (name ? `工作流 · ${name}` : '工作流已完成');

  return (
    <div className={`step-section ${stateClass}${open ? ' open' : ''}`}>
      <button
        type="button"
        className="section-summary"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="section-label">
          <span className="section-icon">
            {running ? (
              <span className="section-spinner-icon">
                <Icon name="spinner" size={12} />
              </span>
            ) : (
              <Icon name={isError ? 'alert' : 'sparkles'} size={12} />
            )}
          </span>
          {label}
          {phase ? <span className="workflow-phase-tag">{phase}</span> : null}
          {agentProgress ? <span className="workflow-progress-tag">{agentProgress}</span> : null}
        </span>
        <span className="section-right">
          <span className="section-status-icon">
            {running ? (
              <span className="step-spinner" />
            ) : isError ? (
              <Icon name="alert" size={12} />
            ) : (
              <Icon name="check" size={12} />
            )}
          </span>
          <span className="section-arrow">{open ? '▲' : '▼'}</span>
        </span>
      </button>
      <div className={`section-detail${open ? ' open' : ''}`}>
        <div className="workflow-detail">
          {phases.length > 0 ? (
            <ul className="workflow-phases">
              {phases.map((p) => {
                const s = phaseStatus(p, phase, phases, workflowDone);
                return (
                  <li key={p} className={`workflow-phase-item status-${s}`}>
                    <div className="workflow-phase-row">
                      <span className="workflow-phase-name">{p}</span>
                      <span className="workflow-phase-status">{statusLabel(s)}</span>
                    </div>
                  </li>
                );
              })}
            </ul>
          ) : null}
          {log.length > 0 ? (
            <ul className="workflow-log">
              {log.slice(-8).map((line, i) => (
                <li key={`${line}-${i}`}>{line}</li>
              ))}
            </ul>
          ) : (
            <div className="workflow-log mute">暂无日志</div>
          )}
        </div>
      </div>
    </div>
  );
}
