import React, { useCallback, useState } from 'react';
import { motion } from 'motion/react';
import type { ChatMessage } from '../../stores/chat-store';
import Markdown from '../shared/Markdown';
import TraceCard from './TraceCard';
import AudioPlayer from '../tools/AudioPlayer';
import Icon, { ICON_SIZES } from '../shared/Icon';
import TooltipWrap from '../shared/TooltipWrap';
import { useToastStore } from '../../stores/toast-store';
import './MessageBubble.css';

interface Props {
  message: ChatMessage;
}

/** Format timestamp as "h:mm AM/PM" */
function formatTime(ts: number): string {
  if (!ts) return '';
  return new Date(ts).toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
  });
}

/** Moon SVG avatar matching the prototype */
const MoonAvatar = () => (
  <div className="msg-avatar">
    <svg className="msg-avatar-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3c.132 0 .263 0 .393 0a7.5 7.5 0 0 0 7.92 12.446a9 9 0 1 1 -8.313 -12.454z"/>
      <path d="M12 8v4"/>
      <path d="M12 16h.01"/>
    </svg>
  </div>
);

export default function MessageBubble({ message }: Props) {
  const { role, content, usage, toolCallId, blocks, audios, timestamp } = message;
  const [copied, setCopied] = useState(false);
  const addToast = useToastStore((s) => s.addToast);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(content).then(() => {
      setCopied(true);
      addToast('已复制到剪贴板', 'success');
      setTimeout(() => setCopied(false), 2000);
    }).catch(() => {
      addToast('复制失败', 'error');
    });
  }, [content, addToast]);

  const timeStr = formatTime(timestamp);

  if (role === 'user') {
    return (
      <motion.div
        className="msg-row msg-row-user"
        layout
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
      >
        <div className="msg-col msg-col-user">
          {/* Image attachments */}
          {message.attachments && message.attachments.length > 0 && (
            <div className="user-attachments">
              {message.attachments.map((url, i) => (
                <img key={i} src={url} alt={`附件 ${i + 1}`} className="user-attachment-thumb" />
              ))}
            </div>
          )}
          <div className="bubble bubble-user">
            <pre className="user-text">{content}</pre>
          </div>
          {timeStr && <span className="msg-time msg-time-user">{timeStr}</span>}
        </div>
      </motion.div>
    );
  }

  if (role === 'error') {
    return (
      <motion.div
        className="msg-row msg-row-assistant"
        layout
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
      >
        <MoonAvatar />
        <div className="msg-col msg-col-assistant">
          <div className="bubble bubble-error">
            <Icon name="alert" size={ICON_SIZES.sm} style={{ color: 'var(--accent-plum)' }} /> {content}
          </div>
          {timeStr && <span className="msg-time msg-time-assistant">{timeStr}</span>}
        </div>
      </motion.div>
    );
  }

  if (role === 'tool') {
    return (
      <motion.div
        className="msg-row msg-row-assistant"
        layout
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
      >
        <MoonAvatar />
        <div className="msg-col msg-col-assistant">
          <div className="bubble bubble-tool">
            <Icon name="tool" size={ICON_SIZES.sm} /> <pre className="tool-text">{content}</pre>
          </div>
          {timeStr && <span className="msg-time msg-time-assistant">{timeStr}</span>}
        </div>
      </motion.div>
    );
  }

  // assistant — split reasoning steps and content into separate cards
  const stepBlocks = blocks?.filter(b => b.type === 'think' || b.type === 'tool') || [];
  const contentBlocks = blocks?.filter(b => b.type === 'text' || b.type === 'widget' || b.type === 'video' || b.type === 'image') || [];
  const hasSteps = stepBlocks.length > 0;
  const hasContent = contentBlocks.length > 0 || !!content;
  const splitCards = hasSteps && hasContent;

  return (
    <motion.div
      className="msg-row msg-row-assistant"
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: 'easeOut' }}
    >
      <MoonAvatar />
      <div className="msg-col msg-col-assistant">
        {/* Reasoning card — only step blocks */}
        {hasSteps && (
          <div className={`bubble bubble-assistant${splitCards ? ' bubble-trace-only' : ''}`}>
            <div className="msg-content">
              <TraceCard blocks={stepBlocks} />
            </div>
          </div>
        )}

        {/* Content card — text/widget/video + actions + audio + usage */}
        {hasContent && (
          <div className={`bubble bubble-assistant${splitCards ? ' bubble-content-only' : ''}`}>
            <div className="msg-content">
              {hasContent && contentBlocks.length > 0 ? (
                <TraceCard blocks={contentBlocks} />
              ) : (
                <div className="final-content"><Markdown text={content} /></div>
              )}
            </div>
            {audios?.map((a, i) => <AudioPlayer key={`a-${i}`} audio={a} />)}
            <div className="msg-actions">
              <TooltipWrap label={copied ? '已复制' : '复制'}>
                <button
                  className="msg-action-btn"
                  onClick={handleCopy}
                  aria-label={copied ? '已复制' : '复制消息内容'}
                >
                  <Icon name={copied ? 'check' : 'clipboard'} size={12} />
                  {copied ? '已复制' : '复制'}
                </button>
              </TooltipWrap>
            </div>
            {usage && (
              <div className="usage-info">
                {usage.input_tokens} 输入 / {usage.output_tokens} 输出
              </div>
            )}
          </div>
        )}

        {/* No content but has steps — render actions on last card */}
        {!hasContent && hasSteps && (
          <>
            {audios?.map((a, i) => <AudioPlayer key={`a-${i}`} audio={a} />)}
            <div className="msg-actions" style={{ marginTop: 4 }}>
              <TooltipWrap label={copied ? '已复制' : '复制'}>
                <button
                  className="msg-action-btn"
                  onClick={handleCopy}
                  aria-label={copied ? '已复制' : '复制消息内容'}
                >
                  <Icon name={copied ? 'check' : 'clipboard'} size={12} />
                  {copied ? '已复制' : '复制'}
                </button>
              </TooltipWrap>
            </div>
          </>
        )}

        {timeStr && <span className="msg-time msg-time-assistant">{timeStr}</span>}
      </div>
    </motion.div>
  );
}
