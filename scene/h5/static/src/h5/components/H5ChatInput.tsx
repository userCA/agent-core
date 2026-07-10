import React, { useCallback, useRef, useState } from 'react';
import { useUIStore } from '../../stores/ui-store';
import ToolDrawer from './ToolDrawer';
import './H5ChatInput.css';

interface PendingImage {
  file: File;
  preview: string;
}

interface Props {
  onSend: (text: string, files?: File[]) => void;
}

const MAX_IMAGES = 9;

export default function H5ChatInput({ onSend }: Props) {
  const inputValue = useUIStore((s) => s.inputValue);
  const setInputValue = useUIStore((s) => s.setInputValue);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [pendingImages, setPendingImages] = useState<PendingImage[]>([]);

  const handleImageSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    const imageFiles = files.filter(f => f.type.startsWith('image/'));
    if (imageFiles.length === 0) return;

    const newImages = imageFiles.slice(0, MAX_IMAGES - pendingImages.length).map(file => ({
      file,
      preview: URL.createObjectURL(file),
    }));
    setPendingImages(prev => [...prev, ...newImages].slice(0, MAX_IMAGES));

    // Reset input value so the same file can be selected again
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }, [pendingImages.length]);

  /** Handle files from ToolDrawer (album / camera / file) */
  const handleDrawerFiles = useCallback((files: File[]) => {
    const imageFiles = files.filter(f => f.type.startsWith('image/'));
    if (imageFiles.length === 0) return;
    const newImages = imageFiles.slice(0, MAX_IMAGES - pendingImages.length).map(file => ({
      file,
      preview: URL.createObjectURL(file),
    }));
    setPendingImages(prev => [...prev, ...newImages].slice(0, MAX_IMAGES));
  }, [pendingImages.length]);

  const removeImage = useCallback((index: number) => {
    setPendingImages(prev => {
      const removed = prev[index];
      if (removed) URL.revokeObjectURL(removed.preview);
      return prev.filter((_, i) => i !== index);
    });
  }, []);

  const handleSend = useCallback(() => {
    const text = inputValue.trim();
    if (!text && pendingImages.length === 0) return;
    const files = pendingImages.map(p => p.file);
    onSend(text, files.length > 0 ? files : undefined);
    setInputValue('');
    // Cleanup preview URLs
    pendingImages.forEach(p => URL.revokeObjectURL(p.preview));
    setPendingImages([]);
    // Reset textarea height after send
    if (textareaRef.current) {
      textareaRef.current.style.height = '44px';
    }
  }, [inputValue, pendingImages, onSend, setInputValue]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  /** Auto-resize textarea to fit content, max 120px */
  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputValue(e.target.value);
    const el = e.target;
    el.style.height = '44px';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
  };

  return (
    <div className="h5-input-dock">
      {/* Image previews */}
      {pendingImages.length > 0 && (
        <div className="h5-image-preview-row">
          {pendingImages.map((img, i) => (
            <div key={i} className="h5-image-preview">
              <img src={img.preview} alt={`preview-${i}`} />
              <button
                type="button"
                className="h5-image-remove"
                onClick={() => removeImage(i)}
                aria-label="移除图片"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                  stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>
          ))}
          {pendingImages.length < MAX_IMAGES && (
            <button
              type="button"
              className="h5-image-add"
              onClick={() => fileInputRef.current?.click()}
              aria-label="添加图片"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <path d="M12 8v8m-4-4h8" />
              </svg>
            </button>
          )}
        </div>
      )}

      <div className="h5-input-row">
        {/* Plus button — opens media drawer */}
        <button
          type="button"
          className="h5-input-btn h5-input-plus"
          aria-label="更多"
          onClick={() => setDrawerOpen(true)}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M5 12h14m-7-7v14" />
          </svg>
        </button>

        {/* Hidden file input (for preview row's add button) */}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          multiple
          style={{ display: 'none' }}
          onChange={handleImageSelect}
        />

        {/* Textarea */}
        <textarea
          ref={textareaRef}
          className="h5-input-textarea"
          rows={1}
          placeholder="写点什么…"
          value={inputValue}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
        />

        {/* Send button */}
        <button
          type="button"
          className="h5-input-btn h5-input-send"
          onClick={handleSend}
          disabled={!inputValue.trim() && pendingImages.length === 0}
          aria-label="发送消息"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="m5 12l7-7l7 7m-7 7V5" />
          </svg>
        </button>
      </div>

      {/* Media Drawer (bottom sheet) */}
      <ToolDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        onFilesSelected={handleDrawerFiles}
      />
    </div>
  );
}
