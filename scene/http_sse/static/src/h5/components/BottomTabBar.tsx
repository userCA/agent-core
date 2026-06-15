import React from 'react';
import * as Tabs from '@radix-ui/react-tabs';
import { motion } from 'motion/react';
import { useUIStore } from '../../stores/ui-store';
import Icon from '../../components/shared/Icon';
import './BottomTabBar.css';

const TAB_ITEMS = [
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
    <Tabs.Root value={activeTab} onValueChange={(v) => setActiveTab(v as 'chat' | 'skills')} asChild>
      <nav className="h5-tab-bar">
        <Tabs.List className="h5-tab-bar">
          {TAB_ITEMS.map((tab) => (
            <Tabs.Trigger key={tab.key} value={tab.key} asChild>
              <motion.button
                className={`h5-tab ${activeTab === tab.key ? 'h5-tab--active' : ''}`}
                aria-label={tab.label}
                whileTap={{ scale: 0.92 }}
                transition={{ type: 'spring', stiffness: 500, damping: 30 }}
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
              </motion.button>
            </Tabs.Trigger>
          ))}
        </Tabs.List>
      </nav>
    </Tabs.Root>
  );
}
