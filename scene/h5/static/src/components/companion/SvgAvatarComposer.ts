/**
 * SVG Avatar Composer — 基于 svg-avatar-composer.html 核心逻辑
 * 为每个用户生成独一无二的像素风格宠物头像
 */

import type { BreedId } from './breed-sprites';

export type EyeType = 'dot' | 'sparkle' | 'big' | 'round' | 'heart' | 'star';
export type EarType = 'cat' | 'rabbit' | 'mix';
export type HatType = 'none' | 'crown' | 'tophat' | 'propeller' | 'halo' | 'wizard' | 'beanie' | 'tinyduck';
export type PaletteType = 'default' | 'warm' | 'cool' | 'cream' | 'charcoal' | 'snow';

interface RectData {
  x: number;
  y: number;
  w: number;
  h: number;
  fill: string;
}

interface BreedData {
  rects: RectData[];
  earIdx: [number, number];
  eyeIdx: [number, number];
  colors: { B: string; D: string };
}

// ═══════════════ V3 EXACT RECT DATA ═══════════════
const V3: Record<string, BreedData> = {
  orange_tabby: {
    rects: [{x:6,y:2,w:3,h:3,fill:"#FF9F43"},{x:7,y:1,w:2,h:1,fill:"#FF9F43"},{x:23,y:2,w:3,h:3,fill:"#FF9F43"},{x:23,y:1,w:2,h:1,fill:"#FF9F43"},{x:7,y:2,w:1,h:2,fill:"#CC6611"},{x:24,y:2,w:1,h:2,fill:"#CC6611"},{x:5,y:4,w:22,h:14,fill:"#FF9F43"},{x:4,y:5,w:24,h:12,fill:"#FF9F43"},{x:3,y:7,w:26,h:8,fill:"#FF9F43"},{x:8,y:5,w:1,h:3,fill:"#CC6611"},{x:9,y:5,w:1,h:2,fill:"#CC6611"},{x:23,y:5,w:1,h:3,fill:"#CC6611"},{x:22,y:5,w:1,h:2,fill:"#CC6611"},{x:10,y:6,w:1,h:1,fill:"#CC6611"},{x:21,y:6,w:1,h:1,fill:"#CC6611"},{x:5,y:10,w:2,h:1,fill:"#CC6611"},{x:25,y:10,w:2,h:1,fill:"#CC6611"},{x:4,y:12,w:2,h:1,fill:"#CC6611"},{x:26,y:12,w:2,h:1,fill:"#CC6611"},{x:9,y:10,w:4,h:3,fill:"#fff"},{x:19,y:10,w:4,h:3,fill:"#fff"},{x:10,y:11,w:2,h:2,fill:"#38B149"},{x:20,y:11,w:2,h:2,fill:"#38B149"},{x:11,y:11,w:1,h:2,fill:"#000"},{x:21,y:11,w:1,h:2,fill:"#000"},{x:10,y:10,w:1,h:1,fill:"#fff"},{x:20,y:10,w:1,h:1,fill:"#fff"},{x:15,y:14,w:2,h:1,fill:"#FF7777"},{x:14,y:15,w:1,h:1,fill:"#CC6611"},{x:17,y:15,w:1,h:1,fill:"#CC6611"},{x:15,y:16,w:2,h:1,fill:"#CC6611"},{x:7,y:17,w:18,h:10,fill:"#FF9F43"},{x:5,y:19,w:22,h:8,fill:"#FF9F43"},{x:4,y:21,w:24,h:6,fill:"#FF9F43"},{x:7,y:18,w:3,h:1,fill:"#CC6611"},{x:14,y:18,w:4,h:1,fill:"#CC6611"},{x:22,y:18,w:3,h:1,fill:"#CC6611"},{x:5,y:20,w:4,h:1,fill:"#CC6611"},{x:12,y:20,w:8,h:1,fill:"#CC6611"},{x:23,y:20,w:4,h:1,fill:"#CC6611"},{x:4,y:22,w:5,h:1,fill:"#CC6611"},{x:11,y:22,w:10,h:1,fill:"#CC6611"},{x:23,y:22,w:5,h:1,fill:"#CC6611"},{x:6,y:24,w:4,h:1,fill:"#CC6611"},{x:22,y:24,w:4,h:1,fill:"#CC6611"},{x:26,y:23,w:3,h:2,fill:"#FF9F43"},{x:28,y:21,w:2,h:2,fill:"#FF9F43"},{x:29,y:19,w:2,h:2,fill:"#FF9F43"},{x:27,y:23,w:1,h:1,fill:"#CC6611"},{x:29,y:21,w:1,h:1,fill:"#CC6611"},{x:7,y:26,w:3,h:2,fill:"#FF9F43"},{x:22,y:26,w:3,h:2,fill:"#FF9F43"},{x:8,y:28,w:2,h:1,fill:"#FF9F43"},{x:23,y:28,w:2,h:1,fill:"#FF9F43"}],
    earIdx: [0, 5], eyeIdx: [19, 26], colors: { B: "#FF9F43", D: "#CC6611" }
  },
  tuxedo: {
    rects: [{x:6,y:2,w:3,h:3,fill:"#111"},{x:7,y:1,w:2,h:1,fill:"#111"},{x:23,y:3,w:3,h:3,fill:"#fff"},{x:23,y:2,w:2,h:1,fill:"#fff"},{x:7,y:2,w:1,h:2,fill:"#333"},{x:24,y:3,w:1,h:2,fill:"#ccc"},{x:5,y:4,w:22,h:14,fill:"#111"},{x:4,y:5,w:24,h:12,fill:"#111"},{x:3,y:7,w:26,h:8,fill:"#111"},{x:20,y:4,w:7,h:8,fill:"#fff"},{x:22,y:3,w:5,h:2,fill:"#fff"},{x:18,y:5,w:2,h:5,fill:"#fff"},{x:12,y:12,w:8,h:5,fill:"#fff"},{x:10,y:13,w:2,h:3,fill:"#fff"},{x:20,y:13,w:2,h:3,fill:"#fff"},{x:9,y:10,w:4,h:3,fill:"#fff"},{x:19,y:10,w:4,h:3,fill:"#fff"},{x:10,y:11,w:2,h:2,fill:"#44AAFF"},{x:20,y:11,w:2,h:2,fill:"#44AAFF"},{x:11,y:11,w:1,h:2,fill:"#000"},{x:21,y:11,w:1,h:2,fill:"#000"},{x:10,y:10,w:1,h:1,fill:"#fff"},{x:20,y:10,w:1,h:1,fill:"#fff"},{x:15,y:14,w:2,h:1,fill:"#FF9999"},{x:14,y:15,w:1,h:1,fill:"#111"},{x:17,y:15,w:1,h:1,fill:"#111"},{x:15,y:16,w:2,h:1,fill:"#111"},{x:14,y:16,w:1,h:1,fill:"#fff"},{x:17,y:16,w:1,h:1,fill:"#fff"},{x:7,y:17,w:18,h:10,fill:"#111"},{x:5,y:19,w:22,h:8,fill:"#111"},{x:4,y:21,w:24,h:6,fill:"#111"},{x:11,y:17,w:10,h:8,fill:"#fff"},{x:9,y:19,w:2,h:5,fill:"#fff"},{x:21,y:19,w:2,h:5,fill:"#fff"},{x:14,y:19,w:1,h:1,fill:"#111"},{x:17,y:19,w:1,h:1,fill:"#111"},{x:15,y:20,w:2,h:1,fill:"#111"},{x:14,y:21,w:1,h:1,fill:"#111"},{x:17,y:21,w:1,h:1,fill:"#111"},{x:7,y:26,w:3,h:2,fill:"#fff"},{x:22,y:26,w:3,h:2,fill:"#fff"},{x:8,y:28,w:2,h:1,fill:"#fff"},{x:23,y:28,w:2,h:1,fill:"#fff"},{x:26,y:23,w:3,h:2,fill:"#111"},{x:28,y:21,w:2,h:2,fill:"#fff"},{x:29,y:19,w:2,h:2,fill:"#111"}],
    earIdx: [0, 5], eyeIdx: [15, 22], colors: { B: "#111", D: "#1a1a1a" }
  },
  calico: {
    rects: [{x:6,y:2,w:3,h:3,fill:"#FF9F43"},{x:7,y:1,w:2,h:1,fill:"#FF9F43"},{x:23,y:2,w:3,h:3,fill:"#111"},{x:23,y:1,w:2,h:1,fill:"#111"},{x:7,y:2,w:1,h:2,fill:"#CC6611"},{x:24,y:2,w:1,h:2,fill:"#333"},{x:5,y:4,w:22,h:14,fill:"#fff"},{x:4,y:5,w:24,h:12,fill:"#fff"},{x:3,y:7,w:26,h:8,fill:"#fff"},{x:4,y:5,w:8,h:8,fill:"#FF9F43"},{x:3,y:7,w:3,h:5,fill:"#FF9F43"},{x:20,y:4,w:7,h:9,fill:"#111"},{x:25,y:7,w:4,h:5,fill:"#111"},{x:10,y:6,w:3,h:3,fill:"#FF9F43"},{x:19,y:7,w:2,h:2,fill:"#111"},{x:9,y:10,w:4,h:3,fill:"#fff"},{x:19,y:10,w:4,h:3,fill:"#fff"},{x:10,y:11,w:2,h:2,fill:"#38B149"},{x:11,y:11,w:1,h:2,fill:"#000"},{x:10,y:10,w:1,h:1,fill:"#fff"},{x:20,y:11,w:2,h:2,fill:"#44AAFF"},{x:21,y:11,w:1,h:2,fill:"#000"},{x:20,y:10,w:1,h:1,fill:"#fff"},{x:15,y:14,w:2,h:1,fill:"#FF9999"},{x:14,y:15,w:1,h:1,fill:"#CC6611"},{x:17,y:15,w:1,h:1,fill:"#CC6611"},{x:15,y:16,w:2,h:1,fill:"#CC6611"},{x:7,y:17,w:18,h:10,fill:"#fff"},{x:5,y:19,w:22,h:8,fill:"#fff"},{x:4,y:21,w:24,h:6,fill:"#fff"},{x:7,y:18,w:6,h:6,fill:"#FF9F43"},{x:20,y:19,w:7,h:7,fill:"#111"},{x:5,y:21,w:4,h:4,fill:"#FF9F43"},{x:26,y:23,w:3,h:2,fill:"#111"},{x:28,y:21,w:2,h:2,fill:"#FF9F43"},{x:29,y:19,w:2,h:2,fill:"#111"},{x:7,y:26,w:3,h:2,fill:"#FF9F43"},{x:22,y:26,w:3,h:2,fill:"#111"},{x:8,y:28,w:2,h:1,fill:"#FF9F43"},{x:23,y:28,w:2,h:1,fill:"#111"}],
    earIdx: [0, 5], eyeIdx: [15, 22], colors: { B: "#fff", D: "#111" }
  },
  siamese: {
    rects: [{x:6,y:2,w:3,h:3,fill:"#5a3a2a"},{x:7,y:1,w:2,h:1,fill:"#5a3a2a"},{x:23,y:2,w:3,h:3,fill:"#5a3a2a"},{x:23,y:1,w:2,h:1,fill:"#5a3a2a"},{x:7,y:2,w:1,h:2,fill:"#3a2a1a"},{x:24,y:2,w:1,h:2,fill:"#3a2a1a"},{x:5,y:4,w:22,h:14,fill:"#D4C0A8"},{x:4,y:5,w:24,h:12,fill:"#D4C0A8"},{x:3,y:7,w:26,h:8,fill:"#D4C0A8"},{x:6,y:4,w:20,h:6,fill:"#5a3a2a"},{x:5,y:5,w:22,h:4,fill:"#5a3a2a"},{x:7,y:3,w:18,h:2,fill:"#5a3a2a"},{x:8,y:8,w:16,h:1,fill:"#8a6a5a"},{x:9,y:9,w:14,h:1,fill:"#aa8a7a"},{x:9,y:10,w:4,h:2,fill:"#fff"},{x:19,y:10,w:4,h:2,fill:"#fff"},{x:10,y:10,w:2,h:2,fill:"#4080c0"},{x:20,y:10,w:2,h:2,fill:"#4080c0"},{x:11,y:10,w:1,h:2,fill:"#000"},{x:21,y:10,w:1,h:2,fill:"#000"},{x:10,y:10,w:1,h:1,fill:"#fff"},{x:20,y:10,w:1,h:1,fill:"#fff"},{x:5,y:11,w:2,h:3,fill:"#C4B098"},{x:25,y:11,w:2,h:3,fill:"#C4B098"},{x:15,y:13,w:2,h:1,fill:"#aa7a6a"},{x:14,y:14,w:1,h:1,fill:"#5a3a2a"},{x:17,y:14,w:1,h:1,fill:"#5a3a2a"},{x:15,y:15,w:2,h:1,fill:"#5a3a2a"},{x:7,y:17,w:18,h:10,fill:"#D4C0A8"},{x:5,y:19,w:22,h:8,fill:"#D4C0A8"},{x:4,y:21,w:24,h:6,fill:"#D4C0A8"},{x:7,y:18,w:18,h:1,fill:"#C4B098"},{x:5,y:20,w:22,h:1,fill:"#C4B098"},{x:4,y:22,w:24,h:1,fill:"#C4B098"},{x:7,y:26,w:3,h:2,fill:"#5a3a2a"},{x:22,y:26,w:3,h:2,fill:"#5a3a2a"},{x:8,y:28,w:2,h:1,fill:"#5a3a2a"},{x:23,y:28,w:2,h:1,fill:"#5a3a2a"},{x:26,y:23,w:3,h:2,fill:"#5a3a2a"},{x:28,y:21,w:2,h:2,fill:"#5a3a2a"},{x:29,y:19,w:2,h:2,fill:"#5a3a2a"}],
    earIdx: [0, 5], eyeIdx: [14, 21], colors: { B: "#D4C0A8", D: "#5a3a2a" }
  },
  black_cat: {
    rects: [{x:6,y:2,w:3,h:3,fill:"#141414"},{x:7,y:1,w:2,h:1,fill:"#141414"},{x:23,y:2,w:3,h:3,fill:"#141414"},{x:23,y:1,w:2,h:1,fill:"#141414"},{x:7,y:2,w:1,h:2,fill:"#0a0a0a"},{x:24,y:2,w:1,h:2,fill:"#0a0a0a"},{x:5,y:4,w:22,h:14,fill:"#141414"},{x:4,y:5,w:24,h:12,fill:"#141414"},{x:3,y:7,w:26,h:8,fill:"#141414"},{x:8,y:6,w:16,h:6,fill:"#1c1c1c"},{x:10,y:5,w:12,h:2,fill:"#1c1c1c"},{x:9,y:10,w:4,h:3,fill:"#FFC840"},{x:19,y:10,w:4,h:3,fill:"#FFC840"},{x:8,y:10,w:1,h:3,fill:"#aa8800"},{x:13,y:10,w:1,h:3,fill:"#aa8800"},{x:18,y:10,w:1,h:3,fill:"#aa8800"},{x:23,y:10,w:1,h:3,fill:"#aa8800"},{x:11,y:10,w:1,h:3,fill:"#000"},{x:21,y:10,w:1,h:3,fill:"#000"},{x:10,y:10,w:1,h:1,fill:"#fff"},{x:20,y:10,w:1,h:1,fill:"#fff"},{x:15,y:14,w:2,h:1,fill:"#333"},{x:14,y:15,w:1,h:1,fill:"#222"},{x:17,y:15,w:1,h:1,fill:"#222"},{x:15,y:15,w:2,h:1,fill:"#1a1a1a"},{x:7,y:17,w:18,h:10,fill:"#141414"},{x:5,y:19,w:22,h:8,fill:"#141414"},{x:4,y:21,w:24,h:6,fill:"#141414"},{x:7,y:18,w:18,h:1,fill:"#1c1c1c"},{x:5,y:20,w:22,h:1,fill:"#1c1c1c"},{x:4,y:22,w:24,h:1,fill:"#1c1c1c"},{x:26,y:23,w:3,h:2,fill:"#141414"},{x:28,y:21,w:2,h:2,fill:"#141414"},{x:29,y:19,w:2,h:2,fill:"#141414"},{x:7,y:26,w:3,h:2,fill:"#141414"},{x:22,y:26,w:3,h:2,fill:"#141414"},{x:8,y:28,w:2,h:1,fill:"#0a0a0a"},{x:23,y:28,w:2,h:1,fill:"#0a0a0a"}],
    earIdx: [0, 5], eyeIdx: [11, 20], colors: { B: "#141414", D: "#0a0a0a" }
  },
  ragdoll: {
    rects: [{x:5,y:2,w:4,h:4,fill:"#E8DDD0"},{x:6,y:1,w:3,h:1,fill:"#E8DDD0"},{x:23,y:2,w:4,h:4,fill:"#E8DDD0"},{x:23,y:1,w:3,h:1,fill:"#E8DDD0"},{x:4,y:3,w:1,h:3,fill:"#D8CDC0"},{x:27,y:3,w:1,h:3,fill:"#D8CDC0"},{x:5,y:1,w:2,h:1,fill:"#D8CDC0"},{x:25,y:1,w:2,h:1,fill:"#D8CDC0"},{x:6,y:3,w:2,h:2,fill:"#C0A890"},{x:24,y:3,w:2,h:2,fill:"#C0A890"},{x:5,y:5,w:22,h:14,fill:"#E8DDD0"},{x:4,y:6,w:24,h:12,fill:"#E8DDD0"},{x:3,y:8,w:26,h:8,fill:"#E8DDD0"},{x:7,y:5,w:18,h:7,fill:"#C0A890"},{x:6,y:6,w:20,h:5,fill:"#C0A890"},{x:8,y:4,w:16,h:2,fill:"#C0A890"},{x:8,y:9,w:16,h:1,fill:"#D0C0A8"},{x:9,y:10,w:14,h:1,fill:"#D8C8B0"},{x:9,y:11,w:4,h:3,fill:"#fff"},{x:19,y:11,w:4,h:3,fill:"#fff"},{x:10,y:12,w:2,h:2,fill:"#6090D0"},{x:20,y:12,w:2,h:2,fill:"#6090D0"},{x:11,y:12,w:1,h:2,fill:"#000"},{x:21,y:12,w:1,h:2,fill:"#000"},{x:10,y:11,w:1,h:1,fill:"#fff"},{x:20,y:11,w:1,h:1,fill:"#fff"},{x:12,y:14,w:8,h:3,fill:"#fff"},{x:10,y:15,w:2,h:2,fill:"#fff"},{x:20,y:15,w:2,h:2,fill:"#fff"},{x:15,y:14,w:2,h:1,fill:"#FFAAAA"},{x:14,y:16,w:1,h:1,fill:"#C0A890"},{x:17,y:16,w:1,h:1,fill:"#C0A890"},{x:15,y:17,w:2,h:1,fill:"#C0A890"},{x:6,y:18,w:20,h:10,fill:"#E8DDD0"},{x:4,y:20,w:24,h:8,fill:"#E8DDD0"},{x:3,y:22,w:26,h:6,fill:"#E8DDD0"},{x:6,y:19,w:20,h:1,fill:"#D8CDC0"},{x:4,y:21,w:24,h:1,fill:"#D8CDC0"},{x:3,y:23,w:26,h:1,fill:"#D8CDC0"},{x:3,y:20,w:1,h:4,fill:"#D8CDC0"},{x:28,y:20,w:1,h:4,fill:"#D8CDC0"},{x:11,y:19,w:10,h:7,fill:"#fff"},{x:9,y:21,w:2,h:4,fill:"#fff"},{x:21,y:21,w:2,h:4,fill:"#fff"},{x:6,y:27,w:4,h:2,fill:"#fff"},{x:22,y:27,w:4,h:2,fill:"#fff"},{x:7,y:29,w:2,h:1,fill:"#fff"},{x:23,y:29,w:2,h:1,fill:"#fff"},{x:27,y:24,w:3,h:3,fill:"#E8DDD0"},{x:29,y:22,w:2,h:2,fill:"#D8CDC0"},{x:30,y:20,w:1,h:2,fill:"#E8DDD0"}],
    earIdx: [0, 9], eyeIdx: [18, 25], colors: { B: "#E8DDD0", D: "#C0A890" }
  },
  scottish_fold: {
    rects: [{x:5,y:4,w:5,h:2,fill:"#D4B896"},{x:6,y:3,w:4,h:1,fill:"#D4B896"},{x:22,y:4,w:5,h:2,fill:"#D4B896"},{x:22,y:3,w:4,h:1,fill:"#D4B896"},{x:5,y:4,w:5,h:1,fill:"#C4A886"},{x:22,y:4,w:5,h:1,fill:"#C4A886"},{x:6,y:4,w:3,h:1,fill:"#C4A886"},{x:23,y:4,w:3,h:1,fill:"#C4A886"},{x:5,y:5,w:22,h:14,fill:"#D4B896"},{x:4,y:6,w:24,h:12,fill:"#D4B896"},{x:3,y:8,w:26,h:8,fill:"#D4B896"},{x:3,y:10,w:2,h:4,fill:"#D4B896"},{x:27,y:10,w:2,h:4,fill:"#D4B896"},{x:2,y:11,w:1,h:2,fill:"#D4B896"},{x:29,y:11,w:1,h:2,fill:"#D4B896"},{x:8,y:7,w:16,h:5,fill:"#E4C8A6"},{x:10,y:6,w:12,h:2,fill:"#E4C8A6"},{x:9,y:11,w:4,h:4,fill:"#fff"},{x:19,y:11,w:4,h:4,fill:"#fff"},{x:10,y:12,w:2,h:2,fill:"#88CC44"},{x:20,y:12,w:2,h:2,fill:"#88CC44"},{x:11,y:12,w:1,h:2,fill:"#000"},{x:21,y:12,w:1,h:2,fill:"#000"},{x:10,y:11,w:1,h:1,fill:"#fff"},{x:20,y:11,w:1,h:1,fill:"#fff"},{x:6,y:13,w:2,h:2,fill:"#E8A090"},{x:24,y:13,w:2,h:2,fill:"#E8A090"},{x:15,y:15,w:2,h:1,fill:"#FFAAAA"},{x:14,y:16,w:1,h:1,fill:"#C4A886"},{x:17,y:16,w:1,h:1,fill:"#C4A886"},{x:15,y:17,w:2,h:1,fill:"#C4A886"},{x:7,y:18,w:18,h:10,fill:"#D4B896"},{x:5,y:20,w:22,h:8,fill:"#D4B896"},{x:4,y:22,w:24,h:6,fill:"#D4B896"},{x:7,y:19,w:18,h:1,fill:"#C4A886"},{x:5,y:21,w:22,h:1,fill:"#C4A886"},{x:4,y:23,w:24,h:1,fill:"#C4A886"},{x:3,y:21,w:1,h:4,fill:"#D4B896"},{x:28,y:21,w:1,h:4,fill:"#D4B896"},{x:26,y:24,w:3,h:2,fill:"#D4B896"},{x:28,y:22,w:2,h:2,fill:"#C4A886"},{x:7,y:27,w:3,h:2,fill:"#E4C8A6"},{x:22,y:27,w:3,h:2,fill:"#E4C8A6"},{x:8,y:29,w:2,h:1,fill:"#E4C8A6"},{x:23,y:29,w:2,h:1,fill:"#E4C8A6"}],
    earIdx: [0, 7], eyeIdx: [17, 24], colors: { B: "#D4B896", D: "#C4A886" }
  },
};

