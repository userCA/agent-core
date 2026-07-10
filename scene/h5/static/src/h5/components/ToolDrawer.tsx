import React, { useCallback, useRef } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { Image, Camera, FileUp } from 'lucide-react';
import './ToolDrawer.css';

interface Props {
  open: boolean;
  onClose: () => void;
  onFilesSelected: (files: File[]) => void;
}

const spring = { type: 'spring' as const, damping: 28, stiffness: 380 };

export default function ToolDrawer({ open, onClose, onFilesSelected }: Props) {
  const albumRef = useRef<HTMLInputElement>(null);
  const cameraRef = useRef<HTMLInputElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleFiles = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(e.target.files || []);
      if (files.length > 0) {
        onFilesSelected(files);
        onClose();
      }
      // Reset so same file can be re-selected
      if (e.target) e.target.value = '';
    },
    [onFilesSelected, onClose],
  );

  const trigger = (ref: React.RefObject<HTMLInputElement | null>) => {
    ref.current?.click();
  };

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Overlay */}
          <motion.div
            className="td-overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onClose}
          />

          {/* Sheet */}
          <motion.div
            className="td-sheet"
            initial={{ y: '100%' }}
            animate={{ y: 0 }}
            exit={{ y: '100%' }}
            transition={spring}
          >
            {/* Handle */}
            <div className="td-handle" onClick={onClose}>
              <div className="td-handle-bar" />
            </div>

            {/* Body — WeChat-style media actions */}
            <div className="td-body">
              <div className="td-grid td-grid-media">
                <button
                  type="button"
                  className="td-media-btn"
                  onClick={() => trigger(albumRef)}
                  aria-label="从相册选择"
                >
                  <span className="td-media-ic">
                    <Image size={24} />
                  </span>
                  <span className="td-media-label">相册</span>
                </button>

                <button
                  type="button"
                  className="td-media-btn"
                  onClick={() => trigger(cameraRef)}
                  aria-label="拍摄"
                >
                  <span className="td-media-ic">
                    <Camera size={24} />
                  </span>
                  <span className="td-media-label">拍摄</span>
                </button>

                <button
                  type="button"
                  className="td-media-btn"
                  onClick={() => trigger(fileRef)}
                  aria-label="发送文件"
                >
                  <span className="td-media-ic">
                    <FileUp size={24} />
                  </span>
                  <span className="td-media-label">文件</span>
                </button>
              </div>
            </div>

            {/* Hidden file inputs */}
            <input
              ref={albumRef}
              type="file"
              accept="image/*"
              multiple
              style={{ display: 'none' }}
              onChange={handleFiles}
            />
            <input
              ref={cameraRef}
              type="file"
              accept="image/*"
              capture="environment"
              style={{ display: 'none' }}
              onChange={handleFiles}
            />
            <input
              ref={fileRef}
              type="file"
              multiple
              style={{ display: 'none' }}
              onChange={handleFiles}
            />
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
