import { create } from 'zustand';
import type { ChannelInfo } from '../api/client';
import { fetchChannels, saveChannel, deleteChannel } from '../api/client';
import { useToastStore } from './toast-store';

interface ChannelState {
  channels: ChannelInfo[];
  loading: boolean;
  load: () => Promise<void>;
  save: (ch: ChannelInfo) => Promise<void>;
  remove: (id: string) => Promise<void>;
}

export const useChannelStore = create<ChannelState>((set) => ({
  channels: [],
  loading: false,

  load: async () => {
    set({ loading: true });
    try {
      const channels = await fetchChannels();
      set({ channels });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '加载渠道失败';
      useToastStore.getState().addToast(msg, 'error');
    } finally {
      set({ loading: false });
    }
  },

  save: async (ch) => {
    try {
      await saveChannel(ch);
      await useChannelStore.getState().load();
      useToastStore.getState().addToast(`渠道 "${ch.name}" 保存成功`, 'success');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '保存渠道失败';
      useToastStore.getState().addToast(msg, 'error');
    }
  },

  remove: async (id) => {
    try {
      await deleteChannel(id);
      await useChannelStore.getState().load();
      useToastStore.getState().addToast('渠道已删除', 'success');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '删除渠道失败';
      useToastStore.getState().addToast(msg, 'error');
    }
  },
}));
