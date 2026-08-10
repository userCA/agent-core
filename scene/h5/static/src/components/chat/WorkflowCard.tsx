import React, { useState } from 'react';
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
  const head = isError
    ? '工作流失败'
    : running
      ? (name ? `工作流 · ${name}` : '工作流执行中')
      : workflowStatus === 'aborted'
        ? '工作流已中止'
        : workflowStatus === 'failed'
          ? '工作流失败'
          : (name ? `工作流 · ${name}` : '工作流已完成');

  return (
    <div className={`workflow-card${running ? ' running' : ''}${isError ? ' error' : ''}`}>
      <button
        type="button"
        className="workflow-summary"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="workflow-title">
          {running && <span className="workflow-spinner" aria-hidden />}
          {head}
          {phase ? <span className="workflow-phase">{phase}</span> : null}
          {agentProgress ? <span className="workflow-progress">{agentProgress}</span> : null}
        </span>
        <span className="workflow-arrow">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className="workflow-body">
          {phases.length > 0 ? (
            <ul className="workflow-phases">
              {phases.map((p) => (
                <li
                  key={p}
                  className={`workflow-phase-item${p === phase ? ' current' : ''}`}
                >
                  {p}
                </li>
              ))}
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
      )}
    </div>
  );
}