// ═══════════════ PALETTE REMAP ═══════════════
const PAL: Record<string, () => { B: string; D: string } | null> = {
  default: () => null,
  warm: () => ({ B: "#FF9F43", D: "#CC6611" }),
  cool: () => ({ B: "#9BA4B5", D: "#6B7B8D" }),
  cream: () => ({ B: "#D4C0A8", D: "#B0A090" }),
  charcoal: () => ({ B: "#3a3a3a", D: "#1a1a1a" }),
  snow: () => ({ B: "#F5F0EB", D: "#D0C8C0" }),
};

// ═══════════════ EYE OVERLAYS ═══════════════
function eyeDot(b: RectData, bg?: string): RectData[] {
  const iy = b.h <= 2 ? b.y : b.y + 1;
  const ih = 2;
  return [
    { x: b.x, y: b.y, w: b.w, h: b.h, fill: bg || '#fff' },
    { x: b.x + 1, y: iy, w: 2, h: ih, fill: '#38B149' },
    { x: b.x + 2, y: iy, w: 1, h: ih, fill: '#000' },
    { x: b.x + 1, y: b.y, w: 1, h: 1, fill: '#fff' },
  ];
}

function eyeSparkle(b: RectData, bg?: string): RectData[] {
  const iy = b.h <= 2 ? b.y : b.y + 1;
  const ih = 2;
  return [
    { x: b.x, y: b.y, w: b.w, h: b.h, fill: bg || '#fff' },
    { x: b.x + 1, y: iy, w: 2, h: ih, fill: '#FFC840' },
    { x: b.x + 2, y: iy, w: 1, h: ih, fill: '#aa7700' },
    { x: b.x + 1, y: b.y, w: 1, h: 1, fill: '#fff' },
    { x: b.x, y: b.y, w: 1, h: 1, fill: '#FFF8A0' },
    { x: b.x + b.w - 1, y: b.y + b.h - 1, w: 1, h: 1, fill: '#FFF8A0' },
  ];
}

