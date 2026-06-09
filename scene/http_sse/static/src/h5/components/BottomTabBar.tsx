import React from 'react';
import { motion } from 'motion/react';
import { useUIStore } from '../../stores/ui-store';
import Icon from '../../components/shared/Icon';
import './BottomTabBar.css';

const TABS = [
  { key: 'chat' as const, icon: 'message' as const, label: '聊天' },
  { key: 'skills' as const, icon: 'code' as const, label: '技能' },
];

export default function BottomTabBar() {
  const activeTab = useUIStore((s) => s.h5ActiveTab);
  const setActiveTab = useUIStore((s) => s.setH5ActiveTab);

  // Hide tab bar on aux pages (settings/history)
  if (activeTab === 'settings' || activeTab === 'history') {
    return null;
  }

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
          {activeTab === tab.key && (
            <motion.div
              className="h5-tab-indicator"
              layoutId="tab-indicator"
              transition={{ type: 'spring', stiffness: 500, damping: 35 }}
            />
          )}
        </button>
      ))}
    </nav>
  );
}
