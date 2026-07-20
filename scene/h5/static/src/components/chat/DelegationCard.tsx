import React, { useState } from 'react';
import type { DelegationAgentItem } from '../../stores/chat-store';
import './DelegationCard.css';

interface Props {
  mode?: string;
  status?: 'running' | 'done';
  agents?: DelegationAgentItem[];
  isError?: boolean;
}

/** Check SVG — same as TraceCard */
const CheckNode = ({ size = 10 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="20 6 9 17 4 12" />
  </svg>
);

/** Chevron SVG — same as TraceCard */
const Chevron = () => (
  <svg className="t-chev" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="9 18 15 12 9 6" />
  </svg>
);

export default function DelegationCard({ mode, status, agents = [], isError }: Props) {
  const running = status === 'running';
  const [open, setOpen] = useState(running);
  const title = running ? '协调专家' : isError ? '专家协调失败' : '专家协调完成';
  const detail = running
    ? (agents.length > 0 ? `${agents.length} 位专家${mode ? ` · ${mode}` : ''}` : '等待响应…')
    : (agents.length > 0 ? `${agents.length} 位专家${mode ? ` · ${mode}` : ''}` : '完成');

  return (
    <div className={`t-step del-step${open ? ' open' : ''}${isError ? ' del-error' : ''}`}>
      <span className={`t-node del-node ${running ? 'running' : 'done'}`}>
        {running ? <span className="t-spin" /> : <CheckNode />}
      </span>
      <button
        type="button"
        className="t-head"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="t-kind">{title}</span>
        <span className="t-sub">{detail}</span>
        <Chevron />
      </button>
      <div className="t-body">
        <div className={`t-body-inner${isError ? ' t-error' : ''}`}>
          {agents.length === 0 ? (
            <span className="del-mute">等待专家响应…</span>
          ) : (
            <ul className="del-agents">
              {agents.map((a) => (
                <li key={`${a.agent}-${a.task || ''}`} className={`del-agent status-${a.status}`}>
                  <div className="del-agent-row">
                    <strong>{a.agent}</strong>
                    <span className="del-agent-status">{a.status}</span>
                  </div>
                  {a.task ? <div className="del-agent-task">{a.task}</div> : null}
                  {a.summary ? <div className="del-agent-summary">{a.summary}</div> : null}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
