import React, { useMemo } from 'react';
import { motion } from 'motion/react';
import { useCompanionStore } from '../../stores/companion-store';
import { useUIStore } from '../../stores/ui-store';
import { buildAvatarSVG, bonesToAvatarConfig } from '../companion/SvgAvatarComposer';
import { BREED_LABELS } from '../companion/breed-sprites';
import Icon from '../shared/Icon';
import './Pages.css';
import './CompanionProfilePage.css';

interface Props {
  onBack?: () => void;
}

const RARITY_LABELS: Record<string, string> = {
  common: '普通',
  uncommon: '稀有',
  rare: '珍稀',
  epic: '史诗',
  legendary: '传说',
};

const RARITY_COLORS: Record<string, string> = {
  common: '#8e8e93',
  uncommon: '#30d158',
  rare: '#409cff',
  epic: '#bf5af2',
  legendary: '#ff9f0a',
};

const QUIRK_LABELS: Record<string, string> = {
  night_owl: '夜猫子',
  picky_eater: '挑食怪',
  chatterbox: '话痨',
  shy: '社恐',
  collector: '收集癖',
  hyperactive: '多动症',
  sleepyhead: '睡神',
  glass_heart: '玻璃心',
  foodie: '贪吃',
  clean_freak: '洁癖',
  tsundere_extreme: '究极傲娇',
  philosopher: '哲学家',
  comedian: '搞笑猫',
};

const BOND_LEVELS = [
  { threshold: 0, label: 'STRANGER', display: '陌生人', desc: '你们刚刚相遇' },
  { threshold: 10, label: 'ACQUAINTANCE', display: '相识', desc: '开始记住你的名字' },
  { threshold: 50, label: 'FRIEND', display: '朋友', desc: '经常一起玩耍' },
  { threshold: 200, label: 'CLOSE', display: '知己', desc: '彼此非常了解' },
  { threshold: 1000, label: 'SOULMATE', display: '灵魂伴侣', desc: '命中注定的羁绊' },
];

function getBondLevel(score: number): typeof BOND_LEVELS[number] {
  for (let i = BOND_LEVELS.length - 1; i >= 0; i--) {
    if (score >= BOND_LEVELS[i].threshold) return BOND_LEVELS[i];
  }
  return BOND_LEVELS[0];
}

function getBondProgress(score: number): number {
  const current = getBondLevel(score);
  const idx = BOND_LEVELS.indexOf(current);
  if (idx === BOND_LEVELS.length - 1) return 100;
  const next = BOND_LEVELS[idx + 1];
  const range = next.threshold - current.threshold;
  const progress = score - current.threshold;
  return Math.min(100, Math.max(0, (progress / range) * 100));
}

const demoBones = {
  uid: 'demo-uid',
  breed: 'orange_tabby',
  rarity: 'common',
  eye: 'dot',
  ear: 'cat',
  accent: 'none',
  hat: 'none',
  quirk: 'foodie',
  shiny: false,
  color: 'default',
  stats: { CURIOSITY: 45, SOCIAL: 35, AFFECTION: 68, PLAYFUL: 22, LUCK: 45 },
  name: '橘子',
  personality: '佛系吃货',
  hatched_at: Date.now() - 86400000 * 7,
};

