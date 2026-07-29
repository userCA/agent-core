<template>
  <view class="chat-page" :class="'theme-' + themeStore.theme">
    <!-- 自定义顶栏 -->
    <view class="chat-header" :style="{ paddingTop: statusBarHeight + 'px' }">
      <view class="chat-header-inner">
        <view class="chat-header-left" @tap="handleNewSession">
          <text class="header-icon">+</text>
        </view>
        <text class="chat-header-title">咪兔</text>
        <view class="chat-header-right" @tap="handleAbort" v-if="chatStore.isStreaming">
          <text class="header-icon abort">■</text>
        </view>
        <view class="chat-header-right" v-else>
          <text class="header-icon"> </text>
        </view>
      </view>
    </view>

    <!-- 消息列表 -->
    <scroll-view
      class="chat-messages"
      :style="{ top: headerTotalHeight + 'px', bottom: inputHeight + 'px' }"
      scroll-y
      :scroll-into-view="scrollToId"
      :scroll-with-animation="true"
      @scrolltoupper="onScrollTop"
    >
      <!-- 加载更多指示器 -->
      <view v-if="hasMoreMessages" class="load-more-indicator" @tap="loadMoreMessages">
        <text class="load-more-text">{{ loadingMore ? '加载中...' : '↑ 加载更早的消息' }}</text>
      </view>

      <!-- 欢迎页 -->
      <view v-if="chatStore.welcomeVisible && chatStore.messages.length === 0" class="welcome-screen">
        <image class="welcome-logo" src="/static/logo.png" mode="aspectFit" />
        <text class="welcome-title">你好，我是咪兔</text>
        <text class="welcome-subtitle">你的 AI 伙伴，有什么可以帮你的？</text>
        <view class="welcome-suggestions">
          <button
            v-for="(s, i) in suggestions"
            :key="i"
            class="suggestion-pill"
            @tap="handleSuggestion(s)"
          >
            {{ s }}
          </button>
        </view>
      </view>

      <!-- 消息气泡 -->
      <view
        v-for="msg in displayMessages"
        :key="msg.id"
        :id="'msg-' + msg.id"
      >
        <!-- 用户消息 -->
        <view v-if="msg.role === 'user'" class="msg-row msg-row-user">
          <view class="bubble bubble-user">
            <text class="user-text">{{ msg.content }}</text>
          </view>
        </view>

        <!-- 错误消息 -->
        <view v-else-if="msg.role === 'error'" class="msg-row msg-row-assistant">
          <view class="msg-avatar">
            <text class="avatar-icon">🌙</text>
          </view>
          <view class="bubble bubble-error">
            <text>{{ msg.content }}</text>
          </view>
        </view>

        <!-- 助手消息 -->
        <view v-else-if="msg.role === 'assistant'" class="msg-row msg-row-assistant">
          <view class="msg-avatar">
            <text class="avatar-icon">🌙</text>
          </view>
          <view class="msg-col">
            <!-- 推理步骤卡片 -->
            <view
              v-if="getStepBlocks(msg).length > 0"
              class="bubble bubble-trace"
            >
              <view
                v-for="(block, bi) in getStepBlocks(msg)"
                :key="bi"
                class="trace-block"
              >
                <view v-if="block.type === 'think'" class="trace-think">
                  <text class="trace-label">💭 思考</text>
                  <text class="trace-text">{{ block.detail }}</text>
                </view>
                <view v-else-if="block.type === 'tool'" class="trace-tool">
                  <text class="trace-label">🔧 {{ block.label || '工具' }}</text>
                  <text v-if="block.detail" class="trace-text">{{ truncateText(block.detail, 200) }}</text>
                </view>
                <view v-else-if="block.type === 'skill'" class="trace-skill">
                  <text class="trace-label">⚡ {{ block.label || '技能' }}</text>
                  <text v-if="block.detail" class="trace-text">{{ block.detail }}</text>
                </view>
                <view v-else-if="block.type === 'text'" class="trace-intermediate-text">
                  <text class="trace-text">{{ block.text }}</text>
                </view>
              </view>
            </view>

            <!-- 内容卡片 -->
            <view v-if="getContentBlocks(msg).length > 0 || msg.content" class="bubble bubble-assistant">
              <view
                v-for="(block, bi) in getContentBlocks(msg)"
                :key="bi"
              >
                <rich-text v-if="block.type === 'text'" :nodes="renderMd(block.text)" class="msg-rich" />
                <image
                  v-else-if="block.type === 'image'"
                  :src="block.imageUrl"
                  mode="widthFix"
                  class="msg-image"
                  @tap="previewImage(block.imageUrl)"
                />
                <view v-else-if="block.type === 'widget'" class="widget-placeholder">
                  <text class="widget-icon">📦</text>
                  <text class="widget-text">交互卡片暂不支持</text>
                </view>
              </view>
              <!-- 如果无内容块但有文本 -->
              <rich-text v-if="getContentBlocks(msg).length === 0 && msg.content && msg.content !== '(empty)'" :nodes="renderMd(msg.content)" class="msg-rich" />
            </view>
          </view>
        </view>
      </view>

      <!-- 流式消息 -->
      <view v-if="showStreaming" :id="'msg-streaming'" class="msg-row msg-row-assistant">
        <view class="msg-avatar">
          <text class="avatar-icon">🌙</text>
        </view>
        <view class="msg-col">
          <!-- 流式推理块 -->
          <view v-if="nonTextStreamBlocks.length > 0" class="bubble bubble-trace">
            <view
              v-for="(block, bi) in nonTextStreamBlocks"
              :key="bi"
              class="trace-block"
            >
              <view v-if="block.type === 'think'" class="trace-think">
                <text class="trace-label">💭 思考{{ block.status === 'running' ? '中...' : '' }}</text>
                <text class="trace-text">{{ block.detail }}</text>
              </view>
              <view v-else-if="block.type === 'tool'" class="trace-tool">
                <text class="trace-label">🔧 {{ block.label || '工具' }}{{ block.status === 'running' ? '...' : '' }}</text>
                <text v-if="block.detail" class="trace-text">{{ truncateText(block.detail, 200) }}</text>
              </view>
              <view v-else-if="block.type === 'skill'" class="trace-skill">
                <text class="trace-label">⚡ {{ block.label || '技能' }}{{ block.status === 'running' ? '...' : '' }}</text>
              </view>
            </view>
          </view>

          <!-- 流式文本气泡 -->
          <view v-if="chatStore.currentText" class="bubble bubble-assistant streaming-bubble">
            <text class="msg-text streaming-text">{{ chatStore.currentText }}</text>
          </view>

          <!-- 无内容时的 typing 指示器 -->
          <view v-if="!chatStore.currentText && nonTextStreamBlocks.length === 0" class="bubble bubble-assistant streaming-bubble">
            <view class="typing-dots">
              <view class="typing-dot" />
              <view class="typing-dot" />
              <view class="typing-dot" />
            </view>
          </view>
        </view>
      </view>

      <!-- 底部间距 -->
      <view style="height: 20rpx;" />
    </scroll-view>

    <!-- HITL 人工输入表单 -->
    <view v-if="chatStore.hitlRequest" class="hitl-card">
      <text class="hitl-prompt">{{ chatStore.hitlRequest.prompt }}</text>
      <view v-for="field in hitlFields" :key="field.name" class="hitl-field">
        <text class="hitl-label">{{ field.label }}<text v-if="field.required" class="required">*</text></text>
        <input
          v-if="field.type === 'text'"
          class="hitl-input"
          :value="hitlValues[field.name] || ''"
          :placeholder="field.placeholder || ''"
          @input="hitlValues[field.name] = $event.detail.value"
        />
        <textarea
          v-else-if="field.type === 'textarea'"
          class="hitl-textarea"
          :value="hitlValues[field.name] || ''"
          :placeholder="field.placeholder || ''"
          :auto-height="true"
          @input="hitlValues[field.name] = $event.detail.value"
        />
        <picker
          v-else-if="field.type === 'select'"
          :range="(field.options || []).map(o => o.label)"
          @change="hitlValues[field.name] = (field.options[$event.detail.value] || {}).value"
        >
          <view class="hitl-picker">
            <text>{{ hitlValues[field.name] ? hitlValues[field.name] : '-- 选择 --' }}</text>
            <text class="picker-arrow">▼</text>
          </view>
        </picker>
        <!-- 语音录制字段 -->
        <view v-else-if="field.type === 'audio_record'" class="hitl-audio-field">
          <view v-if="hitlValues[field.name]" class="audio-recorded">
            <text class="audio-icon">🎵</text>
            <text class="audio-text">已录制</text>
            <text class="audio-clear" @tap="hitlValues[field.name] = ''">✕</text>
          </view>
          <button v-else class="btn-record-hitl" :disabled="hitlRecordingField === field.name" @tap="handleHitlRecord(field.name)">
            {{ hitlRecordingField === field.name ? '录制中...' : '点击录音' }}
          </button>
        </view>
        <text v-if="hitlErrors[field.name]" class="hitl-error">{{ hitlErrors[field.name] }}</text>
      </view>
      <button
        class="hitl-submit"
        :disabled="hitlSubmitting"
        @tap="handleHitlSubmit"
      >
        {{ hitlSubmitting ? '提交中...' : '提交' }}
      </button>
    </view>

    <!-- 输入区域 -->
    <view class="chat-input-area safe-bottom" :style="{ bottom: '0' }">
      <view class="chat-input-row">
        <!-- 图片上传按钮 -->
        <view class="input-btn input-img" @tap="handleChooseImage">
          <text class="btn-icon-img">+</text>
        </view>
        <!-- 语音按钮 -->
        <view
          class="input-btn input-mic"
          :class="{ 'input-mic-active': isRecording }"
          @touchstart.prevent="startRecording"
          @touchend.prevent="stopRecording"
        >
          <text class="btn-icon-mic">{{ isRecording ? '⏹' : '🎤' }}</text>
        </view>
        <textarea
          class="chat-textarea"
          v-model="inputValue"
          placeholder="写点什么…"
          :auto-height="true"
          :maxlength="-1"
          :show-confirm-bar="false"
          :adjust-position="true"
          confirm-type="send"
          @confirm="handleSend"
          @linechange="onLineChange"
        />
        <!-- 发送按钮 -->
        <button
          v-if="!chatStore.isStreaming"
          class="input-btn input-send"
          :disabled="!inputValue.trim()"
          @tap="handleSend"
        >
          <text class="btn-icon">↑</text>
        </button>
        <!-- 中止按钮 -->
        <button
          v-else
          class="input-btn input-abort"
          @tap="handleAbort"
        >
          <text class="btn-icon">■</text>
        </button>
      </view>
    </view>
  </view>
