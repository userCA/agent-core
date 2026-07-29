/**
 * Skill Store — 移植自 scene/h5/static/src/stores/skill-store.ts
 *
 * 管理技能列表、开关状态（持久化）、进化分析/提议/审计。
 * 使用 uni.setStorageSync / uni.getStorageSync 替代 localStorage。
 */

import { reactive } from 'vue';
import {
  fetchCapabilities,
  importSkill as apiImportSkill,
  fetchEvolutionSummary,
  analyzeSkillEvolution,
  fetchEvolutionProposals,
  acceptEvolutionProposal,
  rejectEvolutionProposal,
  fetchEvolutionAudit,
} from '../api/client.js';

const SKILL_ENABLED_KEY = 'agent_skill_enabled';

function loadEnabled() {
  try {
    const raw = uni.getStorageSync(SKILL_ENABLED_KEY);
    if (raw) return new Set(JSON.parse(raw));
  } catch (e) { /* ignore */ }
  return new Set();
}

function saveEnabled(enabled) {
  try {
    uni.setStorageSync(SKILL_ENABLED_KEY, JSON.stringify([...enabled]));
  } catch (e) { /* ignore */ }
}

export const skillStore = reactive({
  /** @type {Array<{name: string, description: string}>} */
  skills: [],
  /** @type {Array<{name: string, description: string}>} */
  tools: [],
  loading: false,
  /** @type {Set<string>} */
  enabled: loadEnabled(),

  // Evolution state
  /** @type {object|null} */
  evolutionSummary: null,
  evolutionLoading: false,
  /** @type {Object<string, Array>} */
  evolutionProposals: {},
  /** @type {Array} */
  evolutionAudit: [],

  // ---- Actions ----

  async loadCapabilities() {
    this.loading = true;
    try {
      const caps = await fetchCapabilities();
      this.skills = caps.skills || [];
      this.tools = caps.tools || [];
    } catch (e) {
      console.warn('[skill] loadCapabilities failed:', e);
      uni.showToast({ title: '加载技能失败', icon: 'none' });
    } finally {
      this.loading = false;
    }
  },

  toggleSkill(name) {
    const next = new Set(this.enabled);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    saveEnabled(next);
    this.enabled = next;
  },

  isEnabled(name) {
    return this.enabled.has(name);
  },

  async importSkill(name, content) {
    try {
      await apiImportSkill(name, content);
      await this.loadCapabilities();
      return true;
    } catch (e) {
      console.error('[skill] importSkill failed:', e);
      uni.showToast({ title: '导入技能失败', icon: 'none' });
      return false;
    }
  },

  // ---- Evolution Actions ----

  async loadEvolutionSummary() {
    try {
      this.evolutionSummary = await fetchEvolutionSummary();
    } catch (e) {
      console.warn('[skill] loadEvolutionSummary failed:', e);
    }
  },

  async analyzeEvolution(skillName) {
    this.evolutionLoading = true;
    try {
      const result = await analyzeSkillEvolution(skillName);
      if (result.status === 'skipped') {
        uni.showToast({
          title: result.reason === 'insufficient_traces' ? '追踪数据不足' : '分析跳过',
          icon: 'none',
        });
        return [];
      }
      const proposals = result.proposals || [];
      this.evolutionProposals = {
        ...this.evolutionProposals,
        [skillName]: proposals,
      };
      uni.showToast({ title: `分析完成：${result.proposals_generated || 0} 条提议`, icon: 'none' });
      return proposals;
    } catch (e) {
      console.error('[skill] analyzeEvolution failed:', e);
      uni.showToast({ title: '进化分析失败', icon: 'none' });
      return [];
    } finally {
      this.evolutionLoading = false;
    }
  },

  async loadEvolutionProposals(skillName) {
    try {
      const proposals = await fetchEvolutionProposals(skillName);
      this.evolutionProposals = {
        ...this.evolutionProposals,
        [skillName]: proposals,
      };
      return proposals;
    } catch (e) {
      return [];
    }
  },

  async acceptProposal(proposalId, skillName) {
    try {
      const result = await acceptEvolutionProposal(proposalId, skillName);
      if (result.success) {
        const current = this.evolutionProposals[skillName] || [];
        this.evolutionProposals = {
          ...this.evolutionProposals,
          [skillName]: current.filter((p) => p.proposal_id !== proposalId),
        };
        uni.showToast({ title: '已应用进化提议', icon: 'success' });
      }
      return result.success;
    } catch (e) {
      console.error('[skill] acceptProposal failed:', e);
      uni.showToast({ title: '应用提议失败', icon: 'none' });
      return false;
    }
  },

  async rejectProposal(proposalId, skillName, reason) {
    try {
      await rejectEvolutionProposal(proposalId, skillName, reason);
      const current = this.evolutionProposals[skillName] || [];
      this.evolutionProposals = {
        ...this.evolutionProposals,
        [skillName]: current.filter((p) => p.proposal_id !== proposalId),
      };
      uni.showToast({ title: '已拒绝进化提议', icon: 'none' });
      return true;
    } catch (e) {
      console.error('[skill] rejectProposal failed:', e);
      uni.showToast({ title: '拒绝提议失败', icon: 'none' });
      return false;
    }
  },

  async loadEvolutionAudit(skillName) {
    try {
      const result = await fetchEvolutionAudit(skillName);
      this.evolutionAudit = result.entries || [];
    } catch (e) {
      /* silent */
    }
  },
});
