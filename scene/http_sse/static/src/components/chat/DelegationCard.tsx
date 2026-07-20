import React, { useState } from 'react';
import type { DelegationAgentItem } from '../../stores/chat-store';
import './DelegationCard.css';

interface Props {
  mode?: string;
  status?: 'running' | 'done';
  agents?: DelegationAgentItem[];
  isError?: boolean;
}

export default function DelegationCard({ mode, status, agents = [], isError }: Props) {
  const [open, setOpen] = useState(status === 'running');
  const running = status === 'running';
  const title = running ? '协调专家中…' : isError ? '专家协调失败' : '专家协调完成';

  return (
    <div className={`delegation-card${running ? ' running' : ''}${isError ? ' error' : ''}`}>
      <button
        type="button"
        className="delegation-summary"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="delegation-title">
          {running && <span className="delegation-spinner" aria-hidden />}
          {title}
          {mode ? <span className="delegation-mode">{mode}</span> : null}
        </span>
        <span className="delegation-arrow">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <ul className="delegation-agents">
          {agents.length === 0 ? (
            <li className="delegation-agent mute">等待专家响应…</li>
          ) : (
            agents.map((a) => (
              <li key={`${a.agent}-${a.task || ''}`} className={`delegation-agent status-${a.status}`}>
                <div className="delegation-agent-row">
                  <strong>{a.agent}</strong>
                  <span className="delegation-agent-status">{a.status}</span>
                </div>
                {a.task ? <div className="delegation-agent-task">{a.task}</div> : null}
                {a.summary ? <div className="delegation-agent-summary">{a.summary}</div> : null}
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
