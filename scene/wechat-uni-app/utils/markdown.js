/**
 * Markdown 渲染工具 — 轻量正则解析器
 *
 * 小程序环境不支持 dangerouslySetInnerHTML，使用 <rich-text> 组件渲染 HTML。
 * 本工具将 Markdown 文本转换为安全的 HTML 字符串，供 rich-text 使用。
 *
 * 支持：
 * - 代码块 ```code```
 * - 行内代码 `code`
 * - 标题 # ## ###
 * - 加粗 **text** / __text__
 * - 斜体 *text* / _text_
 * - 无序列表 - item
 * - 有序列表 1. item
 * - 链接 [text](url)
 * - 分隔线 ---
 * - 换行
 */

/**
 * HTML 转义（防 XSS）
 */
function escapeHtml(text) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * 行内样式处理（bold/italic/code/link）
 */
function inlineMarkdown(text) {
  // 行内代码（先处理，防止内部被转义）
  text = text.replace(/`([^`]+)`/g, '<code style="background:#f0f0f0;padding:2rpx 8rpx;border-radius:6rpx;font-size:24rpx;font-family:monospace;">$1</code>');
  // 加粗
  text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  text = text.replace(/__(.+?)__/g, '<strong>$1</strong>');
  // 斜体
  text = text.replace(/\*(.+?)\*/g, '<em>$1</em>');
  text = text.replace(/_(.+?)_/g, '<em>$1</em>');
  // 链接 — 过滤危险协议，URL 转义防属性注入
  text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, label, url) => {
    if (/^\s*(javascript|data|vbscript)\s*:/i.test(url)) return label;
    const safeUrl = url.replace(/&/g, '&amp;').replace(/"/g, '&quot;');
    return `<a style="color:#3498db;" href="${safeUrl}">${label}</a>`;
  });
  return text;
}

/**
 * 将 Markdown 文本转换为 HTML
 * @param {string} md - Markdown 文本
 * @returns {string} HTML 字符串
 */
export function renderMarkdown(md) {
  if (!md) return '';

  // 预处理：去除 <think> 标签内容（如果有的话）
  md = md.replace(/<think>[\s\S]*?<\/think>/gi, '');

  const lines = md.split('\n');
  const html = [];
  let inCodeBlock = false;
  let codeBlockLang = '';
  let codeLines = [];
  let inList = false;
  let listType = ''; // 'ul' or 'ol'

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // 代码块开始/结束
    if (line.trimStart().startsWith('```')) {
      if (!inCodeBlock) {
        // 关闭之前的列表
        if (inList) {
          html.push(listType === 'ul' ? '</ul>' : '</ol>');
          inList = false;
        }
        inCodeBlock = true;
        codeBlockLang = line.trim().slice(3).trim();
        codeLines = [];
      } else {
        // 代码块结束
        const langLabel = codeBlockLang
          ? `<div style="font-size:20rpx;color:#888;padding:4rpx 16rpx;border-bottom:1rpx solid #2a2a40;">${escapeHtml(codeBlockLang)}</div>`
          : '';
        const codeContent = escapeHtml(codeLines.join('\n'));
        html.push(
          `<div style="background:#1a1a2e;border-radius:12rpx;margin:12rpx 0;overflow:hidden;">${langLabel}<div style="padding:16rpx;font-family:monospace;font-size:24rpx;color:#e0e0e0;white-space:pre-wrap;word-break:break-all;">${codeContent}</div></div>`
        );
        inCodeBlock = false;
        codeBlockLang = '';
      }
      continue;
    }

    if (inCodeBlock) {
      codeLines.push(line);
      continue;
    }

    // 空行
    if (line.trim() === '') {
      if (inList) {
        html.push(listType === 'ul' ? '</ul>' : '</ol>');
        inList = false;
      }
      html.push('<div style="height:12rpx;"></div>');
      continue;
    }

    // 分隔线
    if (/^---+$/.test(line.trim())) {
      if (inList) {
        html.push(listType === 'ul' ? '</ul>' : '</ol>');
        inList = false;
      }
      html.push('<div style="border-top:1rpx solid #e0e0e0;margin:16rpx 0;"></div>');
      continue;
    }

    // 标题
    const h3 = line.match(/^###\s+(.+)/);
    if (h3) {
      if (inList) { html.push(listType === 'ul' ? '</ul>' : '</ol>'); inList = false; }
      html.push(`<div style="font-size:28rpx;font-weight:700;color:#1a1a2e;margin:16rpx 0 8rpx;">${inlineMarkdown(escapeHtml(h3[1]))}</div>`);
      continue;
    }
    const h2 = line.match(/^##\s+(.+)/);
    if (h2) {
      if (inList) { html.push(listType === 'ul' ? '</ul>' : '</ol>'); inList = false; }
      html.push(`<div style="font-size:30rpx;font-weight:700;color:#1a1a2e;margin:20rpx 0 8rpx;">${inlineMarkdown(escapeHtml(h2[1]))}</div>`);
      continue;
    }
    const h1 = line.match(/^#\s+(.+)/);
    if (h1) {
      if (inList) { html.push(listType === 'ul' ? '</ul>' : '</ol>'); inList = false; }
      html.push(`<div style="font-size:34rpx;font-weight:700;color:#1a1a2e;margin:24rpx 0 12rpx;">${inlineMarkdown(escapeHtml(h1[1]))}</div>`);
      continue;
    }

    // 无序列表
    const ulMatch = line.match(/^(\s*)[-*]\s+(.+)/);
    if (ulMatch) {
      if (!inList || listType !== 'ul') {
        if (inList) html.push(listType === 'ul' ? '</ul>' : '</ol>');
        html.push('<ul style="padding-left:32rpx;margin:8rpx 0;">');
        inList = true;
        listType = 'ul';
      }
      html.push(`<li style="font-size:28rpx;line-height:1.7;color:#333;margin:4rpx 0;">${inlineMarkdown(escapeHtml(ulMatch[2]))}</li>`);
      continue;
    }

    // 有序列表
    const olMatch = line.match(/^(\s*)\d+\.\s+(.+)/);
    if (olMatch) {
      if (!inList || listType !== 'ol') {
        if (inList) html.push(listType === 'ul' ? '</ul>' : '</ol>');
        html.push('<ol style="padding-left:32rpx;margin:8rpx 0;">');
        inList = true;
        listType = 'ol';
      }
      html.push(`<li style="font-size:28rpx;line-height:1.7;color:#333;margin:4rpx 0;">${inlineMarkdown(escapeHtml(olMatch[2]))}</li>`);
      continue;
    }

    // 普通段落
    if (inList) {
      html.push(listType === 'ul' ? '</ul>' : '</ol>');
      inList = false;
    }
    html.push(`<div style="font-size:28rpx;line-height:1.7;color:#333;margin:4rpx 0;">${inlineMarkdown(escapeHtml(line))}</div>`);
  }

  // 关闭未结束的列表
  if (inList) {
    html.push(listType === 'ul' ? '</ul>' : '</ol>');
  }

  // 关闭未结束代码块
  if (inCodeBlock) {
    const codeContent = escapeHtml(codeLines.join('\n'));
    html.push(
      `<div style="background:#1a1a2e;border-radius:12rpx;margin:12rpx 0;overflow:hidden;"><div style="padding:16rpx;font-family:monospace;font-size:24rpx;color:#e0e0e0;white-space:pre-wrap;word-break:break-all;">${codeContent}</div></div>`
    );
  }

  return html.join('');
}
