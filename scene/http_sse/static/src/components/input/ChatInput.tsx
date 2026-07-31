import React, { useCallback, useRef, useEffect, useState, useMemo } from 'react';
import { motion } from 'motion/react';
import { useChatStore } from '../../stores/chat-store';
import { useUIStore } from '../../stores/ui-store';
import { useSkillStore } from '../../stores/skill-store';
import { useModelStore } from '../../stores/model-store';
import { useAudioRecorder } from '../../hooks/useAudioRecorder';
import Icon from '../shared/Icon';
import TooltipWrap from '../shared/TooltipWrap';
import './ChatInput.css';

interface Props {
  onSend: (text: string) => void;
  compact?: boolean;
  inlineToolbar?: boolean;
}

export default function ChatInput({ onSend, compact, inlineToolbar }: Props) {
  const isStreaming = useChatStore((s) => s.isStreaming);
  const pendingQueue = useChatStore((s) => s.pendingQueue);
  const inputValue = useUIStore((s) => s.inputValue);
  const setInputValue = useUIStore((s) => s.setInputValue);
  const skills = useSkillStore((s) => s.skills);
  const enabled = useSkillStore((s) => s.enabled);
  const loadCapabilities = useSkillStore((s) => s.loadCapabilities);
  const visibleSkills = skills.filter((s) => enabled.has(s.name));
  const { models, currentProvider, currentModel, loadModels, selectModel } = useModelStore();
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const imageRef = useRef<HTMLInputElement>(null);
  const [showMore, setShowMore] = useState(false);
  const [showSkills, setShowSkills] = useState(false);
  const [recording, setRecording] = useState(false);
  const [showModels, setShowModels] = useState(false);
  const [modelFilter, setModelFilter] = useState('');
  const [shakeInput, setShakeInput] = useState(false);

  const filteredModels = useMemo(() => {
    if (!modelFilter.trim()) return models;
    const q = modelFilter.toLowerCase();
    return models.filter((m) =>
      m.label.toLowerCase().includes(q) || m.desc.toLowerCase().includes(q)
    );
  }, [models, modelFilter]);

  useEffect(() => {
    loadCapabilities();
    loadModels();
  }, [loadCapabilities, loadModels]);

  const handleSend = useCallback(() => {
    const text = inputValue.trim();
    if (!text) {
      setShakeInput(true);
      setTimeout(() => setShakeInput(false), 500);
      return;
    }
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

  const { start: startRecording, stop: stopRecording } = useAudioRecorder((base64, blob) => {
    // Save recording and send as file reference
    const sendVoice = async () => {
      try {
        if (blob) {
          const { uploadFile } = await import('../../api/client');
          const file = new File([blob], `recording-${Date.now()}.wav`, { type: 'audio/wav' });
          const result = await uploadFile(file);
          onSend(`[语音消息] ${result.path}`);
        } else {
          onSend(`[语音消息] base64长度: ${base64.length}`);
        }
      } catch {
        onSend(`[语音消息] (${(base64.length / 1024).toFixed(1)}KB)`);
      }
    };
    sendVoice();
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

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const ext = file.name.split('.').pop()?.toLowerCase();
      const prefix = inputValue ? inputValue + '\n\n' : '';
      if (ext && ['txt', 'md', 'json', 'csv', 'py', 'js', 'ts', 'html', 'css', 'yaml', 'yml', 'xml', 'log'].includes(ext)) {
        const text = await file.text();
        setInputValue(`${prefix}[文件: ${file.name}]\n${text}`);
      } else {
        const { uploadFile } = await import('../../api/client');
        const result = await uploadFile(file);
        setInputValue(`${prefix}[文件: ${file.name}] ${result.url || result.path} (${(result.size / 1024).toFixed(1)}KB)`);
      }
      setShowMore(false);
    } catch { /* ignore */ }
    finally { e.target.value = ''; }
  };

  const handleImageSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const { uploadFile } = await import('../../api/client');
      const result = await uploadFile(file);
      const prefix = inputValue ? inputValue + '\n\n' : '';
      setInputValue(`${prefix}[图片: ${file.name}] ${result.url || result.path}`);
      setShowMore(false);
    } catch { /* ignore */ }
    finally { e.target.value = ''; }
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
            <TooltipWrap label={s.description}>
              <button
                key={s.name}
                className="skill-item"
                onClick={() => insertSkill(s.name)}
              >
                <span className="skill-name">{s.name}</span>
                <span className="skill-desc">{s.description}</span>
              </button>
            </TooltipWrap>
          ))}
        </div>
      )}

      <div className={`input-box${shakeInput ? ' shake' : ''}`}>
        <textarea
          ref={inputRef}
          className="chat-textarea"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={isStreaming ? '排队等待发送…' : '输入消息，按 Enter 发送'}
          rows={1}
          aria-label="消息输入框，按 Enter 发送，Shift+Enter 换行"
        />
        {inputValue && (
          <TooltipWrap label="清空">
            <button
              className="input-clear-btn"
              onClick={() => setInputValue('')}
              aria-label="清空输入"
            >
              <Icon name="cancel" size={12} />
            </button>
          </TooltipWrap>
        )}

        <div className={`input-actions${compact ? ' input-actions--compact' : ''}`}>
          {compact ? (
            <>
              {inlineToolbar ? (
                <div className="actions-left inline-toolbar">
                  <TooltipWrap label="上传文件">
                    <button
                      className="action-btn"
                      onClick={() => fileRef.current?.click()}
                      aria-label="上传文件"
                    >
                      <Icon name="upload" size={14} />
                    </button>
                  </TooltipWrap>
                  <TooltipWrap label="上传图片">
                    <button
                      className="action-btn"
                      onClick={() => imageRef.current?.click()}
                      aria-label="上传图片"
                    >
                      <Icon name="image" size={14} />
                    </button>
                  </TooltipWrap>
                  <TooltipWrap label="选择模型">
                    <button
                      className="action-btn"
                      onClick={() => setShowModels(!showModels)}
                      aria-label="选择模型"
                    >
                      <Icon name="chevron-down" size={14} />
                    </button>
                  </TooltipWrap>
                </div>
              ) : (
                <>
                  <TooltipWrap label="更多">
                    <button
                      className={`action-btn${showMore ? ' active' : ''}`}
                      onClick={() => setShowMore((v) => !v)}
                      aria-label="更多"
                    >
                      <Icon name="plus" size={18} />
                    </button>
                  </TooltipWrap>
                  {showMore && (
                    <>
                      <div className="more-backdrop" onClick={() => setShowMore(false)} />
                      <div className="more-popover">
                        <button onClick={() => { setShowSkills((v) => !v); setShowMore(false); }}>
                          <Icon name="code" size={14} /> 技能
                        </button>
                        <button onClick={() => { fileRef.current?.click(); setShowMore(false); }}>
                          <Icon name="upload" size={14} /> 文件
                        </button>
                        <button onClick={() => { imageRef.current?.click(); setShowMore(false); }}>
                          <Icon name="image" size={14} /> 图片
                        </button>
                        <button onClick={() => { toggleRecording(); setShowMore(false); }}>
                          <Icon name="recording" size={14} /> 语音
                        </button>
                        <button onClick={() => { setShowModels(!showModels); setShowMore(false); }}>
                          <Icon name="chevron-down" size={14} /> 模型
                        </button>
                      </div>
                    </>
                  )}
                </>
              )}
              {showModels && (
                <>
                  <div className="more-backdrop" onClick={() => setShowModels(false)} />
                  <div className="more-popover model-popover" style={{ bottom: '100%', top: 'auto', marginBottom: 6 }}>
                    {models.length > 6 && (
                      <div className="model-filter">
                        <Icon name="search" size={12} />
                        <input
                          type="text"
                          placeholder="搜索模型..."
                          value={modelFilter}
                          onChange={(e) => setModelFilter(e.target.value)}
                          autoFocus
                          onClick={(e) => e.stopPropagation()}
                        />
                      </div>
                    )}
                    {filteredModels.map((m) => (
                      <button key={`${m.provider}/${m.model}`}
                        className={currentProvider === m.provider && currentModel === m.model ? 'active' : ''}
                        onClick={() => { selectModel(m.provider, m.model); setShowModels(false); setModelFilter(''); }}>
                        <span style={{ fontWeight: 600 }}>{m.label}</span>
                        <span style={{ fontSize: 10, color: 'var(--ash)', marginLeft: 8 }}>{m.desc}</span>
                      </button>
                    ))}
                    {filteredModels.length === 0 && (
                      <div className="model-empty">无匹配模型</div>
                    )}
                  </div>
                </>
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
            </>
          ) : (
            <div className="actions-left">
              <TooltipWrap label="选择技能">
                <button
                  className="action-btn"
                  onClick={() => setShowSkills((v) => !v)}
                  aria-label="选择技能"
                >
                  <Icon name="code" size={16} />
                </button>
              </TooltipWrap>
              <TooltipWrap label="更多工具">
                <button
                  className={`action-btn${showMore ? ' active' : ''}`}
                  onClick={() => setShowMore((v) => !v)}
                  aria-label="更多工具"
                >
                  <Icon name="plus" size={16} />
                </button>
              </TooltipWrap>
              <div className="model-bar">
                <TooltipWrap label="切换模型">
                  <button className="model-pick" onClick={() => setShowModels(!showModels)}>
                  <span className="model-label">{models.find(m => m.provider === currentProvider && m.model === currentModel)?.label || `${currentProvider}/${currentModel}`}</span>
                  <Icon name="chevron-down" size={10} />
                </button>
                </TooltipWrap>
                {showModels && (
                  <>
                    <div className="more-backdrop" onClick={() => setShowModels(false)} />
                    <div className="more-popover model-popover" style={{ bottom: '100%', top: 'auto', marginBottom: 6 }}>
                      {models.length > 6 && (
                        <div className="model-filter">
                          <Icon name="search" size={12} />
                          <input
                            type="text"
                            placeholder="搜索模型..."
                            value={modelFilter}
                            onChange={(e) => setModelFilter(e.target.value)}
                            autoFocus
                            onClick={(e) => e.stopPropagation()}
                          />
                        </div>
                      )}
                      {filteredModels.map((m) => (
                        <button key={`${m.provider}/${m.model}`}
                          className={currentProvider === m.provider && currentModel === m.model ? 'active' : ''}
                          onClick={() => { selectModel(m.provider, m.model); setShowModels(false); setModelFilter(''); }}>
                          <span style={{ fontWeight: 600 }}>{m.label}</span>
                          <span style={{ fontSize: 10, color: 'var(--ash)', marginLeft: 8 }}>{m.desc}</span>
                        </button>
                      ))}
                      {filteredModels.length === 0 && (
                        <div className="model-empty">无匹配模型</div>
                      )}
                    </div>
                  </>
                )}
              </div>

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
          )}
          <div className="actions-right">
            {!compact && (
              <TooltipWrap label={recording ? '停止录音' : '语音输入'}>
                <button
                  className={`action-btn${recording ? ' recording' : ''}`}
                  onClick={toggleRecording}
                  aria-label={recording ? '停止录音' : '语音输入'}
                >
                  <Icon name="recording" size={16} />
                </button>
              </TooltipWrap>
            )}
            <motion.button
              className="send-btn"
              onClick={handleSend}
              disabled={!inputValue.trim() || isStreaming}
              aria-label="发送消息"
              whileTap={{ scale: 0.85 }}
              transition={{ type: 'spring', duration: 0.3, bounce: 0.3 }}
            >
              <Icon name="send" size={16} />
            </motion.button>
          </div>
        </div>
      </div>

      <input ref={fileRef} type="file" style={{ display: 'none' }} onChange={handleFileSelect} />
      <input ref={imageRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={handleImageSelect} />
    </div>
  );
}
