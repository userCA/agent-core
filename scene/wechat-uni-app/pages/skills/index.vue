<template>
  <view class="skills-page" :class="'theme-' + themeStore.theme">
    <!-- 顶部搜索栏 -->
    <view class="page-header">
      <view class="search-bar">
        <text class="search-icon">🔍</text>
        <input
          class="search-input"
          v-model="search"
          placeholder="搜索技能..."
          confirm-type="search"
        />
      </view>
      <view class="header-actions">
        <button class="btn-action" @tap="handleShowCreate" :disabled="importing">创建</button>
        <button class="btn-action" @tap="handleImport" :disabled="importing">
          {{ importing ? '导入中...' : '导入' }}
        </button>
      </view>
    </view>

    <!-- 统计 -->
    <view class="section-title" v-if="!skillStore.loading && skillStore.skills.length > 0">
      已启用 {{ enabledCount }}/{{ skillStore.skills.length }}
    </view>

    <!-- 加载中 -->
    <view v-if="skillStore.loading" class="loading-state">
      <text class="loading-text">加载中...</text>
    </view>

    <!-- 空状态 -->
    <view v-else-if="skillStore.skills.length === 0" class="empty-state">
      <text class="empty-icon">⚡</text>
      <text class="empty-text">暂无技能</text>
      <text class="empty-sub">点击"导入"按钮添加技能文件</text>
    </view>

    <!-- 搜索无结果 -->
    <view v-else-if="search && filteredSkills.length === 0" class="empty-state">
      <text class="empty-icon">🔍</text>
      <text class="empty-text">无匹配技能</text>
    </view>

    <!-- 技能列表 -->
    <view v-else class="skill-grid">
      <view
        v-for="skill in filteredSkills"
        :key="skill.name"
        class="skill-card"
        :class="{ 'skill-off': !skillStore.isEnabled(skill.name) }"
      >
        <view class="card-head">
          <text class="card-icon">⚡</text>
          <text class="card-title">{{ skill.name }}</text>
          <switch
            class="skill-switch"
            :checked="skillStore.isEnabled(skill.name)"
            @change="skillStore.toggleSkill(skill.name)"
            color="#1a1a2e"
          />
        </view>
        <text class="card-desc">{{ skill.description }}</text>
        <text class="card-meta">/skill:{{ skill.name }}</text>

        <!-- Evolution Panel -->
        <view class="evo-panel">
          <view class="evo-trigger" @tap="toggleEvoPanel(skill.name)">
            <text class="evo-label">Evolution</text>
            <view v-if="getTraces(skill.name)" class="evo-stats">
              <text class="evo-stat">{{ getTraces(skill.name).total }} traces</text>
              <text class="evo-stat evo-ok">{{ getTraces(skill.name).success }} pass</text>
              <text class="evo-stat" :class="{ 'evo-err': getTraces(skill.name).failure > 0 }">
                {{ getTraces(skill.name).failure }} fail
              </text>
            </view>
            <text v-else class="evo-empty">Awaiting data</text>
          </view>

          <!-- 展开内容 -->
          <view v-if="expandedEvo === skill.name" class="evo-body">
            <!-- 空状态 -->
            <view v-if="!getTraces(skill.name) && !getProposals(skill.name).length" class="evo-empty-detail">
              <text class="evo-empty-title">暂无执行追踪数据</text>
              <text class="evo-empty-desc">技能执行时会自动采集追踪数据，积累足够数据后可分析进化提议。</text>
            </view>

            <!-- 分析按钮 -->
            <view class="evo-actions">
              <button
                class="btn-analyze"
                :disabled="skillStore.evolutionLoading || analyzingSkill === skill.name || !getTraces(skill.name)"
                @tap="handleAnalyze(skill.name)"
              >
                {{ analyzingSkill === skill.name ? '分析中...' : '分析追踪数据' }}
              </button>
            </view>

            <!-- 提议列表 -->
            <view v-if="getProposals(skill.name).length > 0" class="evo-proposals">
              <text class="evo-section-title">提议 ({{ getProposals(skill.name).length }})</text>
              <view
                v-for="(p, pi) in getProposals(skill.name)"
                :key="p.proposal_id"
                class="proposal-card"
                :class="'pp-op-' + p.operation"
              >
                <view class="pp-head">
                  <text class="pp-op-badge">{{ opLabels[p.operation] || p.operation }}</text>
                  <text v-if="p.target_rule_id" class="pp-rule">{{ p.target_rule_id }}</text>
                  <text class="pp-conf">{{ Math.round(p.confidence * 100) }}%</text>
                </view>
                <text v-if="p.rationale" class="pp-rationale">{{ p.rationale }}</text>
                <!-- Diff -->
                <view class="pp-diff">
                  <view
                    v-for="(line, li) in parseDiff(p.diff)"
                    :key="li"
                    class="diff-line"
                    :class="'diff-' + line.type"
                  >
                    <text class="diff-sign">{{ line.type === 'add' ? '+' : line.type === 'del' ? '-' : '' }}</text>
                    <text class="diff-text">{{ line.text.replace(/^[#+-]\s?/, '') }}</text>
                  </view>
                </view>
                <!-- 操作按钮 -->
                <view class="pp-actions">
                  <button class="btn-accept" @tap="handleAccept(p.proposal_id, skill.name)">接受</button>
                  <button v-if="rejectingId !== p.proposal_id" class="btn-reject" @tap="rejectingId = p.proposal_id">拒绝</button>
                  <view v-else class="reject-row">
                    <input class="reject-input" v-model="rejectReason" placeholder="原因（可选）" />
                    <button class="btn-reject" @tap="handleReject(p.proposal_id, skill.name)">确认</button>
                    <button class="btn-cancel" @tap="rejectingId = ''; rejectReason = ''">取消</button>
                  </view>
                </view>
              </view>
            </view>

            <!-- 审计记录 -->
            <view v-if="skillAudit.length > 0" class="evo-audit">
              <text class="evo-section-title">审计记录 ({{ skillAudit.length }})</text>
              <view v-for="entry in skillAudit" :key="entry.audit_id" class="audit-row" :class="'audit-' + entry.action">
                <text class="audit-mark">{{ entry.action === 'accept' ? '✔' : '✘' }}</text>
                <text class="audit-op">{{ opLabels[entry.operation] || entry.operation }}</text>
                <text class="audit-time">{{ formatTime(entry.timestamp) }}</text>
                <text v-if="entry.reject_reason" class="audit-reason">— {{ entry.reject_reason }}</text>
              </view>
            </view>
          </view>
        </view>
      </view>
    </view>

    <!-- 工具列表 -->
    <view v-if="skillStore.tools.length > 0" class="tools-section">
      <view class="section-title">可用工具 ({{ filteredTools.length }})</view>
      <view class="search-bar" style="margin-bottom: 16rpx;">
        <text class="search-icon">🔍</text>
        <input
          class="search-input"
          v-model="toolSearch"
          placeholder="搜索工具..."
          confirm-type="search"
        />
      </view>
      <view v-if="filteredTools.length === 0" class="empty-sub-text">无匹配工具</view>
      <view v-else class="tool-grid">
        <view
          v-for="tool in pagedTools"
          :key="tool.name"
          class="tool-card"
          @tap="toggleToolExpand(tool.name)"
        >
          <view class="tool-head">
            <text class="tool-name">{{ tool.name }}</text>
            <text v-if="tool.description.length > 60" class="tool-expand-icon">
              {{ expandedTools.has(tool.name) ? '▲' : '▼' }}
            </text>
          </view>
          <text class="tool-desc">
            {{ expandedTools.has(tool.name) || tool.description.length <= 60 ? tool.description : tool.description.slice(0, 60) + '…' }}
          </text>
        </view>
      </view>
      <!-- 分页 -->
      <view v-if="totalToolPages > 1" class="pagination">
        <button class="btn-page" :disabled="toolPage <= 1" @tap="toolPage--">上一页</button>
        <text class="page-info">{{ toolPage }} / {{ totalToolPages }}</text>
        <button class="btn-page" :disabled="toolPage >= totalToolPages" @tap="toolPage++">下一页</button>
      </view>
    </view>

    <!-- 创建技能弹窗 -->
    <view v-if="showCreate" class="modal-backdrop" @tap="showCreate = false">
      <view class="modal-content" @tap.stop>
        <text class="modal-title">创建技能</text>
        <view class="modal-field">
          <text class="field-label">名称 <text class="required">*</text></text>
          <input class="field-input" v-model="createName" placeholder="英文名称，如 my-skill" />
          <text v-if="createErrors.name" class="field-error">{{ createErrors.name }}</text>
        </view>
        <view class="modal-field">
          <text class="field-label">描述</text>
          <input class="field-input" v-model="createDesc" placeholder="可选，简要描述" />
        </view>
        <view class="modal-field">
          <text class="field-label">内容 <text class="required">*</text></text>
          <textarea
            class="field-textarea"
            v-model="createContent"
            placeholder="粘贴 Markdown 技能描述..."
            :maxlength="-1"
          />
          <text v-if="createErrors.content" class="field-error">{{ createErrors.content }}</text>
        </view>
        <view class="modal-actions">
          <button class="btn-modal-cancel" @tap="showCreate = false">取消</button>
          <button
            class="btn-modal-create"
            :disabled="creating || !createName.trim() || !createContent.trim()"
            @tap="handleCreate"
          >
            {{ creating ? '创建中...' : '创建' }}
          </button>
        </view>
      </view>
    </view>
  </view>
</template>

<script>
import { skillStore } from '../../stores/skill.js';
import { themeStore } from '../../stores/theme.js';

const OP_LABELS = { add: '添加', modify: '修改', delete: '删除', merge: '合并' };
const TOOLS_PER_PAGE = 24;

export default {
  data() {
    return {
      skillStore,
      themeStore,
      search: '',
      toolSearch: '',
      importing: false,
      showCreate: false,
      creating: false,
      createName: '',
      createDesc: '',
      createContent: '',
      createErrors: {},
      // Evolution panel state
      expandedEvo: null,
      analyzingSkill: null,
      rejectingId: '',
      rejectReason: '',
      opLabels: OP_LABELS,
      // Tools pagination
      toolPage: 1,
      expandedTools: new Set(),
    };
  },

  computed: {
    filteredSkills() {
      if (!this.search.trim()) return skillStore.skills;
      const q = this.search.toLowerCase();
      return skillStore.skills.filter(
        (s) => s.name.toLowerCase().includes(q) || s.description.toLowerCase().includes(q)
      );
    },
    enabledCount() {
      return skillStore.skills.filter((s) => skillStore.isEnabled(s.name)).length;
    },
    filteredTools() {
      if (!this.toolSearch.trim()) return skillStore.tools;
      const q = this.toolSearch.toLowerCase();
      return skillStore.tools.filter(
        (t) => t.name.toLowerCase().includes(q) || t.description.toLowerCase().includes(q)
      );
    },
    totalToolPages() {
      return Math.ceil(this.filteredTools.length / TOOLS_PER_PAGE);
    },
    pagedTools() {
      const start = (this.toolPage - 1) * TOOLS_PER_PAGE;
      return this.filteredTools.slice(start, start + TOOLS_PER_PAGE);
    },
    skillAudit() {
      if (!this.expandedEvo) return [];
      return skillStore.evolutionAudit
        .filter((e) => e.skill_name === this.expandedEvo)
        .slice(0, 12);
    },
  },

  onLoad() {
    skillStore.loadCapabilities();
    if (skillStore.evolutionSummary === null) {
      skillStore.loadEvolutionSummary();
    }
  },

  methods: {
    getTraces(skillName) {
      const counts = skillStore.evolutionSummary?.trace_counts?.[skillName];
      return counts && counts.total > 0 ? counts : null;
    },
    getProposals(skillName) {
      return skillStore.evolutionProposals[skillName] || [];
    },
    parseDiff(raw) {
      if (!raw) return [];
      return raw.split('\n').map((line) => {
        if (!line) return { type: 'ctx', text: '' };
        if (line[0] === '#' || line.startsWith('//')) return { type: 'meta', text: line };
        if (line[0] === '+') return { type: 'add', text: line };
        if (line[0] === '-') return { type: 'del', text: line };
        return { type: 'ctx', text: line };
      });
    },
    formatTime(ts) {
      if (!ts) return '';
      const d = new Date(ts * 1000);
      return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
    },
    toggleEvoPanel(skillName) {
      if (this.expandedEvo === skillName) {
        this.expandedEvo = null;
      } else {
        this.expandedEvo = skillName;
        skillStore.loadEvolutionProposals(skillName);
        skillStore.loadEvolutionAudit(skillName);
      }
    },
    async handleAnalyze(skillName) {
      this.analyzingSkill = skillName;
      await skillStore.analyzeEvolution(skillName);
      this.analyzingSkill = null;
    },
    async handleAccept(proposalId, skillName) {
      await skillStore.acceptProposal(proposalId, skillName);
      await skillStore.loadEvolutionAudit(skillName);
    },
    async handleReject(proposalId, skillName) {
      await skillStore.rejectProposal(proposalId, skillName, this.rejectReason || undefined);
      this.rejectingId = '';
      this.rejectReason = '';
      await skillStore.loadEvolutionAudit(skillName);
    },
    handleShowCreate() {
      this.createName = '';
      this.createDesc = '';
      this.createContent = '';
      this.createErrors = {};
      this.showCreate = true;
    },
    async handleCreate() {
      const errs = {};
      if (!this.createName.trim()) errs.name = '名称不能为空';
      if (!this.createContent.trim()) errs.content = '内容不能为空';
      if (Object.keys(errs).length > 0) {
        this.createErrors = errs;
        return;
      }
      this.creating = true;
      try {
        let frontmatter = '---\n';
        frontmatter += `name: ${this.createName.trim()}\n`;
        if (this.createDesc.trim()) {
          frontmatter += `description: ${this.createDesc.trim()}\n`;
        }
        frontmatter += '---\n\n';
        const fullContent = frontmatter + this.createContent.trim() + '\n';
        const ok = await skillStore.importSkill(this.createName.trim(), fullContent);
        if (ok) {
          this.showCreate = false;
          uni.showToast({ title: `技能"${this.createName}"创建成功`, icon: 'success' });
        }
      } catch (e) {
        uni.showToast({ title: '创建技能失败', icon: 'none' });
      } finally {
        this.creating = false;
      }
    },
    handleImport() {
      // 微信小程序使用 chooseMessageFile 选择 .md 文件
      if (typeof uni.chooseMessageFile === 'function') {
        uni.chooseMessageFile({
          count: 1,
          type: 'file',
          extension: ['.md'],
          success: async (res) => {
            const file = res.tempFiles[0];
            if (!file) return;
            this.importing = true;
            try {
              // 读取文件内容
              const fs = uni.getFileSystemManager();
              const content = fs.readFileSync(file.path, 'utf-8');
              const name = file.name.replace(/\.md$/i, '');
              await skillStore.importSkill(name, content);
              uni.showToast({ title: '导入成功', icon: 'success' });
            } catch (e) {
              uni.showToast({ title: '导入技能失败', icon: 'none' });
            } finally {
              this.importing = false;
            }
          },
        });
      } else {
        uni.showToast({ title: '当前环境不支持文件选择', icon: 'none' });
      }
    },
    toggleToolExpand(name) {
      const next = new Set(this.expandedTools);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      this.expandedTools = next;
    },
  },
};
</script>

<style scoped>
.skills-page {
  min-height: 100vh;
  background: #f5f5f5;
  padding: 24rpx;
  padding-bottom: 40rpx;
}

.page-header {
  margin-bottom: 24rpx;
}

.search-bar {
  display: flex;
  align-items: center;
  background: #fff;
  border-radius: 16rpx;
  padding: 12rpx 20rpx;
  gap: 12rpx;
  border: 1rpx solid #eee;
}

.search-icon {
  font-size: 28rpx;
  flex-shrink: 0;
}

.search-input {
  flex: 1;
  font-size: 28rpx;
  height: 48rpx;
}

.header-actions {
  display: flex;
  gap: 16rpx;
  margin-top: 16rpx;
}

.btn-action {
  flex: 1;
  height: 64rpx;
  font-size: 26rpx;
  background: #fff;
  color: #333;
  border: 1rpx solid #ddd;
  border-radius: 12rpx;
  line-height: 64rpx;
  padding: 0;
}

.btn-action::after {
  border: none;
}

.btn-action[disabled] {
  color: #999;
  background: #f0f0f0;
}

.section-title {
  font-size: 24rpx;
  color: #888;
  margin-bottom: 16rpx;
  padding-left: 4rpx;
}

.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding-top: 120rpx;
  gap: 16rpx;
}

.loading-text { font-size: 28rpx; color: #999; }
.empty-icon { font-size: 80rpx; }
.empty-text { font-size: 32rpx; font-weight: 600; color: #333; }
.empty-sub { font-size: 24rpx; color: #999; }
.empty-sub-text { font-size: 26rpx; color: #999; text-align: center; padding: 40rpx 0; }

/* Skill cards */
.skill-grid {
  display: flex;
  flex-direction: column;
  gap: 20rpx;
}

.skill-card {
  background: #fff;
  border-radius: 20rpx;
  padding: 24rpx;
  border: 2rpx solid #e0e0e0;
}

.skill-card.skill-off {
  opacity: 0.6;
  border-color: #f0f0f0;
}

.card-head {
  display: flex;
  align-items: center;
  gap: 12rpx;
  margin-bottom: 12rpx;
}

.card-icon { font-size: 28rpx; }
.card-title {
  flex: 1;
  font-size: 30rpx;
  font-weight: 600;
  color: #1a1a2e;
}

.skill-switch {
  transform: scale(0.7);
}

.card-desc {
  font-size: 26rpx;
  color: #666;
  line-height: 1.5;
  margin-bottom: 8rpx;
  display: block;
}

.card-meta {
  font-size: 22rpx;
  color: #aaa;
  font-family: monospace;
  display: block;
}

/* Evolution Panel */
.evo-panel {
  margin-top: 16rpx;
  border-top: 1rpx solid #f0f0f0;
  padding-top: 12rpx;
}

.evo-trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8rpx 0;
}

.evo-label {
  font-size: 24rpx;
  font-weight: 600;
  color: #666;
}

.evo-stats {
  display: flex;
  gap: 16rpx;
  font-size: 22rpx;
}

.evo-stat { color: #888; }
.evo-stat.evo-ok { color: #27ae60; }
.evo-stat.evo-err { color: #e74c3c; }
.evo-empty { font-size: 22rpx; color: #bbb; }

.evo-body {
  padding-top: 16rpx;
}

.evo-empty-detail {
  text-align: center;
  padding: 24rpx 0;
}

.evo-empty-title {
  font-size: 26rpx;
  color: #999;
  display: block;
  margin-bottom: 8rpx;
}

.evo-empty-desc {
  font-size: 22rpx;
  color: #bbb;
  display: block;
  line-height: 1.5;
}

.evo-actions {
  margin-bottom: 16rpx;
}

.btn-analyze {
  height: 56rpx;
  font-size: 24rpx;
  background: #1a1a2e;
  color: #fff;
  border-radius: 12rpx;
  border: none;
  line-height: 56rpx;
}

.btn-analyze::after { border: none; }
.btn-analyze[disabled] { background: #ccc; }

.evo-section-title {
  font-size: 24rpx;
  font-weight: 600;
  color: #666;
  margin-bottom: 12rpx;
  display: block;
}

/* Proposal card */
.proposal-card {
  background: #fafafa;
  border: 1rpx solid #e8e8f0;
  border-radius: 12rpx;
  padding: 16rpx;
  margin-bottom: 16rpx;
}

.proposal-card.pp-op-add { border-left: 6rpx solid #27ae60; }
.proposal-card.pp-op-modify { border-left: 6rpx solid #f39c12; }
.proposal-card.pp-op-delete { border-left: 6rpx solid #e74c3c; }
.proposal-card.pp-op-merge { border-left: 6rpx solid #3498db; }

.pp-head {
  display: flex;
  align-items: center;
  gap: 12rpx;
  margin-bottom: 8rpx;
}

.pp-op-badge {
  font-size: 22rpx;
  color: #fff;
  background: #666;
  padding: 4rpx 12rpx;
  border-radius: 8rpx;
}

.pp-rule {
  font-size: 22rpx;
  color: #888;
  font-family: monospace;
}

.pp-conf {
  margin-left: auto;
  font-size: 24rpx;
  font-weight: 600;
  color: #1a1a2e;
}

.pp-rationale {
  font-size: 24rpx;
  color: #555;
  line-height: 1.5;
  margin-bottom: 12rpx;
  display: block;
}

/* Diff */
.pp-diff {
  background: #1a1a2e;
  border-radius: 8rpx;
  padding: 12rpx;
  margin-bottom: 12rpx;
  max-height: 300rpx;
  overflow: hidden;
}

.diff-line {
  display: flex;
  font-size: 20rpx;
  font-family: monospace;
  line-height: 1.6;
}

.diff-sign {
  width: 24rpx;
  flex-shrink: 0;
  color: #888;
}

.diff-text {
  flex: 1;
  color: #ddd;
  word-break: break-all;
}

.diff-add .diff-sign, .diff-add .diff-text { color: #2ecc71; }
.diff-del .diff-sign, .diff-del .diff-text { color: #e74c3c; }
.diff-meta .diff-text { color: #f39c12; }

.pp-actions {
  display: flex;
  gap: 12rpx;
  align-items: center;
}

.btn-accept, .btn-reject, .btn-cancel {
  font-size: 22rpx;
  height: 48rpx;
  line-height: 48rpx;
  border-radius: 8rpx;
  padding: 0 20rpx;
  border: none;
}

.btn-accept { background: #27ae60; color: #fff; }
.btn-reject { background: #e74c3c; color: #fff; }
.btn-cancel { background: #eee; color: #666; }
.btn-accept::after, .btn-reject::after, .btn-cancel::after { border: none; }

.reject-row {
  display: flex;
  align-items: center;
  gap: 8rpx;
  flex: 1;
}

.reject-input {
  flex: 1;
  height: 48rpx;
  font-size: 22rpx;
  background: #f5f5f5;
  border-radius: 8rpx;
  padding: 0 12rpx;
}

/* Audit */
.audit-row {
  display: flex;
  align-items: center;
  gap: 12rpx;
  padding: 8rpx 0;
  border-bottom: 1rpx solid #f0f0f0;
  font-size: 22rpx;
}

.audit-mark { color: #27ae60; font-size: 24rpx; }
.audit-reject .audit-mark { color: #e74c3c; }
.audit-op { color: #666; }
.audit-time { color: #aaa; margin-left: auto; }
.audit-reason { color: #999; font-size: 20rpx; }

/* Tools section */
.tools-section {
  margin-top: 40rpx;
}

.tool-grid {
  display: flex;
  flex-direction: column;
  gap: 12rpx;
}

.tool-card {
  background: #fff;
  border-radius: 16rpx;
  padding: 20rpx;
  border: 1rpx solid #eee;
}

.tool-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8rpx;
}

.tool-name {
  font-size: 28rpx;
  font-weight: 600;
  color: #333;
}

.tool-expand-icon {
  font-size: 20rpx;
  color: #999;
}

.tool-desc {
  font-size: 24rpx;
  color: #666;
  line-height: 1.5;
  display: block;
}

.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16rpx;
  margin-top: 24rpx;
}

.btn-page {
  font-size: 24rpx;
  height: 56rpx;
  line-height: 56rpx;
  padding: 0 24rpx;
  background: #fff;
  border: 1rpx solid #ddd;
  border-radius: 8rpx;
  color: #333;
}

.btn-page::after { border: none; }
.btn-page[disabled] { color: #ccc; }

.page-info {
  font-size: 24rpx;
  color: #888;
  font-family: monospace;
}

/* Modal */
.modal-backdrop {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 999;
  display: flex;
  align-items: center;
  justify-content: center;
}

.modal-content {
  width: 85%;
  max-height: 80vh;
  background: #fff;
  border-radius: 24rpx;
  padding: 32rpx;
  overflow-y: auto;
}

.modal-title {
  font-size: 34rpx;
  font-weight: 700;
  color: #1a1a2e;
  margin-bottom: 24rpx;
  display: block;
}

.modal-field {
  margin-bottom: 20rpx;
}

.field-label {
  font-size: 26rpx;
  color: #555;
  margin-bottom: 8rpx;
  display: block;
}

.required { color: #e74c3c; }

.field-input {
  height: 64rpx;
  padding: 0 20rpx;
  background: #f5f5f5;
  border-radius: 12rpx;
  font-size: 28rpx;
}

.field-textarea {
  width: 100%;
  min-height: 240rpx;
  padding: 16rpx 20rpx;
  background: #f5f5f5;
  border-radius: 12rpx;
  font-size: 26rpx;
  box-sizing: border-box;
}

.field-error {
  font-size: 22rpx;
  color: #e74c3c;
  margin-top: 4rpx;
  display: block;
}

.modal-actions {
  display: flex;
  gap: 16rpx;
  margin-top: 24rpx;
}

.btn-modal-cancel, .btn-modal-create {
  flex: 1;
  height: 72rpx;
  font-size: 28rpx;
  border-radius: 12rpx;
  border: none;
  line-height: 72rpx;
}

.btn-modal-cancel { background: #f0f0f0; color: #666; }
.btn-modal-create { background: #1a1a2e; color: #fff; }
.btn-modal-cancel::after, .btn-modal-create::after { border: none; }
.btn-modal-create[disabled] { background: #ccc; }
</style>