function eyeBig(b: RectData, bg?: string): RectData[] {
  return [
    { x: b.x, y: b.y, w: b.w, h: b.h, fill: bg || '#fff' },
    { x: b.x + 1, y: b.y + 1, w: b.w - 1, h: b.h - 1, fill: '#2a2a2a' },
    { x: b.x + 1, y: b.y, w: 1, h: 1, fill: '#fff' },
    { x: b.x + 3, y: b.y + 1, w: 1, h: 1, fill: '#fff' },
    { x: b.x + 2, y: b.y + 2, w: 1, h: 1, fill: '#fff' },
  ];
}

function eyeRound(b: RectData, bg?: string): RectData[] {
  return [
    { x: b.x, y: b.y, w: b.w, h: b.h, fill: bg || '#fff' },
    { x: b.x + 1, y: b.y + 1, w: 2, h: b.h - 1, fill: '#44AAFF' },
    { x: b.x + 2, y: b.y + 1, w: 1, h: b.h - 1, fill: '#000' },
    { x: b.x + 1, y: b.y + 1, w: 1, h: 1, fill: bg || '#fff' },
    { x: b.x + 1, y: b.y, w: 1, h: 1, fill: '#fff' },
  ];
}

function eyeHeart(b: RectData, bg?: string): RectData[] {
  return [
    { x: b.x, y: b.y, w: b.w, h: b.h, fill: bg || '#fff' },
    { x: b.x + 1, y: b.y + 1, w: 2, h: 2, fill: '#FF69B4' },
    { x: b.x, y: b.y + 2, w: 1, h: 1, fill: '#FF69B4' },
    { x: b.x + 3, y: b.y + 2, w: 1, h: 1, fill: '#FF69B4' },
    { x: b.x + 2, y: b.y + 2, w: 1, h: 1, fill: '#111' },
    { x: b.x + 1, y: b.y, w: 1, h: 1, fill: '#fff' },
  ];
}

