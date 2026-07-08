import React from 'react';
import Icon from './Icon';
import './Loading.css';

interface Props {
  text?: string;
  size?: 'sm' | 'md';
}

export default function Loading({ text = '加载中...', size = 'md' }: Props) {
  return (
    <div className={`loading-indicator loading-${size}`}>
      <Icon name="spinner" size={size === 'sm' ? 12 : 14} className="loading-spinner" />
      <span>{text}</span>
    </div>
  );
}
