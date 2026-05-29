import React, { useCallback, useRef, useEffect, useState } from 'react';
import { useChatStore } from '../../stores/chat-store';
import { useUIStore } from '../../stores/ui-store';
import { useSkillStore } from '../../stores/skill-store';
import { useAudioRecorder } from '../../hooks/useAudioRecorder';
import Icon from '../shared/Icon';
import './ChatInput.css';

interface Props {
  onSend: (text: string) => void;
}

export default function ChatInput({ onSend }: Props) {
  const isStreaming = useChatStore((s) => s.isStreaming);
  const pendingQueue = useChatStore((s) => s.pendingQueue);
  const inputValue = useUIStore((s) => s.inputValue);
  const setInputValue = useUIStore((s) => s.setInputValue);
  const skills = useSkillStore((s) => s.skills);
  const loadCapabilities = useSkillStore((s) => s.loadCapabilities);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [showSkills, setShowSkills] = useState(false);
  const [recording, setRecording] = useState(false);

  // Load skills on mount
  useEffect(() => {
    loadCapabilities();
  }, [loadCapabilities]);

  const handleSend = useCallback(() => {
    const text = inputValue.trim();
    if (!text) return;
    onSend(text);
  }, [inputValue, onSend]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // auto-resize textarea
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
  }, [inputValue]);

  // Audio recorder
  const { start: startRecording, stop: stopRecording } = useAudioRecorder((base64) => {
    // For now, just send a placeholder message indicating voice input
    // In a real implementation, you'd send the base64 audio to a speech-to-text API
    onSend(`[语音输入] ${base64.slice(0, 50)}...`);
  });

  const toggleRecording = () => {
    if (recording) {
      stopRecording();
      setRecording(false);
    } else {
      startRecording();
      setRecording(true);
    }
  };

  const insertSkill = (name: string) => {
    const prefix = inputValue ? inputValue + ' ' : '';
    setInputValue(`${prefix}/skill:${name} `);
    setShowSkills(false);
    inputRef.current?.focus();
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    // For now, just indicate file attachment in the input
    const prefix = inputValue ? inputValue + ' ' : '';
    setInputValue(`${prefix}[附件: ${file.name}] `);
    e.target.value = '';
  };

  return (
    <div className="chat-input-area">
      {pendingQueue.length > 0 && (
        <div className="pending-hint">
          pending {pendingQueue.length} message(s)
        </div>
      )}

      <div className="input-toolbar">
        <div className="toolbar-left">
          <button
            className="toolbar-btn"
            onClick={() => setShowSkills((v) => !v)}
            title="选择技能"
            aria-label="选择技能"
          >
            <Icon name="code" size={14} /> 技能
          </button>
          <button
            className="toolbar-btn"
            onClick={() => fileRef.current?.click()}
            title="上传附件"
            aria-label="上传附件"
          >
            <Icon name="upload" size={14} /> 附件
          </button>
          <input
            ref={fileRef}
            type="file"
            style={{ display: 'none' }}
            onChange={handleFileSelect}
          />
        </div>

        <div className="toolbar-right">
          <button
            className={`toolbar-btn${recording ? ' active' : ''}`}
            onClick={toggleRecording}
            title={recording ? '停止录音' : '语音输入'}
            aria-label={recording ? '停止录音' : '语音输入'}
          >
            <Icon name="recording" size={14} />
            {recording ? '录音中' : '语音'}
          </button>
        </div>
      </div>

      {showSkills && skills.length > 0 && (
        <div className="skill-panel">
          {skills.map((s) => (
            <button
              key={s.name}
              className="skill-item"
              onClick={() => insertSkill(s.name)}
              title={s.description}
            >
              <span className="skill-name">{s.name}</span>
              <span className="skill-desc">{s.description}</span>
            </button>
          ))}
        </div>
      )}

      <div className="input-row">
        <textarea
          ref={inputRef}
          className="chat-textarea"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={isStreaming ? 'queue a message...' : 'type a message'}
          rows={1}
          aria-label="消息输入框，按 Enter 发送，Shift+Enter 换行"
        />
        <button
          className="send-btn"
          onClick={handleSend}
          disabled={!inputValue.trim() || isStreaming}
          aria-label="发送消息"
        >
          <Icon name="send" size={16} />
        </button>
      </div>
    </div>
  );
}