function eyeStar(b: RectData, bg?: string): RectData[] {
  return [
    { x: b.x, y: b.y, w: b.w, h: b.h, fill: bg || '#fff' },
    { x: b.x + 1, y: b.y + 1, w: 2, h: 2, fill: '#FFD700' },
    { x: b.x, y: b.y + 1, w: 1, h: 1, fill: '#FFD700' },
    { x: b.x + 3, y: b.y + 1, w: 1, h: 1, fill: '#FFD700' },
    { x: b.x + 2, y: b.y, w: 1, h: 1, fill: '#FFD700' },
    { x: b.x + 1, y: b.y + 2, w: 1, h: 1, fill: '#FFD700' },
    { x: b.x + 2, y: b.y + 1, w: 1, h: 1, fill: '#000' },
    { x: b.x + 1, y: b.y, w: 1, h: 1, fill: '#fff' },
  ];
}

const EYE_MAP: Record<string, (b: RectData, bg?: string) => RectData[]> = {
  dot: eyeDot, sparkle: eyeSparkle, big: eyeBig, round: eyeRound, heart: eyeHeart, star: eyeStar,
};

// ═══════════════ EAR OVERLAYS ═══════════════
function earCat(b: string, d: string): RectData[] {
  return [
    { x: 6, y: 2, w: 3, h: 3, fill: b }, { x: 7, y: 1, w: 2, h: 1, fill: b },
    { x: 23, y: 2, w: 3, h: 3, fill: b }, { x: 23, y: 1, w: 2, h: 1, fill: b },
    { x: 7, y: 2, w: 1, h: 2, fill: d }, { x: 24, y: 2, w: 1, h: 2, fill: d },
  ];
}

