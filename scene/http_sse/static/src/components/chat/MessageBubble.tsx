import React, { useCallback, useState } from 'react';
import type { ChatMessage } from '../../stores/chat-store';
import Markdown from '../shared/Markdown';
import BlocksRenderer from './BlocksRenderer';
import AudioPlayer from '../tools/AudioPlayer';
import Icon, { ICON_SIZES } from '../shared/Icon';
import { useToastStore } from '../../stores/toast-store';
import './MessageBubble.css';

interface Props {
  message: ChatMessage;
}

export default function MessageBubble({ message }: Props) {
  const { role, content, usage, toolCallId, blocks, audios } = message;
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

  if (role === 'user') {
    return (
      <div className="msg-wrapper msg-user">
        <span className="msg-label">&gt; 你</span>
        <div className="bubble bubble-user">
          <pre className="user-text">{content}</pre>
        </div>
      </div>
    );
  }

  if (role === 'error') {
    return (
      <div className="msg-wrapper msg-error">
        <span className="msg-label"><Icon name="alert" size={ICON_SIZES.sm} /> 错误</span>
        <div className="bubble bubble-error">{content}</div>
      </div>
    );
  }

  if (role === 'tool') {
    return (
      <div className="msg-wrapper msg-tool">
        <span className="msg-label"><Icon name="tool" size={ICON_SIZES.sm} /> 工具</span>
        <div className="bubble bubble-tool">
          <pre className="tool-text">{content}</pre>
        </div>
      </div>
    );
  }

  // assistant
  return (
    <div className="msg-wrapper msg-assistant">
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
          <button
            className="msg-action-btn"
            onClick={handleCopy}
            title={copied ? '已复制' : '复制'}
            aria-label={copied ? '已复制' : '复制消息内容'}
          >
            <Icon name={copied ? 'check' : 'clipboard'} size={12} />
            {copied ? '已复制' : '复制'}
          </button>
        </div>
        {usage && (
          <div className="usage-info">
            {usage.input_tokens} 输入 / {usage.output_tokens} 输出 / {usage.total_tokens} 总计
          </div>
        )}
      </div>
    </div>
  );
}
