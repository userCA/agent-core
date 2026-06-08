import React, { useEffect, useRef } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { useConfirmStore } from '../../stores/confirm-store';
import Icon from '../shared/Icon';
import './ConfirmDialog.css';

export default function ConfirmDialog() {
  const open = useConfirmStore((s) => s.open);
  const title = useConfirmStore((s) => s.title);
  const message = useConfirmStore((s) => s.message);
  const confirmText = useConfirmStore((s) => s.confirmText);
  const cancelText = useConfirmStore((s) => s.cancelText);
  const danger = useConfirmStore((s) => s.danger);
  const type = useConfirmStore((s) => s.type);
  const close = useConfirmStore((s) => s.close);
  const confirm = useConfirmStore((s) => s.confirm);

  const confirmRef = useRef<HTMLButtonElement>(null);
  const prevOpen = useRef(open);

  useEffect(() => {
    if (open && !prevOpen.current) {
      setTimeout(() => confirmRef.current?.focus(), 0);
    }
    prevOpen.current = open;
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        close();
      }
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [open, close]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="confirm-overlay"
          onClick={close}
          role="presentation"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
        >
          <motion.div
            className="confirm-dialog"
            onClick={(e) => e.stopPropagation()}
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="confirm-title"
            aria-describedby="confirm-message"
            initial={{ opacity: 0, scale: 0.95, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 8 }}
            transition={{ type: 'spring', duration: 0.35, bounce: 0.2 }}
          >
            <h3 id="confirm-title" className="confirm-title">
              <span className={`confirm-icon ${type}`}>
                <Icon name={type === 'danger' ? 'alert' : 'check'} size={18} />
              </span>
              {title}
            </h3>
            <p id="confirm-message" className="confirm-message">{message}</p>
            <div className="confirm-actions">
              <button className="confirm-btn cancel" onClick={close}>
                {cancelText}
              </button>
              <button
                ref={confirmRef}
                className={`confirm-btn ${danger ? 'danger' : 'primary'}`}
                onClick={confirm}
              >
                {confirmText}
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
