import React, { useState, useCallback } from 'react';
import type { MessageBlock } from '../../stores/chat-store';
import Markdown from '../shared/Markdown';
import Icon from '../shared/Icon';
import '../tools/StepsPanel.css';
import '../tools/ToolStep.css';

interface Props {
  blocks: MessageBlock[];
}

export default function BlocksRenderer({ blocks }: Props) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

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

        const isThink = b.type === 'think';
        const label = isThink ? '思考过程' : (b.label || '工具');
        const icon = isThink ? 'think' : 'tool';
        const isOpen = expanded.has(i);
        const detailId = `block-detail-${i}`;

        return (
          <div key={i} className={`step-section done-ok${isOpen ? ' open' : ''}`}>
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
                  {b.isError ? <Icon name="alert" size={12} /> : <Icon name="check" size={12} />}
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
