import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useChatStore, type ToolStep as ToolStepType } from '../../stores/chat-store';
import ToolStep from './ToolStep';
import './StepsPanel.css';

interface Props {
  steps?: ToolStepType[];
}

function StepSection({
  step,
  expanded,
  onToggle,
}: {
  step: ToolStepType;
  expanded: boolean;
  onToggle: () => void;
}) {
  const detailRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (expanded && detailRef.current) {
      detailRef.current.scrollTop = detailRef.current.scrollHeight;
    }
  }, [step.detail, expanded]);

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
    <div className={`step-section${expanded ? ' open' : ''}${running ? ' active' : ''}`}>
      <button className="section-summary" onClick={onToggle}>
        <span className="section-label">
          <span className="section-icon">{icon}</span>
          {label}
          {statusSuffix && <span className="section-status-text"> {statusSuffix}</span>}
          {running && <span className="section-spinner" />}
        </span>
        <span className="section-right">
          <span className="section-status-icon">{statusIcon}</span>
          <span className="section-arrow">{expanded ? '[-]' : '[+]'}</span>
        </span>
      </button>
      {expanded && (
        <div className="section-detail" ref={detailRef}>
          <ToolStep step={step} showHeader={false} />
        </div>
      )}
    </div>
  );
}

export default function StepsPanel({ steps: propSteps }: Props) {
  const storeSteps = useChatStore((s) => s.steps);
  const currentText = useChatStore((s) => s.currentText);
  const steps = propSteps ?? storeSteps;

  // Always expand the latest step (running or most recently done).
  // Collapse all once text output begins.
  const [manualExpanded, setManualExpanded] = useState<Set<string>>(new Set());

  const getAutoExpandedId = useCallback(() => {
    if (currentText.length > 0) return null;
    if (steps.length === 0) return null;
    return steps[steps.length - 1].id;
  }, [steps, currentText]);

  const hasRunning = steps.some((s) => s.status === 'running');
  const isStreaming = useChatStore((s) => s.isStreaming);

  // Reset manual overrides when steps reset
  useEffect(() => {
    if (steps.length === 0) setManualExpanded(new Set());
  }, [steps.length]);

  if (steps.length === 0) return null;

  return (
    <div className="steps-panel">
      {steps.map((step) => {
        const autoId = getAutoExpandedId();
        const expanded = manualExpanded.has(step.id) ? true : step.id === autoId;

        const handleToggle = () => {
          setManualExpanded((prev) => {
            const next = new Set(prev);
            if (next.has(step.id)) {
              next.delete(step.id);
            } else {
              next.add(step.id);
            }
            return next;
          });
        };

        return (
          <StepSection
            key={step.id}
            step={step}
            expanded={expanded}
            onToggle={handleToggle}
          />
        );
      })}
      {isStreaming && !hasRunning && currentText.length === 0 && (
        <div className="step-waiting">waiting for next...</div>
      )}
    </div>
  );
}