</template>

<script>
import { chatStore, sendMessage, abortStream, submitHitl } from '../../stores/chat.js';
import { sessionStore } from '../../stores/session.js';
import { uploadFile } from '../../api/client.js';
import { renderMarkdown } from '../../utils/markdown.js';
import { themeStore } from '../../stores/theme.js';

export default {
  data() {
    return {
      chatStore,
      sessionStore,
      themeStore,
      inputValue: '',
      statusBarHeight: 44,
      headerTotalHeight: 88,
      inputHeight: 100,
      scrollToId: '',
      suggestions: [
        '帮我写一首诗',
        '今天天气怎么样',
        '讲一个故事',
        '帮我做计划',
      ],
      // HITL 表单状态
      hitlValues: {},
      hitlSubmitting: false,
      hitlErrors: {},
      // 图片上传状态
      uploadedImages: [],
      // 语音录制状态
      isRecording: false,
      hitlRecordingField: null,
      // 消息分页
      displayWindowSize: 50,
      loadingMore: false,
    };
  },

  computed: {
    /** 是否显示流式消息 */
    showStreaming() {
      return chatStore.isStreaming || chatStore.currentText.length > 0;
    },

    /** 消息列表（窗口化 + 流式时隐藏最后一条助手消息） */
    displayMessages() {
      const msgs = chatStore.messages;
      // 窗口化：只显示最后 N 条
      const start = Math.max(0, msgs.length - this.displayWindowSize);
      let windowed = msgs.slice(start);
      if (this.showStreaming && windowed.length > 0 && windowed[windowed.length - 1].role === 'assistant') {
        windowed = windowed.slice(0, -1);
      }
      return windowed;
    },

    /** 是否有更多消息可加载 */
    hasMoreMessages() {
      return chatStore.messages.length > this.displayWindowSize;
    },

    /** 流式 blocks 中非文本部分（思考、工具、技能） */
    nonTextStreamBlocks() {
      return chatStore.streamBlocks.filter(
        (b) => b.type !== 'text',
      );
    },

    /** HITL 字段列表（从 JSON Schema 解析） */
    hitlFields() {
      const req = chatStore.hitlRequest;
      if (!req || !req.inputSchema) return [];
      const schema = req.inputSchema;
      // 支持 fields 数组格式
      if (Array.isArray(schema.fields)) return schema.fields;
      // 从 JSON Schema properties 解析
      const requiredSet = new Set(schema.required || []);
      const fields = [];
      for (const [name, prop] of Object.entries(schema.properties || {})) {
        const isRequired = requiredSet.has(name);
        const label = prop.title || name;
        if (Array.isArray(prop.enum)) {
          fields.push({ type: 'select', name, label, required: isRequired,
            options: prop.enum.map((v) => ({ label: v, value: v })) });
        } else if (prop.format === 'audio_record' || prop.type === 'audio') {
          fields.push({ type: 'audio_record', name, label, required: isRequired });
        } else if (prop.type === 'string' && ((prop.maxLength || 0) > 200 || prop.format === 'textarea')) {
          fields.push({ type: 'textarea', name, label, placeholder: prop.description, required: isRequired });
        } else {
          fields.push({ type: 'text', name, label, placeholder: prop.description, required: isRequired });
        }
      }
      return fields;
    },
  },

  watch: {
    'chatStore.messages.length'() {
      this.scrollToBottom();
    },
    'chatStore.currentText'() {
      this.scrollToBottom();
    },
    'chatStore.streamBlocks.length'() {
      this.scrollToBottom();
    },
    // HITL 请求变化时重置表单
    'chatStore.hitlRequest'(val) {
      if (val) {
        this.hitlValues = {};
        this.hitlErrors = {};
        this.hitlSubmitting = false;
      }
    },
  },

  onLoad() {
    // 获取状态栏高度
    const sysInfo = uni.getSystemInfoSync();
    this.statusBarHeight = sysInfo.statusBarHeight || 44;
    this.headerTotalHeight = this.statusBarHeight + 44;

    // 计算输入区域高度（近似值）
    this.inputHeight = 100 + (sysInfo.safeAreaInsets?.bottom || 0);

    // 初始化录音管理器
    this._pageAlive = true;
    this._recorderManager = uni.getRecorderManager();
    this._recorderManager.onStop((res) => {
      if (!this._pageAlive) return;
      this.isRecording = false;
      if (res.tempFilePath) {
        if (this.hitlRecordingField) {
          // HITL 录音
          this.hitlValues[this.hitlRecordingField] = res.tempFilePath;
          this.hitlRecordingField = null;
          uni.showToast({ title: '录音完成', icon: 'success' });
        } else {
          // 主输入录音：上传并发送
          this._sendVoiceMessage(res.tempFilePath);
        }
      }
    });
    this._recorderManager.onError((err) => {
      if (!this._pageAlive) return;
      this.isRecording = false;
      this.hitlRecordingField = null;
      uni.showToast({ title: '录音失败', icon: 'none' });
    });
  },

  onShow() {
    // 页面显示时滚动到底部
    this.scrollToBottom();
  },

  onUnload() {
    this._pageAlive = false;
  },

  methods: {
    /** 发送消息 */
    handleSend() {
      const text = this.inputValue.trim();
      if (!text) return;
      this.inputValue = '';
      sendMessage(text);
      this.scrollToBottom();
    },

    /** 中止流式 */
    handleAbort() {
      abortStream();
    },

    /** 新建会话 */
    handleNewSession() {
      sessionStore.createSession();
      chatStore.reset();
    },

    /** 欢迎建议点击 */
    handleSuggestion(text) {
      sendMessage(text);
    },

    /** 获取消息的推理步骤 blocks */
    getStepBlocks(msg) {
      if (!msg.blocks && !msg.intermediateBlocks) return [];
      const isStep = (b) =>
        b.type === 'think' || b.type === 'tool' || b.type === 'skill' ||
        (b.type === 'text' && b.turnPhase === 'intermediate');
      if (msg.intermediateBlocks) {
        return msg.intermediateBlocks.filter(isStep);
      }
      return (msg.blocks || []).filter(isStep);
    },

    /** 获取消息的内容 blocks */
    getContentBlocks(msg) {
      if (!msg.blocks) return [];
      const isContent = (b) =>
        b.type === 'text' && b.turnPhase !== 'intermediate' ||
        b.type === 'image' || b.type === 'video' || b.type === 'widget';
      if (msg.intermediateBlocks) {
        // 有 intermediateBlocks 时，内容块来自 final blocks
        return (msg.blocks || []).filter(isContent);
      }
      return (msg.blocks || []).filter((b) => b.type === 'text' || b.type === 'image' || b.type === 'video' || b.type === 'widget');
    },

    /** Markdown 渲染 */
    renderMd(text) {
      return renderMarkdown(text);
    },

    /** 截断文本 */
    truncateText(text, maxLen) {
      if (!text) return '';
      return text.length > maxLen ? text.slice(0, maxLen) + '...' : text;
    },

    /** 预览图片 */
    previewImage(url) {
      uni.previewImage({ urls: [url], current: url });
    },

    /** 滚动到底部 */
    scrollToBottom() {
      this.$nextTick(() => {
        const msgs = this.displayMessages;
        if (this.showStreaming) {
          this.scrollToId = 'msg-streaming';
        } else if (msgs.length > 0) {
          this.scrollToId = 'msg-' + msgs[msgs.length - 1].id;
        }
        // 重置以允许重复滚动到同一元素
        setTimeout(() => { this.scrollToId = ''; }, 50);
      });
    },

    onScrollTop() {
      // 滚动到顶部时自动加载更多
      if (this.hasMoreMessages && !this.loadingMore) {
        this.loadMoreMessages();
      }
    },

    /** 加载更多早期消息 */
    loadMoreMessages() {
      this.loadingMore = true;
      // 简单扩大窗口
      setTimeout(() => {
        this.displayWindowSize = Math.min(
          this.displayWindowSize + 30,
          chatStore.messages.length
        );
        this.loadingMore = false;
      }, 300);
    },

    onLineChange(e) {
      // 输入框行数变化，更新输入区域高度
      const lines = e.detail?.lineCount || 1;
      this.inputHeight = Math.min(100 + (lines - 1) * 22, 220) + (uni.getSystemInfoSync().safeAreaInsets?.bottom || 0);
    },

    /** HITL 表单提交 */
    async handleHitlSubmit() {
      const req = chatStore.hitlRequest;
      if (!req) return;

      // 验证必填字段
      const errors = {};
      for (const field of this.hitlFields) {
        if (field.required) {
          const val = this.hitlValues[field.name];
          if (val === undefined || val === null || val === '') {
            errors[field.name] = `${field.label} 必填`;
          }
        }
      }
      if (Object.keys(errors).length > 0) {
        this.hitlErrors = errors;
        return;
      }

      this.hitlSubmitting = true;
      try {
        await submitHitl(req.toolCallId, { ...this.hitlValues });
        this.hitlValues = {};
        this.hitlErrors = {};
      } catch (e) {
        // 错误已在 submitHitl 中 toast
      } finally {
        this.hitlSubmitting = false;
      }
    },

    /** 开始录音 */
    startRecording() {
      this.isRecording = true;
      this._recorderManager.start({
        duration: 60000,
        sampleRate: 16000,
        numberOfChannels: 1,
        encodeBitRate: 96000,
        format: 'mp3',
      });
    },

    /** 停止录音 */
    stopRecording() {
      if (this.isRecording) {
        this._recorderManager.stop();
      }
    },

    /** HITL 录音 */
    handleHitlRecord(fieldName) {
      this.hitlRecordingField = fieldName;
      this._recorderManager.start({
        duration: 120000,
        sampleRate: 16000,
        numberOfChannels: 1,
        encodeBitRate: 96000,
        format: 'mp3',
      });
    },

    /** 发送语音消息 */
    async _sendVoiceMessage(tempFilePath) {
      uni.showLoading({ title: '上传中...' });
      const authHeaders = sessionStore.buildAuthHeaders();
      try {
        const result = await uploadFile(tempFilePath, authHeaders);
        uni.hideLoading();
        if (result.url) {
          sendMessage(`[语音] ${result.url}`);
        }
      } catch (e) {
        uni.hideLoading();
        uni.showToast({ title: '语音上传失败', icon: 'none' });
      }
    },

    /** 选择图片并上传 */
    handleChooseImage() {
      uni.chooseMedia({
        count: 9,
        mediaType: ['image'],
        sourceType: ['album', 'camera'],
        success: async (res) => {
          const files = res.tempFiles || [];
          if (files.length === 0) return;

          uni.showLoading({ title: '上传中...' });
          const authHeaders = sessionStore.buildAuthHeaders();

          try {
            for (const file of files) {
              const result = await uploadFile(file.tempFilePath, authHeaders);
              if (result.url) {
                this.uploadedImages.push(result.url);
              }
            }
            uni.hideLoading();
            // 将图片 URL 作为消息发送
            if (this.uploadedImages.length > 0) {
              const imgText = this.uploadedImages.map((url) => `[图片] ${url}`).join('\n');
              sendMessage(imgText);
              this.uploadedImages = [];
            }
          } catch (e) {
            uni.hideLoading();
            this.uploadedImages = [];
            uni.showToast({ title: '上传失败', icon: 'none' });
          }
        },
      });
    },
  },
};
</script>

