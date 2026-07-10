import React, { useState, useCallback, useEffect } from 'react';
import type { MessageBlock } from '../../stores/chat-store';
import Markdown from '../shared/Markdown';
import WidgetFrame from '../tools/WidgetFrame';
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

export default function TraceCard({ blocks }: Props) {
  // Separate step blocks (think/tool) from content blocks (text/widget/video/image)
  const stepBlocks = blocks.filter(b => b.type === 'think' || b.type === 'tool');
  const contentBlocks = blocks.filter(b => b.type === 'text' || b.type === 'widget' || b.type === 'video' || b.type === 'image');

  const [traceOpen, setTraceOpen] = useState(true);
  const [openSteps, setOpenSteps] = useState<Set<number>>(new Set());

  // Auto-expand running blocks, collapse done blocks
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

  const hasRunning = stepBlocks.some((b) => b.status === 'running');

  // Header label
  let headLabel = '思考中…';
  if (hasRunning) {
    const running = stepBlocks.find((b) => b.status === 'running')!;
    headLabel = `${running.label || '处理'} · 进行中`;
  } else if (stepBlocks.length > 0 && !hasRunning) {
    headLabel = `推理完成 · ${stepBlocks.length} 步`;
  }

  // If no step blocks, just render content blocks inline
  if (stepBlocks.length === 0 && contentBlocks.length > 0) {
    return (
      <>
        {contentBlocks.map((b, i) => {
          if (b.type === 'text') return <div key={i} className="final-content block-text"><Markdown text={b.text || ''} /></div>;
          if (b.type === 'widget' && b.widget) return <div key={i} className="block-widget"><WidgetFrame widget={b.widget} /></div>;
          if (b.type === 'video' && b.videoUrl) return (
            <div key={i} className="block-widget">
              <video controls preload="metadata" aria-label="生成的视频"
                style={{ width: '100%', maxHeight: 480, aspectRatio: '16/9', borderRadius: 'var(--radius-sm)', background: '#000' }}
                src={b.videoUrl} />
            </div>
          );
          if (b.type === 'image' && b.imageUrl) return (
            <div key={i} className="block-image">
              <img src={b.imageUrl} alt="生成的图片" loading="lazy"
                style={{ width: '100%', maxHeight: 480, objectFit: 'contain', borderRadius: 'var(--radius-sm)', display: 'block' }} />
            </div>
          );
          return null;
        })}
      </>
    );
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
          {hasRunning ? (
            <span className="t-spin" />
          ) : (
            <CheckNode size={13} />
          )}
        </span>
        <span className="thead-label">{headLabel}</span>
        <Chevron />
      </button>

      <div className="trace-rail">
        {stepBlocks.map((block, i) => {
          const isThink = block.type === 'think';
          const nodeClass = isThink ? 'think' : 'tool';
          const kindLabel = isThink ? '思考' : (block.label || '工具');
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
                  {isRunning ? (block.detail?.slice(0, 40) || '处理中…') : '完成'}
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

      {/* Content blocks rendered below the trace card */}
      {contentBlocks.length > 0 && (
        <div className="trace-content">
          {contentBlocks.map((b, i) => {
            if (b.type === 'text') return <div key={i} className="final-content block-text"><Markdown text={b.text || ''} /></div>;
            if (b.type === 'widget' && b.widget) return <div key={i} className="block-widget"><WidgetFrame widget={b.widget} /></div>;
            if (b.type === 'video' && b.videoUrl) return (
              <div key={i} className="block-widget">
                <video controls preload="metadata" aria-label="生成的视频"
                  style={{ width: '100%', maxHeight: 480, aspectRatio: '16/9', borderRadius: 'var(--radius-sm)', background: '#000' }}
                  src={b.videoUrl} />
              </div>
            );
            if (b.type === 'image' && b.imageUrl) return (
              <div key={i} className="block-image">
                <img src={b.imageUrl} alt="生成的图片" loading="lazy"
                  style={{ width: '100%', maxHeight: 480, objectFit: 'contain', borderRadius: 'var(--radius-sm)', display: 'block' }} />
              </div>
            );
            return null;
          })}
        </div>
      )}
    </div>
  );
}
