import React, { useState, useCallback, useEffect, useRef } from 'react';
import type { MessageBlock } from '../../stores/chat-store';
import Markdown from '../shared/Markdown';
import WidgetFrame from '../tools/WidgetFrame';
import Icon from '../shared/Icon';
import DelegationCard from './DelegationCard';
import '../tools/StepsPanel.css';
import '../tools/ToolStep.css';

interface Props {
  blocks: MessageBlock[];
}

export default function BlocksRenderer({ blocks }: Props) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const prevLen = useRef(0);

  // Auto-expand running blocks, collapse done blocks
  useEffect(() => {
    if (blocks.length === 0) return;
    setExpanded((prev) => {
      const next = new Set(prev);
      for (let i = 0; i < blocks.length; i++) {
        if (blocks[i].status === 'running') next.add(i);
        else if (blocks[i].status === 'done') next.delete(i);
      }
      return next;
    });
  }, [blocks]);

  const toggle = useCallback((i: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(i) ? next.delete(i) : next.add(i);
      return next;
    });
  }, []);

  return (
    <div className="steps-panel">
      {blocks.map((b, i) => {
        if (b.type === 'text') {
          return (
            <div key={i} className="final-content block-text">
              <Markdown text={b.text || ''} />
            </div>
          );
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
          return (
            <div key={i} className="block-widget">
              <WidgetFrame widget={b.widget} />
            </div>
          );
        }

        if (b.type === 'video' && b.videoUrl) {
          return (
            <div key={i} className="block-widget">
              <div className="video-container" style={{ margin: '8px 0' }}>
                <video
                  controls
                  preload="metadata"
                  aria-label="生成的视频"
                  style={{
                    width: '100%',
                    maxHeight: 480,
                    aspectRatio: '16 / 9',
                    borderRadius: 'var(--radius-sm)',
                    background: '#000',
                  }}
                  src={b.videoUrl}
                />
                <div style={{
                  marginTop: 6,
                  fontSize: 12,
                  color: 'var(--mute)',
                  fontFamily: 'var(--font-mono)',
                  display: 'flex',
                  gap: 12,
                  alignItems: 'center',
                }}>
                  {b.videoSize && <span>{b.videoSize}</span>}
                  {b.videoSeconds && <span>{b.videoSeconds}s</span>}
                  <a
                    href={b.videoUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: 'var(--accent)' }}
                  >
                    下载
                  </a>
                </div>
              </div>
            </div>
          );
        }

        const isThink = b.type === 'think';
        const label = isThink ? '思考过程' : (b.label || '工具');
        const icon = isThink ? 'think' : 'tool';
        const isOpen = expanded.has(i);
        const running = b.status === 'running';
        const detailId = `block-detail-${i}`;

        return (
          <div key={i} className={`step-section done-ok${isOpen ? ' open' : ''}${running ? ' active' : ''}`}>
            <button
              className="section-summary"
              onClick={() => toggle(i)}
              aria-expanded={isOpen}
              aria-controls={detailId}
            >
              <span className="section-label">
                <span className="section-icon"><Icon name={icon} size={12} /></span>
                {label}
              </span>
              <span className="section-right">
                <span className="section-status-icon">
                  {running ? (
                    <span className="step-spinner" />
                  ) : b.isError ? (
                    <Icon name="alert" size={12} />
                  ) : (
                    <Icon name="check" size={12} />
                  )}
                </span>
                <span className="section-arrow">{isOpen ? '▲' : '▼'}</span>
              </span>
            </button>
            <div
              id={detailId}
              className={`section-detail${isOpen ? ' open' : ''}`}
            >
              <div className={`step-detail${b.isError ? ' error' : ''}`}>
                {b.detail}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
