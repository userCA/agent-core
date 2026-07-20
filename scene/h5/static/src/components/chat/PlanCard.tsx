import React, { useState } from 'react';
import type { PlanStepItem, MessageBlock } from '../../stores/chat-store';
import './PlanCard.css';

interface Props {
  title?: string;
  status?: 'running' | 'done';
  planStatus?: string;
  done?: number;
  total?: number;
  steps?: PlanStepItem[];
  isError?: boolean;
  stepTools?: Map<string, MessageBlock[]>;
}

const CheckNode = ({ size = 10 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="20 6 9 17 4 12" />
  </svg>
);

const Chevron = () => (
  <svg className="t-chev" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="9 18 15 12 9 6" />
  </svg>
);

export default function PlanCard({
  title,
  status,
  planStatus,
  done = 0,
  total = 0,
  steps = [],
  isError,
  stepTools,
}: Props) {
  const running = status === 'running';
  const [open, setOpen] = useState(running);
  const progress = total > 0 ? `${done}/${total}` : '';
  const head = isError
    ? '计划失败'
    : planStatus === 'cancelled'
      ? '计划已取消'
      : planStatus === 'completed'
        ? '计划已完成'
        : (title || '执行计划');
  const detail = progress
    ? `进度 ${progress}`
    : running
      ? '进行中…'
      : '完成';

  return (
    <div className={`t-step plan-step-card${open ? ' open' : ''}${isError ? ' plan-error' : ''}`}>
      <span className={`t-node plan-node ${running ? 'running' : 'done'}`}>
        {running ? <span className="t-spin" /> : <CheckNode />}
      </span>
      <button
        type="button"
        className="t-head"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="t-kind">{head}</span>
        <span className="t-sub">{detail}</span>
        <Chevron />
      </button>
      <div className="t-body">
        <div className={`t-body-inner${isError ? ' t-error' : ''}`}>
          {steps.length === 0 ? (
            <span className="plan-mute">暂无步骤</span>
          ) : (
            <ul className="plan-steps-list">
              {steps.map((s) => {
                const tools = stepTools?.get(s.id) || [];
                return (
                  <li key={s.id} className={`plan-step-item status-${s.status}`}>
                    <div className="plan-step-row">
                      <strong>{s.title}</strong>
                      <span className="plan-step-status">{s.status}</span>
                    </div>
                    {s.detail ? <div className="plan-step-detail">{s.detail}</div> : null}
                    {tools.length > 0 && (
                      <div className="plan-step-tools">
                        {tools.map((t, ti) => (
                          <div key={ti} className={`plan-tool-item ${t.status === 'running' ? 'running' : 'done'}`}>
                            <span className="plan-tool-icon">
                              {t.status === 'running'
                                ? <span className="t-spin" style={{ width: 8, height: 8 }} />
                                : <CheckNode size={8} />}
                            </span>
                            <span className="plan-tool-name">{t.toolName || t.label || 'tool'}</span>
                            {t.detail && (
                              <span className="plan-tool-detail">
                                {t.detail.length > 50 ? `${t.detail.slice(0, 50)}…` : t.detail}
                              </span>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
