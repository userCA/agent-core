/**
 * SSE 流解析器 — 移植自 scene/h5/static/src/api/sse-parser.ts
 *
 * 小程序使用 uni.request 的 enableChunked + onChunkReceived，
 * 收到 ArrayBuffer 分片后累积为 UTF-8 文本，按 SSE 协议解析。
 *
 * 协议格式：
 *   event: <channel>\n
 *   data: <json>\n
 *   \n
 *   data: [DONE]  → 终止信号
 */

/**
 * 将 ArrayBuffer 转为 UTF-8 字符串
 * @param {ArrayBuffer} buffer
 * @returns {string}
 */
function arrayBufferToString(buffer) {
  // 微信小程序环境使用 TextDecoder 或 Uint8Array
  if (typeof TextDecoder !== 'undefined') {
    return new TextDecoder().decode(new Uint8Array(buffer));
  }
  // fallback: 手动解码 UTF-8
  const bytes = new Uint8Array(buffer);
  let result = '';
  let i = 0;
  while (i < bytes.length) {
    const b = bytes[i];
    if (b < 0x80) {
      result += String.fromCharCode(b);
      i++;
    } else if (b < 0xe0) {
      result += String.fromCharCode(((b & 0x1f) << 6) | (bytes[i + 1] & 0x3f));
      i += 2;
    } else if (b < 0xf0) {
      result += String.fromCharCode(
        ((b & 0x0f) << 12) | ((bytes[i + 1] & 0x3f) << 6) | (bytes[i + 2] & 0x3f),
      );
      i += 3;
    } else {
      const cp =
        ((b & 0x07) << 18) |
        ((bytes[i + 1] & 0x3f) << 12) |
        ((bytes[i + 2] & 0x3f) << 6) |
        (bytes[i + 3] & 0x3f);
      // Convert to surrogate pair
      const offset = cp - 0x10000;
      result += String.fromCharCode(0xd800 + (offset >> 10), 0xdc00 + (offset & 0x3ff));
      i += 4;
    }
  }
  return result;
}

/**
 * 创建一个 SSE 解析器实例
 *
 * @param {function} onFrame - 回调函数，参数 { sseEvent: string, data: object }
 * @param {function} onDone - 流结束回调
 * @param {function} onError - 错误回调
 * @returns {{ feed: function, flush: function }}
 */
export function createSSEParser(onFrame, onDone, onError) {
  let buffer = '';
  // 残留的不完整 UTF-8 字节（跨 chunk 边界时使用）
  let _byteRemainder = null;

  /**
   * 解析 buffer 中完整 SSE 帧
   */
  function processBuffer() {
    // SSE 帧以 \n\n 分隔
    const parts = buffer.split('\n\n');
    // 最后一段可能不完整，保留在 buffer 中
    buffer = parts.pop() || '';

    for (const part of parts) {
      let channel = '';
      const lines = part.split('\n');
      for (const line of lines) {
        if (line.startsWith('event: ')) {
          channel = line.slice(7).trim();
        } else if (line.startsWith('data: ')) {
          const raw = line.slice(6);
          if (raw === '[DONE]') {
            if (onDone) onDone();
            return;
          }
          if (raw) {
            try {
              const data = JSON.parse(raw);
              if (onFrame) onFrame({ sseEvent: channel || 'message', data });
            } catch (e) {
              // 忽略格式错误的 JSON
              console.warn('[SSE] malformed JSON:', raw.slice(0, 100));
            }
          }
        }
      }
    }
  }

  return {
    /**
     * 喂入一个 ArrayBuffer 分片
     * @param {ArrayBuffer} chunk
     */
    feed(chunk) {
      try {
        let bytes = new Uint8Array(chunk);
        // 拼接上一次残留的不完整字节
        if (_byteRemainder) {
          const merged = new Uint8Array(_byteRemainder.length + bytes.length);
          merged.set(_byteRemainder);
          merged.set(bytes, _byteRemainder.length);
          bytes = merged;
          _byteRemainder = null;
        }
        // 检查末尾是否有不完整的 UTF-8 多字节序列
        let safeEnd = bytes.length;
        if (safeEnd > 0) {
          // 从末尾向前扫描，跳过 continuation bytes (10xxxxxx)
          let trailing = 0;
          while (trailing < 3 && safeEnd - trailing - 1 >= 0 &&
                 (bytes[safeEnd - trailing - 1] & 0xC0) === 0x80) {
            trailing++;
          }
          if (trailing > 0) {
            const leadIdx = safeEnd - trailing - 1;
            const leadByte = bytes[leadIdx];
            // 判断前导字节期望的总字节数
            let expected = 1;
            if (leadByte >= 0xC0 && leadByte < 0xE0) expected = 2;
            else if (leadByte >= 0xE0 && leadByte < 0xF0) expected = 3;
            else if (leadByte >= 0xF0) expected = 4;
            // 如果实际 continuation bytes 少于期望，说明不完整
            if (trailing < expected - 1) {
              safeEnd = leadIdx;
              _byteRemainder = bytes.slice(safeEnd);
            }
          }
        }
        // 解码安全部分
        if (safeEnd > 0) {
          const safeBytes = bytes.slice(0, safeEnd);
          if (typeof TextDecoder !== 'undefined') {
            buffer += new TextDecoder().decode(safeBytes);
          } else {
            buffer += arrayBufferToString(safeBytes.buffer);
          }
        } else if (!_byteRemainder) {
          // 整个 chunk 都是残留
          _byteRemainder = bytes;
        }
        processBuffer();
      } catch (e) {
        console.error('[SSE] feed error:', e);
        if (onError) onError(e);
      }
    },

    /**
     * 流结束后 flush 剩余 buffer
     */
    flush() {
      // 处理残留字节
      if (_byteRemainder && _byteRemainder.length > 0) {
        if (typeof TextDecoder !== 'undefined') {
          buffer += new TextDecoder().decode(_byteRemainder);
        } else {
          buffer += arrayBufferToString(_byteRemainder.buffer);
        }
        _byteRemainder = null;
      }
      if (buffer.trim()) {
        let channel = '';
        const lines = buffer.split('\n');
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            channel = line.slice(7).trim();
          } else if (line.startsWith('data: ')) {
            const raw = line.slice(6);
            if (raw === '[DONE]') {
              if (onDone) onDone();
              return;
            }
            if (raw) {
              try {
                const data = JSON.parse(raw);
                if (onFrame) onFrame({ sseEvent: channel || 'message', data });
              } catch (e) {
                // ignore
              }
            }
          }
        }
      }
      buffer = '';
    },
  };
}
