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
  const enabled = useSkillStore((s) => s.enabled);
  const loadCapabilities = useSkillStore((s) => s.loadCapabilities);
  const visibleSkills = skills.filter((s) => enabled.has(s.name));
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const imageRef = useRef<HTMLInputElement>(null);
  const [showMore, setShowMore] = useState(false);
  const [showSkills, setShowSkills] = useState(false);
  const [recording, setRecording] = useState(false);

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

  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
  }, [inputValue]);

  const { start: startRecording, stop: stopRecording } = useAudioRecorder((base64) => {
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
    setShowMore(false);
    inputRef.current?.focus();
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const prefix = inputValue ? inputValue + ' ' : '';
    setInputValue(`${prefix}[文件: ${file.name}] `);
    setShowMore(false);
    e.target.value = '';
  };

  const handleImageSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const prefix = inputValue ? inputValue + ' ' : '';
    setInputValue(`${prefix}[图片: ${file.name}] `);
    setShowMore(false);
    e.target.value = '';
  };

  return (
    <div className="chat-input-area">
      {pendingQueue.length > 0 && (
        <div className="pending-hint">
          pending {pendingQueue.length} message(s)
        </div>
      )}

      {showSkills && visibleSkills.length > 0 && (
        <div className="skill-panel">
          {visibleSkills.map((s) => (
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

      <div className="input-box">
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

        <div className="input-actions">
          <div className="actions-left">
            <button
              className="action-btn"
              onClick={() => setShowSkills((v) => !v)}
              title="选择技能"
              aria-label="选择技能"
            >
              <Icon name="code" size={16} />
            </button>
            <button
              className={`action-btn${showMore ? ' active' : ''}`}
              onClick={() => setShowMore((v) => !v)}
              title="更多工具"
              aria-label="更多工具"
            >
              <Icon name="plus" size={16} />
            </button>

            {showMore && (
              <>
                <div className="more-backdrop" onClick={() => setShowMore(false)} />
                <div className="more-popover">
                  <button onClick={() => { fileRef.current?.click(); }}>
                    <Icon name="upload" size={14} /> 文件
                  </button>
                  <button onClick={() => { imageRef.current?.click(); }}>
                    <Icon name="image" size={14} /> 图片
                  </button>
                </div>
              </>
            )}
          </div>

          <div className="actions-right">
            <button
              className={`action-btn${recording ? ' recording' : ''}`}
              onClick={toggleRecording}
              title={recording ? '停止录音' : '语音输入'}
              aria-label={recording ? '停止录音' : '语音输入'}
            >
              <Icon name="recording" size={16} />
            </button>
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
      </div>

      <input ref={fileRef} type="file" style={{ display: 'none' }} onChange={handleFileSelect} />
      <input ref={imageRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={handleImageSelect} />
    </div>
  );
}
