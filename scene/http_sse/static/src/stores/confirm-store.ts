import { create } from 'zustand';

interface ConfirmOptions {
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel?: () => void;
}

interface ConfirmState {
  open: boolean;
  title: string;
  message: string;
  confirmText: string;
  cancelText: string;
  danger: boolean;
  onConfirm: (() => void) | null;
  onCancel: (() => void) | null;

  requestConfirm: (options: ConfirmOptions) => void;
  close: () => void;
  confirm: () => void;
}

export const useConfirmStore = create<ConfirmState>((set, get) => ({
  open: false,
  title: '',
  message: '',
  confirmText: '确认',
  cancelText: '取消',
  danger: false,
  onConfirm: null,
  onCancel: null,

  requestConfirm: (options) => {
    set({
      open: true,
      title: options.title,
      message: options.message,
      confirmText: options.confirmText || '确认',
      cancelText: options.cancelText || '取消',
      danger: options.danger ?? false,
      onConfirm: () => {
        options.onConfirm();
        get().close();
      },
      onCancel: options.onCancel
        ? () => {
            options.onCancel!();
            get().close();
          }
        : null,
    });
  },

  close: () => {
    const { onCancel } = get();
    if (onCancel) onCancel();
    set({ open: false, onConfirm: null, onCancel: null });
  },

  confirm: () => {
    const { onConfirm } = get();
    if (onConfirm) onConfirm();
    else set({ open: false });
  },
}));
