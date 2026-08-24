import React, { useCallback, useState } from 'react';
import { motion } from 'motion/react';
import type { ChatMessage } from '../../stores/chat-store';
import { useChatStore } from '../../stores/chat-store';
import { useSessionStore } from '../../stores/session-store';
import { submitRunFeedback } from '../../api/client';
import Markdown from '../shared/Markdown';
import BlocksRenderer from './BlocksRenderer';
import AudioPlayer from '../tools/AudioPlayer';
import Icon, { ICON_SIZES } from '../shared/Icon';
import TooltipWrap from '../shared/TooltipWrap';
import { useToastStore } from '../../stores/toast-store';
import './MessageBubble.css';

interface Props {
  message: ChatMessage;
}

export default function MessageBubble({ message }: Props) {
  const { role, content, usage, toolCallId, blocks, audios, runId, feedbackVote, id: messageId } = message;
  const [copied, setCopied] = useState(false);
  const addToast = useToastStore((s) => s.addToast);
  const sessionId = useSessionStore((s) => s.sessionId);
  const setMessageFeedbackVote = useChatStore((s) => s.setMessageFeedbackVote);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(content).then(() => {
      setCopied(true);
      addToast('已复制到剪贴板', 'success');
      setTimeout(() => setCopied(false), 2000);
    }).catch(() => {
      addToast('复制失败', 'error');
    });
  }, [content, addToast]);

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

  if (role === 'user') {
    return (
      <motion.div
        className="msg-wrapper msg-user"
        layout
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
      >
        <span className="msg-label">&gt; 你</span>
        <div className="bubble bubble-user">
          <pre className="user-text">{content}</pre>
        </div>
      </motion.div>
    );
  }

  if (role === 'error') {
    return (
      <motion.div
        className="msg-wrapper msg-error"
        layout
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
      >
        <span className="msg-label"><Icon name="alert" size={ICON_SIZES.sm} /> 错误</span>
        <div className="bubble bubble-error">{content}</div>
      </motion.div>
    );
  }

  if (role === 'tool') {
    return (
      <motion.div
        className="msg-wrapper msg-tool"
        layout
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
      >
        <span className="msg-label"><Icon name="tool" size={ICON_SIZES.sm} /> 工具</span>
        <div className="bubble bubble-tool">
          <pre className="tool-text">{content}</pre>
        </div>
      </motion.div>
    );
  }

  // assistant
  return (
    <motion.div
      className="msg-wrapper msg-assistant"
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: 'easeOut' }}
    >
      <span className="msg-label">助手</span>
      <div className="bubble bubble-assistant">
        <div className="msg-content">
          {blocks && blocks.length > 0 ? (
            <BlocksRenderer blocks={blocks} />
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
          {runId && (
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
          )}
        </div>
        {usage && (
          <div className="usage-info">
            {usage.input_tokens} 输入 / {usage.output_tokens} 输出 / {usage.total_tokens} 总计
          </div>
        )}
      </div>
    </motion.div>
  );
}
