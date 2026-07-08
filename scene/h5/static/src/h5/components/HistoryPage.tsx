import React, { useEffect, useMemo, useState } from 'react';
import { motion, AnimatePresence, useReducedMotion } from 'motion/react';
import { useSessionStore, type SessionSummary } from '../../stores/session-store';
import { useUIStore } from '../../stores/ui-store';
import { useToastStore } from '../../stores/toast-store';
import { deleteSession } from '../../api/client';
import Icon from '../../components/shared/Icon';
import './HistoryPage.css';

interface Props {
  onBack: () => void;
}

function formatDateGroup(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const isToday = date.toDateString() === now.toDateString();
  if (isToday) return '今天';

  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  if (date.toDateString() === yesterday.toDateString()) return '昨天';

  const days = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
  const dayName = days[date.getDay()];
  const month = date.getMonth() + 1;
  const day = date.getDate();
  return `${month}月${day}日 · ${dayName}`;
}

function groupByDate(sessions: SessionSummary[]): Map<string, SessionSummary[]> {
  const groups = new Map<string, SessionSummary[]>();
  for (const s of sessions) {
    const key = formatDateGroup(s.created_at);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(s);
  }
  return groups;
}

const listVariants = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.06, delayChildren: 0.05 },
  },
};

const itemVariants = {
  hidden: { opacity: 0, x: -20, scale: 0.95 },
  show: {
    opacity: 1,
    x: 0,
    scale: 1,
    transition: { type: 'spring' as const, stiffness: 400, damping: 32 },
  },
};

const dateLabelVariants = {
  hidden: { opacity: 0, y: -8 },
  show: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.25, ease: 'easeOut' as const },
  },
};

export default function HistoryPage({ onBack }: Props) {
  const sessions = useSessionStore((s) => s.sessions);
  const sessionsLoading = useSessionStore((s) => s.sessionsLoading);
  const loadSessions = useSessionStore((s) => s.loadSessions);
  const removeSession = useSessionStore((s) => s.removeSession);
  const switchSession = useSessionStore((s) => s.switchSession);
  const currentSessionId = useSessionStore((s) => s.sessionId);
  const setH5ActiveTab = useUIStore((s) => s.setH5ActiveTab);
  const addToast = useToastStore((s) => s.addToast);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const reducedMotion = useReducedMotion();

  const pageTransition = reducedMotion
    ? { duration: 0 }
    : { type: 'spring' as const, stiffness: 400, damping: 32 };
  const emptyTransition = reducedMotion ? { duration: 0 } : { delay: 0.2 };
  const spinnerTransition = reducedMotion
    ? { duration: 0 }
    : { duration: 1, repeat: Infinity, ease: 'linear' as const };
  const tapScale = reducedMotion ? 1 : 0.97;
  const exitTransition = reducedMotion
    ? { duration: 0 }
    : { duration: 0.25, ease: 'easeInOut' as const };
  const listVars = reducedMotion ? { hidden: {}, show: {} } : listVariants;
  const itemVars = reducedMotion ? { hidden: {}, show: {} } : itemVariants;
  const dateVars = reducedMotion ? { hidden: {}, show: {} } : dateLabelVariants;

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  const filteredSessions = useMemo(() => {
    if (!searchQuery.trim()) return sessions;
    const q = searchQuery.trim().toLowerCase();
    return sessions.filter((s) => (s.title || '').toLowerCase().includes(q));
  }, [sessions, searchQuery]);

  const groups = useMemo(() => groupByDate(filteredSessions), [filteredSessions]);

  const handleSwitch = (id: string) => {
    switchSession(id);
    setH5ActiveTab('chat');
    addToast('已切换到历史会话', 'success');
  };

  const handleDelete = async (id: string) => {
    setDeletingId(id);
    try {
      await deleteSession(id);
      removeSession(id);
      addToast('已删除会话', 'success');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '删除失败';
      addToast(msg, 'error');
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <motion.div
      className="h5-history"
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 20 }}
      transition={pageTransition}
    >
      <div className="h5-history-body">
        <div className="h5-history-search">
          <Icon name="search" size={14} />
          <input
            type="text"
            placeholder="搜索会话..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            aria-label="搜索会话"
          />
          {searchQuery && (
            <button
              className="h5-history-search-clear"
              onClick={() => setSearchQuery('')}
              aria-label="清除搜索"
            >
              <Icon name="x" size={14} />
            </button>
          )}
        </div>

        {sessionsLoading && (
          <div className="h5-history-loading">
            <motion.div
              className="h5-history-spinner"
              animate={reducedMotion ? undefined : { rotate: 360 }}
              transition={spinnerTransition}
            >
              <Icon name="spinner" size={20} />
            </motion.div>
          </div>
        )}

        {!sessionsLoading && sessions.length === 0 && !searchQuery && (
          <motion.div
            className="h5-history-empty"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={emptyTransition}
          >
            <Icon name="message" size={32} aria-label="暂无消息" />
            <p>暂无历史记录</p>
          </motion.div>
        )}

        {!sessionsLoading && searchQuery && filteredSessions.length === 0 && (
          <motion.div
            className="h5-history-empty"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={emptyTransition}
          >
            <Icon name="search" size={32} aria-label="无搜索结果" />
            <p>未找到匹配的会话</p>
          </motion.div>
        )}

        <AnimatePresence mode="popLayout">
          {Array.from(groups.entries()).map(([dateLabel, items]) => (
            <motion.div
              key={dateLabel}
              className="h5-history-group"
              variants={listVars}
              initial="hidden"
              animate="show"
              exit={reducedMotion ? { opacity: 0 } : { opacity: 0, height: 0 }}
            >
              <motion.h3
                className="h5-history-date"
                variants={dateVars}
              >
                {dateLabel}
              </motion.h3>
              <div className="h5-history-list">
                {items.map((s) => {
                  const isActive = s.session_id === currentSessionId;
                  const isDeleting = deletingId === s.session_id;
                  return (
                    <motion.div
                      key={s.session_id}
                      className={`h5-history-item ${isActive ? 'h5-history-item--active' : ''}`}
                      variants={itemVars}
                      layout={!reducedMotion}
                      exit={{ opacity: 0, x: reducedMotion ? 0 : -40, scale: reducedMotion ? 1 : 0.9, transition: exitTransition }}
                      whileTap={{ scale: tapScale }}
                    >
                      <button
                        className="h5-history-item-main"
                        onClick={() => handleSwitch(s.session_id)}
                      >
                        <span className="h5-history-item-title">{s.title}</span>
                        <span className="h5-history-item-meta">{s.entry_count} 条消息</span>
                      </button>
                      <button
                        className="h5-history-item-delete"
                        onClick={() => handleDelete(s.session_id)}
                        disabled={isDeleting}
                        aria-label="删除会话"
                      >
                        <AnimatePresence mode="wait">
                          {isDeleting ? (
                            <motion.span
                              key="deleting"
                              initial={{ opacity: 0, scale: 0.5 }}
                              animate={{ opacity: 1, scale: 1 }}
                              exit={{ opacity: 0 }}
                            >
                              <Icon name="spinner" size={14} />
                            </motion.span>
                          ) : (
                            <motion.span
                              key="trash"
                              initial={{ opacity: 0, scale: 0.5 }}
                              animate={{ opacity: 1, scale: 1 }}
                              exit={{ opacity: 0 }}
                            >
                              <Icon name="trash" size={14} />
                            </motion.span>
                          )}
                        </AnimatePresence>
                      </button>
                    </motion.div>
                  );
                })}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}