function earRabbit(b: string, _d: string, l: string): RectData[] {
  return [
    { x: 7, y: 0, w: 2, h: 4, fill: b }, { x: 8, y: 0, w: 1, h: 4, fill: l },
    { x: 23, y: 0, w: 2, h: 4, fill: b }, { x: 23, y: 0, w: 1, h: 4, fill: l },
    { x: 8, y: 3, w: 1, h: 1, fill: _d }, { x: 23, y: 3, w: 1, h: 1, fill: _d },
  ];
}

function earMix(b: string, d: string, l: string): RectData[] {
  return [
    { x: 6, y: 2, w: 3, h: 3, fill: b }, { x: 7, y: 1, w: 2, h: 1, fill: b }, { x: 7, y: 2, w: 1, h: 2, fill: d },
    { x: 23, y: 0, w: 2, h: 4, fill: b }, { x: 23, y: 0, w: 1, h: 4, fill: l }, { x: 23, y: 3, w: 1, h: 1, fill: d },
  ];
}

// ═══════════════ HAT OVERLAYS ═══════════════
function hatCrown(): RectData[] {
  return [
    { x: 9, y: 0, w: 14, h: 2, fill: "#FFD700" }, { x: 10, y: -1, w: 12, h: 1, fill: "#FFD700" },
    { x: 10, y: -4, w: 3, h: 4, fill: "#FFD700" }, { x: 13, y: -5, w: 6, h: 5, fill: "#FFD700" }, { x: 19, y: -4, w: 3, h: 4, fill: "#FFD700" },
    { x: 11, y: -4, w: 1, h: 1, fill: "#FF4444" }, { x: 15, y: -5, w: 2, h: 1, fill: "#FF4444" }, { x: 19, y: -4, w: 1, h: 1, fill: "#FF4444" },
    { x: 11, y: 0, w: 1, h: 2, fill: "#FFA500" }, { x: 19, y: 0, w: 1, h: 2, fill: "#FFA500" },
  ];
}

