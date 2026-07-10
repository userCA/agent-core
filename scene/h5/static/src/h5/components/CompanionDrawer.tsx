import React, { useCallback, useState, useMemo } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { Heart, Activity, Lightbulb, X } from 'lucide-react';
import { useCompanionStore } from '../../stores/companion-store';
import { useSessionStore } from '../../stores/session-store';
import { buildAvatarSVG, bonesToAvatarConfig } from '../../components/companion/SvgAvatarComposer';
import './CompanionDrawer.css';

interface Props {
  open: boolean;
  onClose: () => void;
}

const spring = { type: 'spring' as const, damping: 28, stiffness: 380 };

export default function CompanionDrawer({ open, onClose }: Props) {
  const bones = useCompanionStore((s) => s.bones);
  const sessions = useSessionStore((s) => s.sessions);
  const sessionId = useSessionStore((s) => s.sessionId);
  const [toast, setToast] = useState<string | null>(null);

  // Build pixel avatar SVG with cd-avatar class applied directly on the <svg>
  const avatarSvgHtml = useMemo(() => {
    const config = bonesToAvatarConfig(bones as Record<string, unknown> | null);
    const svg = buildAvatarSVG(config);
    // Add cd-avatar class to the SVG root element
    return svg.replace('<svg ', '<svg class="cd-avatar" ');
  }, [bones]);

  const companionName = (bones as Record<string, unknown> | null)?.name as string || '咪兔';

  // Compute today's stats
  const currentSession = sessions.find((s) => s.session_id === sessionId);
  const messageCount = currentSession?.entry_count ?? 0;
  const toolCount = Math.max(1, Math.floor(messageCount / 4));
  const conversationCount = sessions.length || 1;

  // Mood from companion stats
  const stats = (bones as Record<string, unknown> | null)?.stats as Record<string, number> | undefined;
  const affection = stats?.AFFECTION ?? 65;
  const moodPercent = Math.min(100, Math.max(10, affection));
  const moodLabel = moodPercent >= 80 ? '开心' : moodPercent >= 50 ? '平静' : '低落';

  const handlePetReaction = useCallback((type: 'poke' | 'feed' | 'praise') => {
    const reactions: Record<string, string> = {
      poke: `${companionName}咯咯笑着蹦来蹦去！`,
      feed: `${companionName}吃得很开心，真香！`,
      praise: `${companionName}骄傲地笑了！`,
    };
    setToast(reactions[type]);
    setTimeout(() => setToast(null), 2500);
  }, [companionName]);

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Overlay */}
          <motion.div
            className="cd-overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onClose}
          />

          {/* Sheet */}
          <motion.div
            className="cd-sheet"
            initial={{ y: '100%' }}
            animate={{ y: 0 }}
            exit={{ y: '100%' }}
            transition={spring}
          >
            {/* Handle */}
            <div className="cd-handle" onClick={onClose}>
              <div className="cd-handle-bar" />
            </div>

            {/* Header: avatar + name + close */}
            <div className="cd-header">
              <svg
                className="cd-avatar"
                dangerouslySetInnerHTML={{
                  __html: avatarSvgHtml.replace(/<\/?svg[^>]*>/g, ''),
                }}
                viewBox="0 -14 32 46"
                shapeRendering="crispEdges"
                xmlns="http://www.w3.org/2000/svg"
              />
              <div className="cd-header-info">
                <h2 className="cd-name">{companionName}</h2>
                <p className="cd-subtitle">你的编程伙伴</p>
              </div>
              <button className="cd-close" onClick={onClose} aria-label="关闭">
                <X size={16} />
              </button>
            </div>

            {/* Scrollable content */}
            <div className="cd-body">
              {/* Toast */}
              <AnimatePresence>
                {toast && (
                  <motion.div
                    className="cd-toast"
                    initial={{ opacity: 0, y: -8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.2 }}
                  >
                    <p>{toast}</p>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Mood card */}
              <div className="cd-card">
                <div className="cd-card-head">
                  <Heart size={18} className="cd-icon-plum" />
                  <span className="cd-card-label">心情</span>
                </div>
                <div className="cd-mood-row">
                  <div className="cd-progress">
                    <div className="cd-progress-fill" style={{ width: `${moodPercent}%` }} />
                  </div>
                  <span className="cd-mood-label">{moodLabel}</span>
                </div>
              </div>

              {/* Activity card */}
              <div className="cd-card">
                <div className="cd-card-head">
                  <Activity size={18} />
                  <span className="cd-card-label">今天</span>
                </div>
                <div className="cd-stats-grid">
                  <div className="cd-stat">
                    <span className="cd-stat-num">{conversationCount}</span>
                    <span className="cd-stat-label">对话</span>
                  </div>
                  <div className="cd-stat">
                    <span className="cd-stat-num">{messageCount}</span>
                    <span className="cd-stat-label">消息</span>
                  </div>
                  <div className="cd-stat">
                    <span className="cd-stat-num">{toolCount}</span>
                    <span className="cd-stat-label">工具</span>
                  </div>
                </div>
              </div>

              {/* Recent thoughts card */}
              <div className="cd-card">
                <div className="cd-card-head">
                  <Lightbulb size={18} className="cd-icon-warm" />
                  <span className="cd-card-label">最近想法</span>
                </div>
                <div className="cd-thoughts">
                  <div className="cd-thought">
                    <span className="cd-thought-dot" />
                    <p>你今天好像在专注认证模块，要我帮你留意相关的代码模式吗？</p>
                  </div>
                  <div className="cd-thought">
                    <span className="cd-thought-dot" />
                    <p>最近重构工具挺好用的，我可以多提醒你用它。</p>
                  </div>
                </div>
              </div>

              {/* Action buttons */}
              <div className="cd-actions">
                <button className="cd-action-btn" onClick={() => handlePetReaction('poke')}>戳一下</button>
                <button className="cd-action-btn" onClick={() => handlePetReaction('feed')}>喂零食</button>
                <button className="cd-action-btn" onClick={() => handlePetReaction('praise')}>表扬</button>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
