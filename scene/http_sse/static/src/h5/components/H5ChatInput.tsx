import React, { useCallback, useMemo, useRef } from 'react';
import { motion } from 'motion/react';
import { useUIStore } from '../../stores/ui-store';
import { useSkillStore } from '../../stores/skill-store';
import './H5ChatInput.css';

interface Props {
  onSend: (text: string) => void;
}

export default function H5ChatInput({ onSend }: Props) {
  const inputValue = useUIStore((s) => s.inputValue);
  const setInputValue = useUIStore((s) => s.setInputValue);
  const skills = useSkillStore((s) => s.skills);
  const enabled = useSkillStore((s) => s.enabled);
  const inputRef = useRef<HTMLInputElement>(null);

  const quickTags = useMemo(() => {
    return skills
      .filter((s) => enabled.has(s.name))
      .slice(0, 5);
  }, [skills, enabled]);

  const handleSend = useCallback(() => {
    const text = inputValue.trim();
    if (!text) return;
    onSend(text);
    setInputValue('');
  }, [inputValue, onSend, setInputValue]);

  const handleTagClick = useCallback((skillName: string) => {
    onSend('/skill:' + skillName);
  }, [onSend]);

  const showTags = !inputValue && quickTags.length > 0;

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="h5-input-dock">
      {showTags && (
        <motion.div
          className="h5-quick-tags"
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 4 }}
          transition={{ duration: 0.15 }}
        >
          {quickTags.map((skill) => (
            <motion.button
              key={skill.name}
              className="h5-quick-tag"
              onClick={() => handleTagClick(skill.name)}
              whileTap={{ scale: 0.95 }}
            >
              {skill.name}
            </motion.button>
          ))}
        </motion.div>
      )}

      <div className="container-ia-chat">
        <input type="checkbox" name="input-voice" id="input-voice" className="input-voice" style={{display: 'none'}} aria-label="语音模式" />
        <input
          ref={inputRef}
          type="text"
          name="input-text"
          id="input-text"
          placeholder="输入问题..."
          className="input-text"
          required
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <input type="checkbox" name="input-files" id="input-files" className="input-files" style={{display: 'none'}} aria-label="上传文件" />
        <div className="container-upload-files">
          <svg className="upload-file" xmlns="http://www.w3.org/2000/svg" width={24} height={24} viewBox="0 0 24 24">
            <g fill="none" stroke="currentColor" strokeWidth={2}>
              <circle cx={12} cy={13} r={3} />
              <path d="M9.778 21h4.444c3.121 0 4.682 0 5.803-.735a4.4 4.4 0 0 0 1.226-1.204c.749-1.1.749-2.633.749-5.697s0-4.597-.749-5.697a4.4 4.4 0 0 0-1.226-1.204c-.72-.473-1.622-.642-3.003-.702c-.659 0-1.226-.49-1.355-1.125A2.064 2.064 0 0 0 13.634 3h-3.268c-.988 0-1.839.685-2.033 1.636c-.129.635-.696 1.125-1.355 1.125c-1.38.06-2.282.23-3.003.702A4.4 4.4 0 0 0 2.75 7.667C2 8.767 2 10.299 2 13.364s0 4.596.749 5.697c.324.476.74.885 1.226 1.204C5.096 21 6.657 21 9.778 21Z" />
            </g>
          </svg>
          <svg className="upload-file" xmlns="http://www.w3.org/2000/svg" width={24} height={24} viewBox="0 0 24 24">
            <g fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}>
              <rect width={18} height={18} x={3} y={3} rx={2} ry={2} />
              <circle cx={9} cy={9} r={2} />
              <path d="m21 15l-3.086-3.086a2 2 0 0 0-2.828 0L6 21" />
            </g>
          </svg>
          <svg className="upload-file" xmlns="http://www.w3.org/2000/svg" width={24} height={24} viewBox="0 0 24 24">
            <path fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="m6 14l1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2" />
          </svg>
        </div>
        <label htmlFor="input-files" className="label-files">
          <svg xmlns="http://www.w3.org/2000/svg" width={24} height={24} viewBox="0 0 24 24">
            <path fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14m-7-7v14" />
          </svg>
        </label>
        <label htmlFor="input-voice" className="label-voice">
          <svg className="icon-voice" xmlns="http://www.w3.org/2000/svg" width={24} height={24} viewBox="0 0 24 24">
            <path fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth={2} d="M12 4v16m4-13v10M8 7v10m12-6v2M4 11v2" />
          </svg>
          <div className="ai">
            <div className="container">
              <div className="c c4" />
              <div className="c c1" />
              <div className="c c2" />
              <div className="c c3" />
              <div className="rings" />
            </div>
            <div className="glass" />
          </div>
          <div className="text-voice">
            <p>Conversation Started</p>
            <p>Press to cancel the conversation</p>
          </div>
        </label>
        <label htmlFor="input-text" className="label-text" onClick={(e) => { e.preventDefault(); handleSend(); }}>
          <svg xmlns="http://www.w3.org/2000/svg" width={24} height={24} viewBox="0 0 24 24">
            <path fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="m5 12l7-7l7 7m-7 7V5" />
          </svg>
        </label>
      </div>
    </div>
  );
}
