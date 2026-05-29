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
import './App.css';

export default function App() {
  const { sendMessage, abort } = useSSE();
  const loadAuth = useSessionStore((s) => s.loadAuth);
  const authModalOpen = useUIStore((s) => s.authModalOpen);
  const activePage = useUIStore((s) => s.activePage);

  useEffect(() => {
    loadAuth();
  }, [loadAuth]);

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
        </div>
      </div>
      {authModalOpen && <AuthModal />}
    </BridgeProvider>
  );
}
