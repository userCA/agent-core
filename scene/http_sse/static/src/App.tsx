import React, { useEffect } from 'react';
import { BridgeProvider } from './bridge/BridgeContext';
import { useSSE } from './hooks/useSSE';
import { useSessionStore } from './stores/session-store';
import { useUIStore } from './stores/ui-store';
import Sidebar from './components/sidebar/Sidebar';
import Header from './components/header/Header';
import AuthModal from './components/header/AuthModal';
import ChatContainer from './components/chat/ChatContainer';
import ChatInput from './components/input/ChatInput';
import PendingBubbles from './components/input/PendingBubbles';
import SkillsPage from './components/pages/SkillsPage';
import ConnectorsPage from './components/pages/ConnectorsPage';
import ExpertsPage from './components/pages/ExpertsPage';
import KnowledgePage from './components/pages/KnowledgePage';
import ChannelsPage from './components/pages/ChannelsPage';
import ToastContainer from './components/shared/Toast';
import ConfirmDialog from './components/shared/ConfirmDialog';
import './App.css';

const VALID_PAGES = ['chat', 'skills', 'connectors', 'experts', 'knowledge', 'channels'];

export default function App() {
  const { sendMessage, abort } = useSSE();
  const loadAuth = useSessionStore((s) => s.loadAuth);
  const authModalOpen = useUIStore((s) => s.authModalOpen);
  const activePage = useUIStore((s) => s.activePage);
  const setActivePage = useUIStore((s) => s.setActivePage);

  useEffect(() => {
    loadAuth();
  }, [loadAuth]);

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

  return (
    <BridgeProvider>
      <div className="app-layout">
        <Sidebar />
        <div className="app-main">
          <Header onAbort={abort} />
          {activePage === 'chat' && (
            <>
              <ChatContainer onExampleClick={sendMessage} />
              <PendingBubbles />
              <ChatInput onSend={sendMessage} />
            </>
          )}
          {activePage === 'skills' && <SkillsPage />}
          {activePage === 'connectors' && <ConnectorsPage />}
          {activePage === 'experts' && <ExpertsPage />}
          {activePage === 'knowledge' && <KnowledgePage />}
          {activePage === 'channels' && <ChannelsPage />}
        </div>
      </div>
      {authModalOpen && <AuthModal />}
      <ToastContainer />
      <ConfirmDialog />
    </BridgeProvider>
  );
}
