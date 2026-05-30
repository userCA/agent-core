import React from 'react';
import Icon from './Icon';
import './EmptyState.css';

interface Props {
  icon?: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export default function EmptyState({ icon, title, description, action }: Props) {
  return (
    <div className="empty-state">
      {icon && (
        <span className="empty-state-icon">
          <Icon name={icon as any} size={28} />
        </span>
      )}
      <p className="empty-state-title">{title}</p>
      {description && <p className="empty-state-desc">{description}</p>}
      {action && <div className="empty-state-action">{action}</div>}
    </div>
  );
}