<style scoped>
.chat-page {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f5f5f5;
}

/* ---- Header ---- */
.chat-header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  background: #fff;
  border-bottom: 1rpx solid #eee;
}

.chat-header-inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 88rpx;
  padding: 0 24rpx;
}

.chat-header-title {
  font-size: 34rpx;
  font-weight: 600;
  color: #1a1a2e;
}

.chat-header-left,
.chat-header-right {
  width: 80rpx;
  height: 80rpx;
  display: flex;
  align-items: center;
  justify-content: center;
}

.header-icon {
  font-size: 36rpx;
  color: #333;
}

.header-icon.abort {
  color: #e74c3c;
}

/* ---- Messages ---- */
.chat-messages {
  position: fixed;
  left: 0;
  right: 0;
  padding: 20rpx 24rpx;
}

/* ---- Load More ---- */
.load-more-indicator {
  display: flex;
  justify-content: center;
  padding: 20rpx 0;
}

.load-more-text {
  font-size: 24rpx;
  color: var(--ash, #888);
}

/* ---- Welcome ---- */
.welcome-screen {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding-top: 120rpx;
}

.welcome-logo {
  width: 160rpx;
  height: 160rpx;
  margin-bottom: 32rpx;
}

.welcome-title {
  font-size: 40rpx;
  font-weight: 700;
  color: #1a1a2e;
  margin-bottom: 16rpx;
}

.welcome-subtitle {
  font-size: 28rpx;
  color: #888;
  margin-bottom: 60rpx;
}

.welcome-suggestions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 16rpx;
  padding: 0 40rpx;
}