function hatTophat(): RectData[] {
  return [
    { x: 7, y: -2, w: 18, h: 2, fill: "#111" }, { x: 8, y: -1, w: 16, h: 1, fill: "#222" },
    { x: 10, y: -8, w: 12, h: 6, fill: "#111" }, { x: 11, y: -8, w: 10, h: 3, fill: "#2a2a2a" },
    { x: 10, y: -3, w: 12, h: 1, fill: "#cc4444" }, { x: 12, y: -8, w: 8, h: 1, fill: "#3a3a3a" },
  ];
}

function hatPropeller(): RectData[] {
  return [
    { x: 10, y: -9, w: 10, h: 1, fill: "#e8e8e8" }, { x: 8, y: -8, w: 14, h: 1, fill: "#ddd" }, { x: 10, y: -7, w: 10, h: 1, fill: "#d0d0d0" },
    { x: 14, y: -9, w: 2, h: 3, fill: "#ff9f43" }, { x: 15, y: -8, w: 1, h: 1, fill: "#ff4444" },
    { x: 15, y: -6, w: 1, h: 3, fill: "#999" },
    { x: 12, y: -3, w: 6, h: 2, fill: "#ff9f43" }, { x: 11, y: -2, w: 8, h: 1, fill: "#ee8833" },
    { x: 10, y: -1, w: 10, h: 2, fill: "#dd7722" }, { x: 11, y: 0, w: 8, h: 1, fill: "#cc6611" },
  ];
}

