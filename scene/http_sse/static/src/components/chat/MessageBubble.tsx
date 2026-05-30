import React from 'react';
import type { ChatMessage } from '../../stores/chat-store';
import Markdown from '../shared/Markdown';
import StepsPanel from '../tools/StepsPanel';
import WidgetFrame from '../tools/WidgetFrame';
import AudioPlayer from '../tools/AudioPlayer';
import Icon, { ICON_SIZES } from '../shared/Icon';
import './MessageBubble.css';

interface Props {
  message: ChatMessage;
}

export default function MessageBubble({ message }: Props) {
  const { role, content, usage, toolCallId, steps, widgets, audios } = message;

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
          {steps && steps.length > 0 && <StepsPanel steps={steps} />}
          <div className="final-content">
            <Markdown text={content} />
          </div>
        </div>
        {widgets?.map((w, i) => <WidgetFrame key={`w-${i}`} widget={w} />)}
        {audios?.map((a, i) => <AudioPlayer key={`a-${i}`} audio={a} />)}
        {usage && (
          <div className="usage-info">
            {usage.input_tokens} 输入 / {usage.output_tokens} 输出 / {usage.total_tokens} 总计
          </div>
        )}
      </div>
    </div>
  );
}
