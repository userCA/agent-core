import { create } from 'zustand';
import {
  fetchCapabilities,
  fetchEvolutionSummary,
  analyzeSkillEvolution,
  fetchEvolutionProposals,
  acceptEvolutionProposal,
  rejectEvolutionProposal,
  fetchEvolutionAudit,
} from '../api/client';
import type {
  SkillInfo,
  ToolInfo,
  EvolutionSummary,
  EvolutionProposal,
  EvolutionAuditEntry,
} from '../api/client';
import { useToastStore } from './toast-store';

const SKILL_ENABLED_KEY = 'agent_skill_enabled';

function loadEnabled(): Set<string> {
  try {
    const raw = localStorage.getItem(SKILL_ENABLED_KEY);
    if (raw) return new Set(JSON.parse(raw));
  } catch { /* ignore */ }
  return new Set();
}

function saveEnabled(enabled: Set<string>) {
  try {
    localStorage.setItem(SKILL_ENABLED_KEY, JSON.stringify([...enabled]));
  } catch { /* ignore */ }
}

interface SkillState {
  skills: SkillInfo[];
  tools: ToolInfo[];
  loading: boolean;
  enabled: Set<string>;

  // Evolution state
  evolutionSummary: EvolutionSummary | null;
  evolutionLoading: boolean;
  evolutionProposals: Record<string, EvolutionProposal[]>;
  evolutionAudit: EvolutionAuditEntry[];

  loadCapabilities: () => Promise<void>;
  toggleSkill: (name: string) => void;
  isEnabled: (name: string) => boolean;

  loadEvolutionSummary: () => Promise<void>;
  analyzeEvolution: (skillName: string) => Promise<EvolutionProposal[]>;
  loadEvolutionProposals: (skillName: string) => Promise<EvolutionProposal[]>;
  acceptProposal: (proposalId: string, skillName: string) => Promise<boolean>;
  rejectProposal: (proposalId: string, skillName: string, reason?: string) => Promise<boolean>;
  loadEvolutionAudit: (skillName?: string) => Promise<void>;
}

export const useSkillStore = create<SkillState>((set, get) => ({
  skills: [],
  tools: [],
  loading: false,
  enabled: loadEnabled(),

  evolutionSummary: null,
  evolutionLoading: false,
  evolutionProposals: {},
  evolutionAudit: [],

  loadCapabilities: async () => {
    set({ loading: true });
    try {
      const caps = await fetchCapabilities();
      set({ skills: caps.skills, tools: caps.tools });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '加载技能失败';
      useToastStore.getState().addToast(msg, 'error');
    } finally {
      set({ loading: false });
    }
  },

  toggleSkill: (name) => {
    const next = new Set(get().enabled);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    saveEnabled(next);
    set({ enabled: next });
  },

  isEnabled: (name) => get().enabled.has(name),

  // Evolution actions
  loadEvolutionSummary: async () => {
    try {
      const summary = await fetchEvolutionSummary();
      set({ evolutionSummary: summary });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '加载进化摘要失败';
      useToastStore.getState().addToast(msg, 'error');
    }
  },

  analyzeEvolution: async (skillName) => {
    set({ evolutionLoading: true });
    try {
      const result = await analyzeSkillEvolution(skillName);
      if (result.status === 'skipped') {
        useToastStore.getState().addToast(
          result.reason === 'insufficient_traces'
            ? `追踪数据不足，需要更多执行记录`
            : result.reason || '分析跳过',
          'info',
        );
        return [];
      }
      const proposals = result.proposals || [];
      set((s) => ({
        evolutionProposals: { ...s.evolutionProposals, [skillName]: proposals },
      }));
      useToastStore.getState().addToast(
        `分析完成：${result.proposals_generated || 0} 条提议`,
        'success',
      );
      return proposals;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '进化分析失败';
      useToastStore.getState().addToast(msg, 'error');
      return [];
    } finally {
      set({ evolutionLoading: false });
    }
  },

  loadEvolutionProposals: async (skillName) => {
    try {
      const proposals = await fetchEvolutionProposals(skillName);
      set((s) => ({
        evolutionProposals: { ...s.evolutionProposals, [skillName]: proposals },
      }));
      return proposals;
    } catch {
      return [];
    }
  },

  acceptProposal: async (proposalId, skillName) => {
    try {
      const result = await acceptEvolutionProposal(proposalId, skillName);
      if (result.success) {
        set((s) => ({
          evolutionProposals: {
            ...s.evolutionProposals,
            [skillName]: (s.evolutionProposals[skillName] || []).filter(
              (p) => p.proposal_id !== proposalId,
            ),
          },
        }));
        useToastStore.getState().addToast('已应用进化提议', 'success');
      }
      return result.success;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '应用提议失败';
      useToastStore.getState().addToast(msg, 'error');
      return false;
    }
  },

  rejectProposal: async (proposalId, skillName, reason) => {
    try {
      await rejectEvolutionProposal(proposalId, skillName, reason);
      set((s) => ({
        evolutionProposals: {
          ...s.evolutionProposals,
          [skillName]: (s.evolutionProposals[skillName] || []).filter(
            (p) => p.proposal_id !== proposalId,
          ),
        },
      }));
      useToastStore.getState().addToast('已拒绝进化提议', 'info');
      return true;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '拒绝提议失败';
      useToastStore.getState().addToast(msg, 'error');
      return false;
    }
  },

  loadEvolutionAudit: async (skillName) => {
    try {
      const result = await fetchEvolutionAudit(skillName);
      set({ evolutionAudit: result.entries });
    } catch {
      /* silent */
    }
  },
}));