function hatHalo(): RectData[] {
  return [
    { x: 9, y: -7, w: 12, h: 1, fill: "#FFD700" },
    { x: 8, y: -6, w: 1, h: 1, fill: "#FFD700" }, { x: 21, y: -6, w: 1, h: 1, fill: "#FFD700" },
    { x: 7, y: -5, w: 1, h: 2, fill: "#FFD700" }, { x: 22, y: -5, w: 1, h: 2, fill: "#FFD700" },
    { x: 8, y: -3, w: 1, h: 1, fill: "#FFD700" }, { x: 21, y: -3, w: 1, h: 1, fill: "#FFD700" },
    { x: 9, y: -2, w: 12, h: 1, fill: "#FFD700" },
    { x: 15, y: -8, w: 1, h: 1, fill: "#FFF8A0" }, { x: 15, y: -9, w: 1, h: 1, fill: "#FFF8A0" },
  ];
}

function hatWizard(): RectData[] {
  return [
    { x: 7, y: -2, w: 18, h: 2, fill: "#2a2a6a" }, { x: 8, y: -1, w: 16, h: 1, fill: "#3a3a8a" },
    { x: 11, y: -10, w: 10, h: 8, fill: "#2a2a6a" }, { x: 12, y: -10, w: 8, h: 4, fill: "#3a3a8a" },
    { x: 14, y: -12, w: 4, h: 2, fill: "#2a2a6a" }, { x: 15, y: -13, w: 2, h: 1, fill: "#3a3a8a" },
    { x: 11, y: -3, w: 10, h: 1, fill: "#FFD700" },
    { x: 13, y: -7, w: 1, h: 1, fill: "#FFD700" }, { x: 18, y: -8, w: 1, h: 1, fill: "#FFD700" }, { x: 14, y: -5, w: 1, h: 1, fill: "#FFD700" },
  ];
}

function hatBeanie(): RectData[] {
  return [
    { x: 9, y: -4, w: 14, h: 5, fill: "#cc4444" }, { x: 10, y: -5, w: 12, h: 1, fill: "#cc4444" },
    { x: 9, y: -3, w: 14, h: 1, fill: "#eee" }, { x: 9, y: -1, w: 14, h: 1, fill: "#eee" },
    { x: 8, y: 1, w: 16, h: 2, fill: "#aa3333" }, { x: 9, y: 0, w: 14, h: 1, fill: "#cc4444" },
    { x: 13, y: -6, w: 2, h: 2, fill: "#eee" }, { x: 14, y: -5, w: 2, h: 1, fill: "#eee" },
    { x: 14, y: -7, w: 2, h: 1, fill: "#eee" }, { x: 15, y: -6, w: 1, h: 1, fill: "#eee" },
  ];
}

