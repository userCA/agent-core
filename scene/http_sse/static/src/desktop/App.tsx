import React, { useEffect } from 'react';
import { MotionConfig, AnimatePresence, motion } from 'motion/react';
import { BridgeProvider } from '../bridge/BridgeContext';
import { useSSE } from '../hooks/useSSE';
import { useSessionStore } from '../stores/session-store';
import { useUIStore } from '../stores/ui-store';
import Sidebar from '../components/sidebar/Sidebar';
import Header from '../components/header/Header';
import AuthModal from '../components/header/AuthModal';
import LoginPage from '../components/header/LoginPage';
import ChatContainer from '../components/chat/ChatContainer';
import ChatInput from '../components/input/ChatInput';
import PendingBubbles from '../components/input/PendingBubbles';

import SkillsPage from '../components/pages/SkillsPage';
import ConnectorsPage from '../components/pages/ConnectorsPage';
import ExpertsPage from '../components/pages/ExpertsPage';
import KnowledgePage from '../components/pages/KnowledgePage';
import ChannelsPage from '../components/pages/ChannelsPage';
import CompanionProfilePage from '../components/pages/CompanionProfilePage';
import ToastContainer from '../components/shared/Toast';
import ConfirmDialog from '../components/shared/ConfirmDialog';
import { useModelStore } from '../stores/model-store';
import './App.css';

const VALID_PAGES = ['chat', 'skills', 'connectors', 'experts', 'knowledge', 'channels', 'companion'];

export default function DesktopApp() {
  const { sendMessage, abort } = useSSE();
  const hasAuth = useSessionStore((s) => s.hasAuth);
  const loadAuth = useSessionStore((s) => s.loadAuth);
  const loadModels = useModelStore((s) => s.loadModels);
  const activePage = useUIStore((s) => s.activePage);
  const setActivePage = useUIStore((s) => s.setActivePage);

  useEffect(() => {
    loadAuth();
    loadModels();
  }, [loadAuth, loadModels]);

  // Sync activePage with browser back/forward buttons
  useEffect(() => {
    const handlePopState = (e: PopStateEvent) => {
      const page = (e.state?.page as string) || 'chat';
      if (VALID_PAGES.includes(page)) {
        setActivePage(page as typeof activePage);
      }
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, [setActivePage]);

  if (!hasAuth) {
    return <LoginPage />;
  }

  return (
    <BridgeProvider>
      <MotionConfig reducedMotion="user">
        <div className="app-layout">
        <a className="skip-link" href="#main-content">跳到主要内容</a>
        <Sidebar />
        <div id="main-content" className="app-main" onClick={() => {
          // Close sidebar on mobile when clicking content area
          const collapsed = useUIStore.getState().sidebarCollapsed;
          if (!collapsed && window.innerWidth <= 768) {
            useUIStore.getState().toggleSidebar();
          }
        }}>
          <Header onAbort={abort} />
          <AnimatePresence mode="wait">
            {activePage === 'chat' && (
              <motion.div
                key="chat"
                className="page-wrapper"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.12 }}
              >
                <ChatContainer onExampleClick={sendMessage} />
                <PendingBubbles />
                <ChatInput onSend={sendMessage} />
              </motion.div>
            )}
            {activePage === 'skills' && (
              <motion.div
                key="skills"
                className="page-wrapper"
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.18 }}
              >
                <SkillsPage />
              </motion.div>
            )}
            {activePage === 'connectors' && (
              <motion.div key="connectors" className="page-wrapper" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.18 }}>
                <ConnectorsPage />
              </motion.div>
            )}
            {activePage === 'experts' && (
              <motion.div key="experts" className="page-wrapper" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.18 }}>
                <ExpertsPage />
              </motion.div>
            )}
            {activePage === 'knowledge' && (
              <motion.div key="knowledge" className="page-wrapper" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.18 }}>
                <KnowledgePage />
              </motion.div>
            )}
            {activePage === 'channels' && (
              <motion.div key="channels" className="page-wrapper" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.18 }}>
                <ChannelsPage />
              </motion.div>
            )}
            {activePage === 'companion' && (
              <motion.div key="companion" className="page-wrapper" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.18 }}>
                <CompanionProfilePage />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
      <AuthModal />
      <ToastContainer />
      <ConfirmDialog />
      </MotionConfig>
    </BridgeProvider>
  );
}
