import React from 'react';
import { useUIStore } from '../../stores/ui-store';
import Icon from '../../components/shared/Icon';
import './BottomTabBar.css';

const TABS = [
  { key: 'chat' as const, icon: 'message' as const, label: '聊天' },
  { key: 'skills' as const, icon: 'code' as const, label: '技能' },
  { key: 'settings' as const, icon: 'key' as const, label: '设置' },
];

export default function BottomTabBar() {
  const activeTab = useUIStore((s) => s.h5ActiveTab);
  const setActiveTab = useUIStore((s) => s.setH5ActiveTab);

  return (
    <nav className="h5-tab-bar">
      {TABS.map((tab) => (
        <button
          key={tab.key}
          className={`h5-tab ${activeTab === tab.key ? 'h5-tab--active' : ''}`}
          onClick={() => setActiveTab(tab.key)}
          aria-label={tab.label}
        >
          <Icon name={tab.icon} size={24} />
          <span className="h5-tab-label">{tab.label}</span>
        </button>
      ))}
    </nav>
  );
}