function hatTinyduck(): RectData[] {
  return [
    { x: 13, y: -2, w: 6, h: 4, fill: "#FFD700" }, { x: 12, y: -4, w: 4, h: 3, fill: "#FFD700" },
    { x: 13, y: -5, w: 2, h: 1, fill: "#FFD700" }, { x: 15, y: -3, w: 3, h: 1, fill: "#FF8C00" },
    { x: 16, y: -2, w: 2, h: 1, fill: "#FF8C00" }, { x: 13, y: -4, w: 1, h: 1, fill: "#000" },
    { x: 17, y: -1, w: 1, h: 2, fill: "#eec800" }, { x: 14, y: 2, w: 2, h: 1, fill: "#FF8C00" }, { x: 17, y: 2, w: 2, h: 1, fill: "#FF8C00" },
  ];
}

const HAT_MAP: Record<string, () => RectData[]> = {
  none: () => [],
  crown: hatCrown,
  tophat: hatTophat,
  propeller: hatPropeller,
  halo: hatHalo,
  wizard: hatWizard,
  beanie: hatBeanie,
  tinyduck: hatTinyduck,
};

// ═══════════════ RENDER ═══════════════
function makeRect(r: RectData): string {
  return `<rect x="${r.x}" y="${r.y}" width="${r.w}" height="${r.h}" fill="${r.fill}"/>`;
}

export interface AvatarConfig {
  breed: BreedId | string;
  eye: EyeType | string;
  ear: EarType | string;
  hat: HatType | string;
  palette: PaletteType | string;
  shiny?: boolean;
}

export function buildAvatarSVG(config: AvatarConfig): string {
  const { breed, eye: eyeType, ear: earType, hat: hatName, palette: palKey, shiny } = config;
  const breedKey = breed in V3 ? breed : 'orange_tabby';
  const data = V3[breedKey];
  if (!data) return '';

  const rects = data.rects;
  const [es, ee] = data.earIdx;
  const [is, ie] = data.eyeIdx;

  // palette
  let bC = data.colors.B;
  let dC = data.colors.D;
  if (palKey !== 'default' && PAL[palKey]) {
    const p = PAL[palKey]();
    if (p) { bC = p.B; dC = p.D; }
  }

  // Build SVG parts
  let svgParts: string[] = [];

  // Render body (skip ear + eye ranges)
  for (let i = 0; i < rects.length; i++) {
    if (i >= es && i <= ee) continue;
    if (i >= is && i <= ie) continue;
    const r = rects[i];
    let f = r.fill;
    if (f === data.colors.B) f = bC;
    else if (f === data.colors.D) f = dC;
    svgParts.push(makeRect({ x: r.x, y: r.y, w: r.w, h: r.h, fill: f }));
  }

  // Ear overlay
  const earFn = earType === 'rabbit' ? earRabbit : earType === 'mix' ? earMix : earCat;
  const earRects = earFn(bC, dC, bC);
  earRects.forEach(r => svgParts.push(makeRect(r)));

  // Eye overlay
  const leftBox = rects[is];
  const rightBox = rects[is + 1] || { x: leftBox.x + 10, y: leftBox.y, w: leftBox.w, h: leftBox.h, fill: leftBox.fill };
  const eyeBG = leftBox.fill;
  const eyeFn = EYE_MAP[eyeType] || eyeDot;
  [leftBox, rightBox].forEach(box => {
    eyeFn(box, eyeBG).forEach(r => svgParts.push(makeRect(r)));
  });

  // Hat
  const hatFn = HAT_MAP[hatName] || HAT_MAP.none;
  hatFn().forEach(r => svgParts.push(makeRect(r)));

  // Shiny particles
  if (shiny) {
    const particles = [
      { x: -1, y: 3 }, { x: 31, y: 5 }, { x: -1, y: 12 },
      { x: 31, y: 16 }, { x: 1, y: 22 }, { x: 30, y: 25 }
    ];
    particles.forEach(p => {
      svgParts.push(`<rect x="${p.x}" y="${p.y}" width="1" height="1" fill="#FFD700" opacity="0.7"/>`);
    });
  }

  return `<svg width="240" height="272" viewBox="0 -14 32 46" shape-rendering="crispEdges" xmlns="http://www.w3.org/2000/svg">${svgParts.join('')}</svg>`;
}

// 基于 bones 数据生成头像配置
export function bonesToAvatarConfig(bones: Record<string, unknown> | null): AvatarConfig {
  if (!bones) {
    return { breed: 'orange_tabby', eye: 'dot', ear: 'cat', hat: 'none', palette: 'default', shiny: false };
  }
  return {
    breed: (bones.breed as string) || 'orange_tabby',
    eye: (bones.eye as EyeType) || 'dot',
    ear: (bones.ear as EarType) || 'cat',
    hat: (bones.hat as HatType) || 'none',
    palette: (bones.color as PaletteType) || 'default',
    shiny: (bones.shiny as boolean) || false,
  };
}
