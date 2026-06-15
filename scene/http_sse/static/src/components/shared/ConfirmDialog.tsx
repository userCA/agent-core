import React from 'react';
import * as AlertDialog from '@radix-ui/react-alert-dialog';
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

  return (
    <AlertDialog.Root open={open}>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="confirm-overlay" />
        <AlertDialog.Content className="confirm-dialog">
          <AlertDialog.Title className="confirm-title">
            <span className={`confirm-icon ${type}`}>
              <Icon name={type === 'danger' ? 'alert' : 'check'} size={18} />
            </span>
            {title}
          </AlertDialog.Title>
          <AlertDialog.Description className="confirm-message">
            {message}
          </AlertDialog.Description>
          <div className="confirm-actions">
            <AlertDialog.Cancel asChild>
              <button className="confirm-btn cancel" onClick={close}>
                {cancelText}
              </button>
            </AlertDialog.Cancel>
            <AlertDialog.Action asChild>
              <button
                className={`confirm-btn ${danger ? 'danger' : 'primary'}`}
                onClick={confirm}
              >
                {confirmText}
              </button>
            </AlertDialog.Action>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  );
}
