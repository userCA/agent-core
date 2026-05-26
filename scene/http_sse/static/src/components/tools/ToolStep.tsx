import React from 'react';
import type { ToolStep as ToolStepType } from '../../stores/chat-store';
import MediaDetector from '../shared/MediaDetector';
import './ToolStep.css';

interface Props {
  step: ToolStepType;
  showHeader?: boolean;
}

export default function ToolStep({ step, showHeader = true }: Props) {
  const elapsed = Math.floor((Date.now() - step.startTime) / 1000);
  const icon = step.type === 'think' ? '[#]' : '[%]';
  const statusIcon = step.status === 'done' ? (step.isError ? '[!]' : '[x]') : '';

  return (
    <div className={`tool-step ${step.status}`}>
      {showHeader && (
        <div className="step-header">
          <span className="step-icon">{icon}</span>
          <span className="step-label">{step.label}</span>
          {step.status === 'running' && (
            <span className="step-elapsed">{elapsed}s</span>
          )}
          {step.isSlow && <span className="step-slow">(slow)</span>}
          <span className="step-status">{statusIcon}</span>
          {step.status === 'running' && <span className="step-spinner" />}
        </div>
      )}
      {step.detail && (
        <div className={`step-detail ${step.isError ? 'error' : ''}`}>
          <MediaDetector text={step.detail} />
        </div>
      )}
    </div>
  );
}