.suggestion-pill {
  padding: 16rpx 32rpx;
  background: #fff;
  border: 2rpx solid #e0e0e0;
  border-radius: 32rpx;
  font-size: 26rpx;
  color: #555;
  line-height: 1.4;
}

/* ---- Message Row ---- */
.msg-row {
  display: flex;
  margin-bottom: 24rpx;
  animation: fadeIn 0.2s ease-out;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8rpx); }
  to { opacity: 1; transform: translateY(0); }
}

.msg-row-user {
  justify-content: flex-end;
}

.msg-row-assistant {
  justify-content: flex-start;
}

.msg-avatar {
  width: 64rpx;
  height: 64rpx;
  border-radius: 50%;
  background: #e8e8f0;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 16rpx;
  flex-shrink: 0;
}

.avatar-icon {
  font-size: 32rpx;
}

.msg-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12rpx;
  min-width: 0;
}

/* ---- Bubbles ---- */
.bubble {
  padding: 20rpx 28rpx;
  border-radius: 20rpx;
  max-width: 85%;
  word-break: break-all;
}

.bubble-user {
  background: #1a1a2e;
  color: #fff;
  border-bottom-right-radius: 6rpx;
  max-width: 75%;
}

.user-text {
  font-size: 28rpx;
  line-height: 1.6;
  white-space: pre-wrap;
}

