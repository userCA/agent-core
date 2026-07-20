import React, { useState, useCallback, useEffect } from 'react';
import type { MessageBlock } from '../../stores/chat-store';
import Markdown from '../shared/Markdown';
import WidgetFrame from '../tools/WidgetFrame';
import DelegationCard from './DelegationCard';
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
  if (b.type === 'delegation') {
    return (
      <DelegationCard
        key={i}
        mode={b.mode}
        status={b.status}
        agents={b.agents}
        isError={b.isError}
      />
    );
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
  // Only think/tool/skill are reasoning steps. turnPhase alone must not promote
  // text/delegation/media into the tool rail (streaming text is intermediate until message.end).
  const isStep = (b: MessageBlock) => {
    if (b.type !== 'think' && b.type !== 'tool' && b.type !== 'skill') return false;
    return b.turnPhase ? b.turnPhase === 'intermediate' : true;
  };
  const stepBlocks = blocks.filter(isStep);
  const contentBlocks = blocks.filter((b) => !isStep(b));

  const [traceOpen, setTraceOpen] = useState(true);
  const [openSteps, setOpenSteps] = useState<Set<number>>(new Set());

  useEffect(() => {
    if (stepBlocks.length === 0) return;
    setOpenSteps((prev) => {
      const next = new Set(prev);
      for (let i = 0; i < stepBlocks.length; i++) {
        if (stepBlocks[i].status === 'running') next.add(i);
        else if (stepBlocks[i].status === 'done') next.delete(i);
      }
      return next;
    });
  }, [stepBlocks]);

  const toggleStep = useCallback((i: number) => {
    setOpenSteps((prev) => {
      const next = new Set(prev);
      next.has(i) ? next.delete(i) : next.add(i);
      return next;
    });
  }, []);

  const hasRunning = stepBlocks.some((b) => b.status === 'running')
    || contentBlocks.some((b) => b.type === 'delegation' && b.status === 'running');

  let headLabel = '思考中…';
  if (contentBlocks.some((b) => b.type === 'delegation' && b.status === 'running')) {
    headLabel = '协调专家 · 进行中';
  } else if (stepBlocks.some((b) => b.status === 'running')) {
    const running = stepBlocks.find((b) => b.status === 'running')!;
    headLabel = `${running.label || '处理'} · 进行中`;
  } else if (stepBlocks.length > 0) {
    headLabel = `推理完成 · ${stepBlocks.length} 步`;
  }

  if (stepBlocks.length === 0 && contentBlocks.length > 0) {
    return <>{contentBlocks.map((b, i) => renderContentBlock(b, i))}</>;
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

      <div className="trace-rail">
        {stepBlocks.map((block, i) => {
          const isThink = block.type === 'think';
          const isSkill = block.type === 'skill';
          const nodeClass = isThink ? 'think' : isSkill ? 'skill' : 'tool';
          const kindLabel = isThink ? '思考' : isSkill ? (block.label || '技能') : (block.label || '工具');
          const isRunning = block.status === 'running';
          const isOpen = openSteps.has(i);

          return (
            <div key={i} className={`t-step${isOpen ? ' open' : ''}`}>
              <span className={`t-node ${nodeClass} ${isRunning ? 'running' : 'done'}`}>
                {isRunning ? <span className="t-spin" /> : <CheckNode />}
              </span>
              <button
                type="button"
                className="t-head"
                onClick={() => toggleStep(i)}
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

      {contentBlocks.length > 0 && (
        <div className="trace-content">
          {contentBlocks.map((b, i) => renderContentBlock(b, i))}
        </div>
      )}
    </div>
  );
}
