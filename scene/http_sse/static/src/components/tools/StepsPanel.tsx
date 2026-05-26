import React, { useState } from 'react';
import { useChatStore, type ToolStep as ToolStepType } from '../../stores/chat-store';
import ToolStep from './ToolStep';
import './StepsPanel.css';

interface Props {
  steps?: ToolStepType[];
}

function StepSection({ step }: { step: ToolStepType }) {
  const [expanded, setExpanded] = useState(false);
  const icon = step.type === 'think' ? '[#]' : '[%]';
  const running = step.status === 'running';
  const done = step.status === 'done';
  const statusIcon = done ? (step.isError ? '[!]' : '[x]') : '';

  let label = step.label;
  if (step.type === 'think') label = '思考过程';

  let statusSuffix = '';
  if (running) {
    const elapsed = Math.floor((Date.now() - step.startTime) / 1000);
    statusSuffix = `${elapsed}s`;
    if (step.isSlow) statusSuffix += ' (slow)';
  }

  return (
    <div className={`step-section${expanded ? ' open' : ''}`}>
      <button className="section-summary" onClick={() => setExpanded((v) => !v)}>
        <span className="section-label">
          <span className="section-icon">{icon}</span>
          {label}
          {statusSuffix && <span className="section-status-text"> {statusSuffix}</span>}
        </span>
        <span className="section-right">
          {running && <span className="section-spinner" />}
          <span className="section-arrow">{expanded ? '[-]' : '[+]'}</span>
        </span>
      </button>
      {expanded && (
        <div className="section-detail">
          <ToolStep step={step} showHeader={false} />
        </div>
      )}
    </div>
  );
}

export default function StepsPanel({ steps: propSteps }: Props) {
  const storeSteps = useChatStore((s) => s.steps);
  const steps = propSteps ?? storeSteps;

  if (steps.length === 0) return null;

  return (
    <div className="steps-panel">
      {steps.map((step) => (
        <StepSection key={step.id} step={step} />
      ))}
    </div>
  );
}
