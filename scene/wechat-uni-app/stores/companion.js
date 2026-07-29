/**
 * Companion Store — 移植自 scene/h5/static/src/stores/companion-store.ts
 *
 * 边界规则：前端不在本地判断心情。
 * mood 来自 emotion.frontend_mood（由 setEmotion 设置），
 * 或默认为 'sleeping'（首次 SSE 事件之前）。
 *
 * 后端是情绪和骨骼数据的唯一来源。
 */

import { reactive } from 'vue';
import { fetchCompanion, hatchCompanion } from '../api/client.js';

export const companionStore = reactive({
  /** @type {'sleeping'|'happy'|'calm'|'sad'|'excited'|'curious'} */
  mood: 'sleeping',
  muted: false,
  /** @type {object|null} CompanionBones 数据 */
  bones: null,
  /** @type {object|null} CompanionEmotion */
  emotion: null,
  /** @type {{text: string, ttl_ms: number}|null} */
  bubble: null,
  revealed: false,

  /** SSE companion 事件触发时调用 */
  setEmotion(emotion) {
    this.emotion = emotion;
    if (emotion && emotion.frontend_mood) {
      this.mood = emotion.frontend_mood;
    }
  },

  setBubble(bubble) {
    this.bubble = bubble;
  },

  toggleMuted() {
    this.muted = !this.muted;
  },

  /**
   * 从后端加载伴侣数据
   * 优先尝试 hatch（首次会生成名字和个性），失败则降级为仅获取骨骼
   * @param {string} uid
   */
  async reveal(uid) {
    try {
      const data = await hatchCompanion(uid);
      this.bones = data;
      this.revealed = true;
      return;
    } catch (e) {
      // hatch 失败，降级为获取已有骨骼
    }
    try {
      const bones = await fetchCompanion(uid);
      this.bones = bones;
      this.revealed = true;
    } catch (e) {
      console.warn('[companion] reveal failed:', e);
      this.revealed = true;
    }
  },

  /** 重置所有状态（用户退出/切换 uid） */
  reset() {
    this.bones = null;
    this.emotion = null;
    this.revealed = false;
    this.mood = 'sleeping';
    this.bubble = null;
  },
});
