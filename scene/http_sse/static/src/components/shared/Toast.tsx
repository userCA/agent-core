import React, { useCallback } from 'react';
import * as Toast from '@radix-ui/react-toast';
import { Check, CircleX, Info, X } from 'lucide-react';
import { useToastStore } from '../../stores/toast-store';
import './Toast.css';

function ToastIcon({ type }: { type: string }) {
  if (type === 'success') {
    return <Check size={16} />;
  }
  if (type === 'error') {
    return <CircleX size={16} />;
  }
  return <Info size={16} />;
}

export default function ToastContainer() {
  const toasts = useToastStore((s) => s.toasts);
  const removeToast = useToastStore((s) => s.removeToast);

  const handleOpenChange = useCallback((id: string, open: boolean) => {
    if (!open) removeToast(id);
  }, [removeToast]);

  return (
    <Toast.Provider swipeDirection="right" duration={4000}>
      {toasts.map((t) => (
        <Toast.Root
          key={t.id}
          className={`toast-item ${t.type}`}
          onOpenChange={(open) => handleOpenChange(t.id, open)}
        >
          <span className="toast-icon">
            <ToastIcon type={t.type} />
          </span>
          <Toast.Description className="toast-message">
            {t.message}
          </Toast.Description>
          <Toast.Close className="toast-close" aria-label="关闭通知">
            <X size={14} />
          </Toast.Close>
        </Toast.Root>
      ))}
      <Toast.Viewport className="toast-viewport" />
    </Toast.Provider>
  );
}