export default function CompanionProfilePage({ onBack }: Props) {
  const bones = useCompanionStore((s) => s.bones);
  const setH5ActiveTab = useUIStore((s) => s.setH5ActiveTab);
  const back = onBack ?? (() => setH5ActiveTab('chat'));

  const data = bones || demoBones;
  const score = (data.stats?.AFFECTION ?? 50) * 5; // simulated bond score
  const bondLevel = getBondLevel(score);
  const bondProgress = getBondProgress(score);

  const svgString = useMemo(() => {
    const config = bonesToAvatarConfig(data as unknown as Record<string, unknown>);
    return buildAvatarSVG(config);
  }, [data]);

  const stats = data.stats || {};
  const statEntries = Object.entries(stats) as [string, number][];

  const rarityColor = RARITY_COLORS[data.rarity as string] || '#8e8e93';

  return (
    <div className="page">
      {!onBack && (
        <div className="page-header">
          <button className="page-back" onClick={back} aria-label="返回">
            <Icon name="chevron-left" size={18} />
          </button>
          <h1 className="page-title">宠物资料</h1>
        </div>
      )}

      <div className="page-body companion-profile-body">
        {/* Avatar Section */}
        <motion.div
          className="companion-avatar-section"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35 }}
        >
          <div className="companion-avatar-wrapper">
            <div
              className="companion-avatar-svg"
              role="img"
              aria-label={`${data.name || '宠物'} 头像`}
              dangerouslySetInnerHTML={{ __html: svgString }}
            />
            {data.shiny && (
              <span className="companion-shiny-badge">&#10022;</span>
            )}
          </div>
          <div className="companion-name-section">
            <h2 className="companion-name">
              {data.name || '未命名'}
              <span
                className="companion-rarity-tag"
                style={{ color: rarityColor, borderColor: rarityColor }}
              >
                {RARITY_LABELS[data.rarity as string] || '普通'}
              </span>
            </h2>
            <p className="companion-personality">
              {(data.personality as string) || '一只神秘的咪兔'}
            </p>
            <div className="companion-meta-row">
              <span className="companion-meta-item">
                <Icon name="cat" size={12} />
                {BREED_LABELS[data.breed as keyof typeof BREED_LABELS] || '未知品种'}
              </span>
              {data.hatched_at && (
                <span className="companion-meta-item">
                  <Icon name="calendar" size={12} />
                  {new Date(data.hatched_at).toLocaleDateString('zh-CN')}
                </span>
              )}
            </div>
          </div>
        </motion.div>

        {/* Bond Level */}
        <motion.div
          className="companion-card"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, delay: 0.08 }}
        >
          <h3 className="companion-card-title">
            <Icon name="heart" size={14} /> 亲密度
          </h3>
          <div className="companion-bond-info">
            <div className="companion-bond-level">
              <span className="companion-bond-label">{bondLevel.display}</span>
              <span className="companion-bond-score">{score} 分</span>
            </div>
            <div className="companion-bond-bar">
              <div
                className="companion-bond-fill"
                style={{ width: `${bondProgress}%` }}
              />
            </div>
            <p className="companion-bond-desc">{bondLevel.desc}</p>
          </div>
        </motion.div>

        {/* Stats */}
        <motion.div
          className="companion-card"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, delay: 0.16 }}
        >
          <h3 className="companion-card-title">
            <Icon name="bar-chart" size={14} /> 属性
          </h3>
          <div className="companion-stats-grid">
            {statEntries.map(([key, value]) => (
              <div key={key} className="companion-stat-item">
                <div className="companion-stat-header">
                  <span className="companion-stat-name">{key}</span>
                  <span className="companion-stat-value">{value}</span>
                </div>
                <div className="companion-stat-bar">
                  <motion.div
                    className="companion-stat-fill"
                    initial={{ width: 0 }}
                    animate={{ width: `${value}%` }}
                    transition={{ duration: 0.8, ease: 'easeOut', delay: 0.3 }}
                  />
                </div>
              </div>
            ))}
          </div>
        </motion.div>

        {/* Quirk */}
        {data.quirk && (
          <motion.div
            className="companion-card"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, delay: 0.24 }}
          >
            <h3 className="companion-card-title">
              <Icon name="sparkles" size={14} /> 怪癖
            </h3>
            <div className="companion-quirk">
              <span className="companion-quirk-tag">
                {QUIRK_LABELS[data.quirk as string] || data.quirk}
              </span>
            </div>
          </motion.div>
        )}

        {/* Appearance details */}
        <motion.div
          className="companion-card"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, delay: 0.32 }}
        >
          <h3 className="companion-card-title">
            <Icon name="eye" size={14} /> 外观
          </h3>
          <div className="companion-appearance-grid">
            <div className="companion-appearance-item">
              <span className="companion-appearance-label">眼睛</span>
              <span className="companion-appearance-value">{data.eye || '默认'}</span>
            </div>
            <div className="companion-appearance-item">
              <span className="companion-appearance-label">耳朵</span>
              <span className="companion-appearance-value">{data.ear || '默认'}</span>
            </div>
            <div className="companion-appearance-item">
              <span className="companion-appearance-label">配饰</span>
              <span className="companion-appearance-value">{data.hat && data.hat !== 'none' ? data.hat : '无'}</span>
            </div>
            <div className="companion-appearance-item">
              <span className="companion-appearance-label">闪亮</span>
              <span className="companion-appearance-value">{data.shiny ? '是' : '否'}</span>
            </div>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
