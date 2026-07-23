import React, { useState, useCallback, useEffect } from 'react';
import type { MessageBlock } from '../../stores/chat-store';
import Markdown from '../shared/Markdown';
import WidgetFrame from '../tools/WidgetFrame';
import DelegationCard from './DelegationCard';
import PlanCard from './PlanCard';
import './TraceCard.css';

interface Props {
  blocks: MessageBlock[];
}

/** Chevron SVG for trace headers */
const Chevron = () => (
  <svg className="t-chev" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="9 18 15 12 9 6" />
  </svg>
);

/** Check SVG for completed nodes */
const CheckNode = ({ size = 10 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="20 6 9 17 4 12" />
  </svg>
);

function renderContentBlock(b: MessageBlock, i: number) {
  if (b.type === 'text') {
    return <div key={i} className="final-content block-text"><Markdown text={b.text || ''} /></div>;
  }
  if (b.type === 'widget' && b.widget) {
    return <div key={i} className="block-widget"><WidgetFrame widget={b.widget} /></div>;
  }
  if (b.type === 'video' && b.videoUrl) {
    return (
      <div key={i} className="block-widget">
        <video controls preload="metadata" aria-label="生成的视频"
          style={{ width: '100%', maxHeight: 480, aspectRatio: '16/9', borderRadius: 'var(--radius-sm)', background: '#000' }}
          src={b.videoUrl} />
      </div>
    );
  }
  if (b.type === 'image' && b.imageUrl) {
    return (
      <div key={i} className="block-image">
        <img src={b.imageUrl} alt="生成的图片" loading="lazy"
          style={{ width: '100%', maxHeight: 480, objectFit: 'contain', borderRadius: 'var(--radius-sm)', display: 'block' }} />
      </div>
    );
  }
  return null;
}

export default function TraceCard({ blocks }: Props) {
  // think/tool/skill/delegation/plan are reasoning steps.
  // Text blocks stay as content blocks — rendered in trace-content area (streaming-friendly).
  const isStep = (b: MessageBlock) => {
    if (
      b.type !== 'think' &&
      b.type !== 'tool' &&
      b.type !== 'skill' &&
      b.type !== 'delegation' &&
      b.type !== 'plan'
    ) {
      return false;
    }
    return b.turnPhase ? b.turnPhase === 'intermediate' : true;
  };
  const stepBlocks = blocks.filter(isStep);
  // Non-step blocks rendered below the rail (text/widget/video/image).
  // Intermediate text flows here as streaming content during reasoning.
  const contentBlocks = blocks.filter((b) => !isStep(b));

  // Delegation/plan render as full cards; think/tool/skill as compact rail nodes
  // Tools with planStepId are grouped under their plan step, not shown flat.
  const compactStepBlocks = stepBlocks.filter(
    (b) => b.type !== 'delegation' && b.type !== 'plan' && !b.planStepId
  );
  const delegationBlocks = stepBlocks.filter((b) => b.type === 'delegation');
  const planBlocks = stepBlocks.filter((b) => b.type === 'plan');

  // Build map: stepId → tool blocks (for PlanCard grouping)
  const planToolsMap = React.useMemo(() => {
    const map = new Map<string, MessageBlock[]>();
    for (const b of stepBlocks) {
      if (b.planStepId) {
        const arr = map.get(b.planStepId) || [];
        arr.push(b);
        map.set(b.planStepId, arr);
      }
    }
    return map;
  }, [stepBlocks]);

  const [traceOpen, setTraceOpen] = useState(true);
  const [openSteps, setOpenSteps] = useState<Set<number>>(new Set());

  useEffect(() => {
    if (compactStepBlocks.length === 0) return;
    setOpenSteps((prev) => {
      const next = new Set(prev);
      for (let i = 0; i < compactStepBlocks.length; i++) {
        if (compactStepBlocks[i].status === 'running') next.add(i);
        else if (compactStepBlocks[i].status === 'done') next.delete(i);
      }
      return next;
    });
  }, [compactStepBlocks]);

  const toggleStep = useCallback((i: number) => {
    setOpenSteps((prev) => {
      const next = new Set(prev);
      next.has(i) ? next.delete(i) : next.add(i);
      return next;
    });
  }, []);

  const hasRunning = stepBlocks.some((b) => b.status === 'running')
    || contentBlocks.some((b) => b.status === 'running');

  let headLabel = '思考中…';
  if (planBlocks.some((b) => b.status === 'running')) {
    headLabel = '执行计划 · 进行中';
  } else if (delegationBlocks.some((b) => b.status === 'running')) {
    headLabel = '协调专家 · 进行中';
  } else if (compactStepBlocks.some((b) => b.status === 'running')) {
    const running = compactStepBlocks.find((b) => b.status === 'running')!;
    headLabel = `${running.label || '处理'} · 进行中`;
  } else if (stepBlocks.length > 0) {
    headLabel = `推理完成 · ${stepBlocks.length} 步`;
  }

  if (stepBlocks.length === 0 && contentBlocks.length > 0) {
    return <>{contentBlocks.map((b, i) => renderContentBlock(b, i))}</>;
  }

  // When only delegation/plan exists (no compact steps), still render as trace card
  if (stepBlocks.length === 0 && delegationBlocks.length === 0 && planBlocks.length === 0 && contentBlocks.length === 0) {
    return null;
  }

  return (
    <div className={`trace${traceOpen ? '' : ' collapsed'}`}>
      <button
        type="button"
        className="trace-head"
        onClick={() => setTraceOpen((v) => !v)}
        aria-expanded={traceOpen}
      >
        <span className="thead-ic">
          {hasRunning ? <span className="t-spin" /> : <CheckNode size={13} />}
        </span>
        <span className="thead-label">{headLabel}</span>
        <Chevron />
      </button>

      {/* Step rail: think / tool / skill / delegation / plan — all as t-step nodes */}
      {stepBlocks.length > 0 && (
        <div className="trace-rail">
          {stepBlocks.map((block, i) => {
            if (block.type === 'delegation') {
              return (
                <DelegationCard
                  key={`del-${i}`}
                  mode={block.mode}
                  status={block.status}
                  agents={block.agents}
                  isError={block.isError}
                />
              );
            }
            if (block.type === 'plan') {
              return (
                <PlanCard
                  key={`plan-${i}`}
                  title={block.planTitle || block.label}
                  status={block.status}
                  planStatus={block.planStatus}
                  done={block.planDone}
                  total={block.planTotal}
                  steps={block.planSteps}
                  isError={block.isError}
                  stepTools={planToolsMap}
                />
              );
            }
            const isThink = block.type === 'think';
            const isSkill = block.type === 'skill';
            const nodeClass = isThink ? 'think' : isSkill ? 'skill' : 'tool';
            const kindLabel = isThink ? '思考' : isSkill ? (block.label || '技能') : (block.label || '工具');
            const isRunning = block.status === 'running';
            // Index into compactStepBlocks for open/close state
            const compactIdx = compactStepBlocks.indexOf(block);
            const isOpen = openSteps.has(compactIdx);

            return (
              <div key={i} className={`t-step${isOpen ? ' open' : ''}`}>
                <span className={`t-node ${nodeClass} ${isRunning ? 'running' : 'done'}`}>
                  {isRunning ? <span className="t-spin" /> : <CheckNode />}
                </span>
                <button
                  type="button"
                  className="t-head"
                  onClick={() => toggleStep(compactIdx)}
                  aria-expanded={isOpen}
                >
                  <span className="t-kind">{kindLabel}</span>
                  <span className="t-sub">
                    {isRunning
                      ? (block.detail?.slice(0, 40) || '处理中…')
                      : (block.detail
                        ? (block.detail.length > 60 ? `${block.detail.slice(0, 60)}…` : block.detail)
                        : '完成')}
                  </span>
                  <Chevron />
                </button>
                <div className="t-body">
                  <div className={`t-body-inner${block.isError ? ' t-error' : ''}`}>
                    {block.detail || ''}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Other content blocks (widget/video/image, excluding text) */}
      {contentBlocks.length > 0 && (
        <div className="trace-content">
          {contentBlocks.map((b, i) => renderContentBlock(b, i))}
        </div>
      )}
    </div>
  );
}
