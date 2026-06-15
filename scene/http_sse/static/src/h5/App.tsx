import React, { useEffect } from 'react';
import * as Tooltip from '@radix-ui/react-tooltip';
import { MotionConfig, AnimatePresence, motion } from 'motion/react';
import { BridgeProvider } from '../bridge/BridgeContext';
import { useSSE } from '../hooks/useSSE';
import { useSessionStore } from '../stores/session-store';
import { useUIStore } from '../stores/ui-store';
import ChatContainer from '../components/chat/ChatContainer';
import PendingBubbles from '../components/input/PendingBubbles';
import H5ChatInput from './components/H5ChatInput';
import SkillsPage from '../components/pages/SkillsPage';
import ToastContainer from '../components/shared/Toast';
import ConfirmDialog from '../components/shared/ConfirmDialog';
import { useModelStore } from '../stores/model-store';

import CompactHeader from './components/CompactHeader';
import AuthPanel from './components/AuthPanel';
import LoginPage from './components/LoginPage';
import SettingsPage from './components/SettingsPage';
import HistoryPage from './components/HistoryPage';
import CompanionProfilePage from '../components/pages/CompanionProfilePage';
import './App.css';
import './theme/h5.css';

export default function H5App() {
  const { sendMessage, abort } = useSSE();
  const hasAuth = useSessionStore((s) => s.hasAuth);
  const loadAuth = useSessionStore((s) => s.loadAuth);
  const loadModels = useModelStore((s) => s.loadModels);
  const h5ActiveTab = useUIStore((s) => s.h5ActiveTab);
  const setH5ActiveTab = useUIStore((s) => s.setH5ActiveTab);

  useEffect(() => {
    loadAuth();
    loadModels();
  }, [loadAuth, loadModels]);

  if (!hasAuth) {
    return <LoginPage />;
  }

  return (
    <BridgeProvider>
      <Tooltip.Provider delayDuration={500} skipDelayDuration={0}>
      <MotionConfig reducedMotion="user">
        <div className="h5-app-layout">
          <CompactHeader onAbort={abort} />
          <div className="h5-content">
            <AnimatePresence mode="wait">
              {h5ActiveTab === 'chat' && (
                <motion.div
                  key="chat"
                  className="h5-page"
                  initial={{ opacity: 0, x: -12 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 12 }}
                  transition={{ type: 'spring', stiffness: 500, damping: 30 }}
                >
                  <ChatContainer onExampleClick={sendMessage} />
                  <PendingBubbles />
                  <H5ChatInput onSend={sendMessage} />
                </motion.div>
              )}
              {h5ActiveTab === 'skills' && (
                <motion.div
                  key="skills"
                  className="h5-page"
                  initial={{ opacity: 0, x: 12 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -12 }}
                  transition={{ type: 'spring', stiffness: 500, damping: 30 }}
                >
                  <SkillsPage onBack={() => setH5ActiveTab('chat')} />
                </motion.div>
              )}
              {h5ActiveTab === 'settings' && (
                <motion.div
                  key="settings"
                  className="h5-page h5-page--settings"
                  initial={{ opacity: 0, x: 12 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -12 }}
                  transition={{ type: 'spring', stiffness: 500, damping: 30 }}
                >
                  <SettingsPage />
                </motion.div>
              )}
              {h5ActiveTab === 'history' && (
                <motion.div
                  key="history"
                  className="h5-page"
                  initial={{ opacity: 0, x: 12 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -12 }}
                  transition={{ type: 'spring', stiffness: 500, damping: 30 }}
                >
                  <HistoryPage onBack={() => setH5ActiveTab('chat')} />
                </motion.div>
              )}
              {h5ActiveTab === 'companion' && (
                <motion.div
                  key="companion"
                  className="h5-page"
                  initial={{ opacity: 0, x: 12 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -12 }}
                  transition={{ type: 'spring', stiffness: 500, damping: 30 }}
                >
                  <CompanionProfilePage onBack={() => setH5ActiveTab('chat')} />
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
        <AuthPanel />
        <ToastContainer />
        <ConfirmDialog />
      </MotionConfig>
      </Tooltip.Provider>
    </BridgeProvider>
  );
}
