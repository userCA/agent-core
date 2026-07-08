import React, { createContext, useContext, useRef } from 'react';
import type { NativeBridge } from './types';
import { createWebBridge } from './web-provider';

const BridgeCtx = createContext<NativeBridge>(createWebBridge());

export function BridgeProvider({
  bridge,
  children,
}: {
  bridge?: NativeBridge;
  children: React.ReactNode;
}) {
  const ref = useRef<NativeBridge>(bridge || createWebBridge());
  return <BridgeCtx.Provider value={ref.current}>{children}</BridgeCtx.Provider>;
}

export function useBridge(): NativeBridge {
  return useContext(BridgeCtx);
}
