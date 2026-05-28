import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useChatStore, type ToolStep as ToolStepType } from '../../stores/chat-store';
import ToolStep from './ToolStep';
import Icon from '../shared/Icon';
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
  const detailId = `step-detail-${step.id}`;

  useEffect(() => {
    if (expanded && detailRef.current) {
      detailRef.current.scrollTop = detailRef.current.scrollHeight;
    }
  }, [step.detail, expanded]);

  const running = step.status === 'running';
  const done = step.status === 'done';

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
      <button
        className="section-summary"
        onClick={onToggle}
        aria-expanded={expanded}
        aria-controls={detailId}
        aria-label={`${label}详情`}
      >
        <span className="section-label">
          <span className="section-icon">
            {step.type === 'think' ? <Icon name="think" size={12} /> : <Icon name="tool" size={12} />}
          </span>
          {label}
          {statusSuffix && <span className="section-status-text"> {statusSuffix}</span>}
          {running && <Icon name="spinner" size={12} className="section-spinner-icon" />}
        </span>
        <span className="section-right">
          <span className="section-status-icon">
            {done && (step.isError ? <Icon name="alert" size={12} /> : <Icon name="check" size={12} />)}
          </span>
          <span className="section-arrow">
            {expanded ? <Icon name="chevron-up" size={12} /> : <Icon name="chevron-down" size={12} />}
          </span>
        </span>
      </button>
      <div id={detailId} className={`section-detail${expanded ? ' open' : ''}`} ref={detailRef} role="region">
        <ToolStep step={step} showHeader={false} />
      </div>
    </div>
  );
}

export default function StepsPanel({ steps: propSteps }: Props) {
  const storeSteps = useChatStore((s) => s.steps);
  const currentText = useChatStore((s) => s.currentText);
  const steps = propSteps ?? storeSteps;

  // Auto-expand running steps so user sees live progress.
  // When nothing is running, keep the most recent step expanded.
  // manualOpen: user explicitly expanded this step
  // manualClosed: user explicitly collapsed this step (overrides auto)
  const [manualOpen, setManualOpen] = useState<Set<string>>(new Set());
  const [manualClosed, setManualClosed] = useState<Set<string>>(new Set());

  const getAutoExpandedId = useCallback(() => {
    // Only auto-expand the currently running step.
    // Done steps stay collapsed so the user sees clean final output.
    const running = steps.find((s) => s.status === 'running');
    return running ? running.id : null;
  }, [steps]);

  const hasRunning = steps.some((s) => s.status === 'running');
  const isStreaming = useChatStore((s) => s.isStreaming);

  // Reset manual overrides when steps reset
  useEffect(() => {
    if (steps.length === 0) {
      setManualOpen(new Set());
      setManualClosed(new Set());
    }
  }, [steps.length]);

  if (steps.length === 0) return null;

  return (
    <div className="steps-panel">
      {steps.map((step) => {
        const autoId = getAutoExpandedId();
        // manualClosed overrides auto; manualOpen overrides both
        const expanded = manualOpen.has(step.id) ? true
          : manualClosed.has(step.id) ? false
          : step.id === autoId;

        const handleToggle = () => {
          if (expanded) {
            // Currently expanded → user wants to collapse
            setManualOpen((prev) => { const n = new Set(prev); n.delete(step.id); return n; });
            setManualClosed((prev) => { const n = new Set(prev); n.add(step.id); return n; });
          } else {
            // Currently collapsed → user wants to expand
            setManualClosed((prev) => { const n = new Set(prev); n.delete(step.id); return n; });
            setManualOpen((prev) => { const n = new Set(prev); n.add(step.id); return n; });
          }
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