.bubble-assistant {
  background: #fff;
  color: #333;
  border-bottom-left-radius: 6rpx;
  border: 1rpx solid #eee;
}

.bubble-error {
  background: #fff0f0;
  color: #c0392b;
  border: 1rpx solid #fcc;
  border-bottom-left-radius: 6rpx;
  font-size: 26rpx;
}

.bubble-trace {
  background: #f8f8fc;
  border: 1rpx solid #e8e8f0;
  border-radius: 16rpx;
  padding: 16rpx 20rpx;
}

.msg-text {
  font-size: 28rpx;
  line-height: 1.7;
  white-space: pre-wrap;
}

.msg-rich {
  font-size: 28rpx;
  line-height: 1.7;
  word-break: break-all;
}

.widget-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 24rpx;
  background: #f8f8fc;
  border: 2rpx dashed #d0d0d8;
  border-radius: 12rpx;
  margin: 8rpx 0;
}

.widget-icon {
  font-size: 40rpx;
  margin-bottom: 8rpx;
}

.widget-text {
  font-size: 24rpx;
  color: #999;
}

/* ---- Voice Recording ---- */
.input-mic {
  width: 64rpx;
  height: 64rpx;
  border-radius: 50%;
  background: #f0f0f0;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.input-mic-active {
  background: #e74c3c !important;
}

