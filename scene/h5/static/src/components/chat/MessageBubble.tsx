import React, { useCallback, useState } from 'react';
import { motion } from 'motion/react';
import type { ChatMessage } from '../../stores/chat-store';
import { useChatStore } from '../../stores/chat-store';
import { useSessionStore } from '../../stores/session-store';
import { submitRunFeedback } from '../../api/client';
import Markdown from '../shared/Markdown';
import TraceCard from './TraceCard';
import AudioPlayer from '../tools/AudioPlayer';
import Icon, { ICON_SIZES } from '../shared/Icon';
import TooltipWrap from '../shared/TooltipWrap';
import { useToastStore } from '../../stores/toast-store';
import './MessageBubble.css';

interface FeedbackButtonsProps {
  runId?: string;
  feedbackVote?: 'up' | 'down';
  messageId: string;
}

function FeedbackButtons({ runId, feedbackVote, messageId }: FeedbackButtonsProps) {
  const addToast = useToastStore((s) => s.addToast);
  const sessionId = useSessionStore((s) => s.sessionId);
  const setMessageFeedbackVote = useChatStore((s) => s.setMessageFeedbackVote);

  const handleFeedback = useCallback(async (helpful: boolean) => {
    if (!runId || feedbackVote) return;
    const vote = helpful ? 'up' : 'down';
    setMessageFeedbackVote(messageId, vote);
    try {
      await submitRunFeedback({
        run_id: runId,
        was_helpful: helpful,
        session_id: sessionId ?? undefined,
      });
      addToast('感谢反馈', 'success');
    } catch {
      setMessageFeedbackVote(messageId, undefined);
      addToast('反馈提交失败', 'error');
    }
  }, [runId, feedbackVote, messageId, sessionId, setMessageFeedbackVote, addToast]);

  if (!runId) return null;

  return (
    <>
      <TooltipWrap label="有帮助">
        <button
          type="button"
          className={`msg-action-btn${feedbackVote === 'up' ? ' is-active' : ''}`}
          onClick={() => handleFeedback(true)}
          disabled={!!feedbackVote}
          aria-label="有帮助"
        >
          <Icon name="thumbs-up" size={12} />
        </button>
      </TooltipWrap>
      <TooltipWrap label="没帮助">
        <button
          type="button"
          className={`msg-action-btn${feedbackVote === 'down' ? ' is-active' : ''}`}
          onClick={() => handleFeedback(false)}
          disabled={!!feedbackVote}
          aria-label="没帮助"
        >
          <Icon name="thumbs-down" size={12} />
        </button>
      </TooltipWrap>
    </>
  );
}

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
  const { role, content, usage, toolCallId, blocks, audios, timestamp, runId, feedbackVote, id: messageId } = message;
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
  // Intermediate text (from tool_use turns) is treated as reasoning content —
  // it goes into the TraceCard (collapsed), not the content area.
  const { intermediateBlocks } = message;
  const isReasoningStep = (b: NonNullable<typeof blocks>[number]) => {
    if (b.type === 'think' || b.type === 'tool' || b.type === 'skill' || b.type === 'delegation' || b.type === 'plan') return true;
    // Intermediate text (generated during tool_use turns) is also reasoning
    if (b.type === 'text' && b.turnPhase === 'intermediate') return true;
    return false;
  };
  const stepBlocks = intermediateBlocks
    ? intermediateBlocks.filter(isReasoningStep)
    : (blocks?.filter(isReasoningStep) || []);
  const contentBlocks = intermediateBlocks
    ? intermediateBlocks.filter(b => !isReasoningStep(b))
      // Only final-phase blocks go to the content area
      .concat(blocks?.filter(b => b.turnPhase !== 'intermediate' && !isReasoningStep(b)) || [])
    : (blocks?.filter(b => b.type === 'text' || b.type === 'widget' || b.type === 'video' || b.type === 'image') || []);
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
        {/* Reasoning card — always uses bubble-trace-only for standalone trace styling */}
        {hasSteps && (
          <div className="bubble bubble-assistant bubble-trace-only">
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
              <FeedbackButtons runId={runId} feedbackVote={feedbackVote} messageId={messageId} />
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
              <FeedbackButtons runId={runId} feedbackVote={feedbackVote} messageId={messageId} />
            </div>
          </>
        )}

        {timeStr && <span className="msg-time msg-time-assistant">{timeStr}</span>}
      </div>
    </motion.div>
  );
}
