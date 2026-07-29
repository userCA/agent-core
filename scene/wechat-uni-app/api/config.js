/**
 * API 配置 — 对齐 scene/h5/static/src/config.ts
 *
 * API_BASE: 小程序需配置绝对地址，开发期可在微信开发者工具关闭域名校验
 * AUTH_KEYS: 鉴权字段列表，与 H5 保持一致
 * AUTH_STORAGE_KEY: 本地存储 key
 */

// 开发环境使用 localhost，生产环境替换为实际域名
export const API_BASE = 'http://127.0.0.1:8000';

export const AUTH_KEYS = ['uid', 'deviceid', 'channel', 'pacmtoken'];

export const AUTH_STORAGE_KEY = 'aigc_auth';

export const KNOWN_UIDS_KEY = 'agent_known_uids';