.btn-icon-mic {
  font-size: 28rpx;
}

/* ---- HITL Audio ---- */
.hitl-audio-field {
  margin-top: 8rpx;
}

.btn-record-hitl {
  height: 64rpx;
  font-size: 26rpx;
  background: #f5f5f5;
  color: #333;
  border: 2rpx dashed #ccc;
  border-radius: 12rpx;
  line-height: 64rpx;
}

.btn-record-hitl::after { border: none; }
.btn-record-hitl[disabled] { background: #e0e0e0; color: #999; }

.audio-recorded {
  display: flex;
  align-items: center;
  gap: 12rpx;
  padding: 12rpx 20rpx;
  background: #f0f8f0;
  border-radius: 12rpx;
}

.audio-icon { font-size: 32rpx; }
.audio-text { font-size: 26rpx; color: #27ae60; flex: 1; }
.audio-clear { font-size: 28rpx; color: #e74c3c; padding: 8rpx; }

.msg-image {
  width: 100%;
  max-width: 480rpx;
  border-radius: 12rpx;
  margin-top: 8rpx;
}

/* ---- Trace blocks ---- */
.trace-block {
  margin-bottom: 12rpx;
}

.trace-block:last-child {
  margin-bottom: 0;
}

.trace-label {
  font-size: 24rpx;
  font-weight: 600;
  color: #666;
  margin-bottom: 4rpx;
  display: block;
}

.trace-text {
  font-size: 24rpx;
  color: #888;
  line-height: 1.5;
  white-space: pre-wrap;
  display: block;
  max-height: 200rpx;
  overflow: hidden;
}

.trace-think,
.trace-tool,
.trace-skill,
.trace-intermediate-text {
  padding: 4rpx 0;
}

/* ---- Streaming ---- */
.streaming-bubble {
  min-height: 60rpx;
}

.streaming-text {
  white-space: pre-wrap;
}

.typing-dots {
  display: flex;
  gap: 8rpx;
  padding: 8rpx 0;
}

.typing-dot {
  width: 12rpx;
  height: 12rpx;
  border-radius: 50%;
  background: #999;
  animation: typing 1.4s infinite ease-in-out;
}

.typing-dot:nth-child(2) {
  animation-delay: 0.2s;
}

.typing-dot:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes typing {
  0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
  40% { opacity: 1; transform: scale(1); }
}

/* ---- Input Area ---- */
.chat-input-area {
  position: fixed;
  left: 0;
  right: 0;
  background: #fff;
  border-top: 1rpx solid #eee;
  padding: 16rpx 24rpx;
  z-index: 100;
}

.chat-input-row {
  display: flex;
  align-items: flex-end;
  gap: 16rpx;
}

.chat-textarea {
  flex: 1;
  min-height: 72rpx;
  max-height: 240rpx;
  padding: 16rpx 24rpx;
  background: #f5f5f5;
  border-radius: 36rpx;
  font-size: 28rpx;
  line-height: 1.5;
}

.input-btn {
  width: 72rpx;
  height: 72rpx;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border: none;
  padding: 0;
  margin: 0;
  line-height: 72rpx;
}

.input-btn::after {
  border: none;
}

.input-send {
  background: #1a1a2e;
}

.input-send[disabled] {
  background: #ccc;
}

.input-abort {
  background: #e74c3c;
}

.btn-icon {
  color: #fff;
  font-size: 32rpx;
  font-weight: 700;
}

/* ---- Image Upload Button ---- */
.input-img {
  width: 64rpx;
  height: 64rpx;
  border-radius: 50%;
  background: #f0f0f0;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.btn-icon-img {
  font-size: 36rpx;
  color: #666;
  font-weight: 300;
  line-height: 1;
}

/* ---- HITL Card ---- */
.hitl-card {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 200;
  background: #fff;
  border-top: 2rpx solid #e0e0e0;
  padding: 24rpx;
  max-height: 60vh;
  overflow-y: auto;
}

.hitl-prompt {
  font-size: 28rpx;
  color: #333;
  font-weight: 600;
  margin-bottom: 20rpx;
  display: block;
}

.hitl-field {
  margin-bottom: 16rpx;
}

.hitl-label {
  font-size: 24rpx;
  color: #666;
  margin-bottom: 8rpx;
  display: block;
}

.required {
  color: #e74c3c;
}

.hitl-input {
  height: 64rpx;
  padding: 0 20rpx;
  background: #f5f5f5;
  border-radius: 12rpx;
  font-size: 28rpx;
}

.hitl-textarea {
  width: 100%;
  min-height: 120rpx;
  padding: 16rpx 20rpx;
  background: #f5f5f5;
  border-radius: 12rpx;
  font-size: 28rpx;
  box-sizing: border-box;
}

.hitl-picker {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 64rpx;
  padding: 0 20rpx;
  background: #f5f5f5;
  border-radius: 12rpx;
  font-size: 28rpx;
}

.picker-arrow {
  font-size: 20rpx;
  color: #999;
}

.hitl-error {
  font-size: 22rpx;
  color: #e74c3c;
  margin-top: 4rpx;
  display: block;
}

.hitl-submit {
  width: 100%;
  height: 80rpx;
  background: #1a1a2e;
  color: #fff;
  font-size: 28rpx;
  border-radius: 12rpx;
  margin-top: 16rpx;
  line-height: 80rpx;
  border: none;
}

.hitl-submit::after {
  border: none;
}

.hitl-submit[disabled] {
  background: #ccc;
}
</style>
