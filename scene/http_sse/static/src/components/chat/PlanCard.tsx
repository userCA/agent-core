import React, { useState } from 'react';
import type { PlanStepItem } from '../../stores/chat-store';
import './PlanCard.css';

interface Props {
  title?: string;
  status?: 'running' | 'done';
  planStatus?: string;
  done?: number;
  total?: number;
  steps?: PlanStepItem[];
  isError?: boolean;
}

export default function PlanCard({
  title,
  status,
  planStatus,
  done = 0,
  total = 0,
  steps = [],
  isError,
}: Props) {
  const [open, setOpen] = useState(status === 'running');
  const running = status === 'running';
  const progress = total > 0 ? `${done}/${total}` : '';
  const head = isError
    ? '计划更新失败'
    : running
      ? (title || '执行计划')
      : planStatus === 'cancelled'
        ? '计划已取消'
        : planStatus === 'completed'
          ? '计划已完成'
          : (title || '执行计划');

  return (
    <div className={`plan-card${running ? ' running' : ''}${isError ? ' error' : ''}`}>
      <button
        type="button"
        className="plan-summary"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="plan-title">
          {running && <span className="plan-spinner" aria-hidden />}
          {head}
          {progress ? <span className="plan-progress">{progress}</span> : null}
        </span>
        <span className="plan-arrow">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <ul className="plan-steps">
          {steps.length === 0 ? (
            <li className="plan-step mute">暂无步骤</li>
          ) : (
            steps.map((s) => (
              <li key={s.id} className={`plan-step status-${s.status}`}>
                <div className="plan-step-row">
                  <strong>{s.title}</strong>
                  <span className="plan-step-status">{s.status}</span>
                </div>
                {s.detail ? <div className="plan-step-detail">{s.detail}</div> : null}
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
