import React, { useEffect } from 'react';
import { BridgeProvider } from './bridge/BridgeContext';
import { useSSE } from './hooks/useSSE';
import { useSessionStore } from './stores/session-store';
import { useUIStore } from './stores/ui-store';
import Header from './components/header/Header';
import AuthModal from './components/header/AuthModal';
import ChatContainer from './components/chat/ChatContainer';
import ChatInput from './components/input/ChatInput';
import PendingBubbles from './components/input/PendingBubbles';

export default function App() {
  const { sendMessage, abort } = useSSE();
  const loadAuth = useSessionStore((s) => s.loadAuth);
  const authModalOpen = useUIStore((s) => s.authModalOpen);

  useEffect(() => {
    loadAuth();
  }, [loadAuth]);

  return (
    <BridgeProvider>
      <Header onAbort={abort} />
      <ChatContainer onExampleClick={sendMessage} />
      <PendingBubbles />
      <ChatInput onSend={sendMessage} />
      {authModalOpen && <AuthModal />}
    </BridgeProvider>
  );
}
