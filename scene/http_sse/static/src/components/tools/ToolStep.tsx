import React from 'react';
import type { ToolStep as ToolStepType } from '../../stores/chat-store';
import MediaDetector from '../shared/MediaDetector';
import Icon from '../shared/Icon';
import './ToolStep.css';

interface Props {
  step: ToolStepType;
  showHeader?: boolean;
}

export default function ToolStep({ step, showHeader = true }: Props) {
  const elapsed = Math.floor((Date.now() - step.startTime) / 1000);


  return (
    <div className={`tool-step ${step.status}`}>
      {showHeader && (
        <div className="step-header">
          <span className="step-icon">
            {step.type === 'think' ? <Icon name="think" size={12} /> : <Icon name="tool" size={12} />}
          </span>
          <span className="step-label">{step.label}</span>
          {step.status === 'running' && (
            <span className="step-elapsed">{elapsed}s</span>
          )}
          {step.isSlow && <span className="step-slow">(slow)</span>}
          <span className="step-status">
            {step.status === 'done' && (step.isError ? <Icon name="alert" size={12} /> : <Icon name="check" size={12} />)}
          </span>
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
