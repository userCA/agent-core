import React, { useState, useEffect } from 'react';
import { useChannelStore } from '../../stores/channel-store';
import { useUIStore } from '../../stores/ui-store';
import { useConfirmStore } from '../../stores/confirm-store';
import type { ChannelInfo } from '../../api/client';
import Icon from '../shared/Icon';
import Loading from '../shared/Loading';
import { SkeletonList } from '../shared/Skeleton';
import EmptyState from '../shared/EmptyState';
import CollapsibleSection from '../shared/CollapsibleSection';
import './Pages.css';

const emptyChannel = (): ChannelInfo => ({
  id: '', name: '', type: 'feishu', enabled: true,
  app_id: '', app_secret: '',
});

interface Props { onBack?: () => void; }

export default function ChannelsPage({ onBack }: Props) {
  const { channels, loading, loadError, load, save, remove } = useChannelStore();
  const setActivePage = useUIStore((s) => s.setActivePage);
  const back = onBack ?? (() => setActivePage('chat'));
  const requestConfirm = useConfirmStore((s) => s.requestConfirm);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<ChannelInfo>(emptyChannel());
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState('');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [openDropdown, setOpenDropdown] = useState<string | null>(null);
  const toggleDropdown = (name: string) => setOpenDropdown(prev => prev === name ? null : name);

  useEffect(() => { load(); }, [load]);

  // Esc to close form, dropdown
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      if (openDropdown) { setOpenDropdown(null); return; }
      if (showForm && !submitting) { setShowForm(false); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [showForm, submitting, openDropdown]);

  const startNew = () => {
    setForm(emptyChannel()); setEditingId(null); setShowForm(true);
    setFormError(''); setFieldErrors({});
  };

  const startEdit = (ch: ChannelInfo) => {
    setForm({ ...ch }); setEditingId(ch.id); setShowForm(true);
    setFormError(''); setFieldErrors({});
  };

  const validate = (): boolean => {
    const errs: Record<string, string> = {};
    if (!form.id.trim()) errs.id = '标识不能为空';
    else if (!/^[a-zA-Z0-9_-]+$/.test(form.id)) errs.id = '只允许英文、数字、下划线、横线';
    if (!form.name.trim()) errs.name = '名称不能为空';
    if (form.type === 'feishu' && !form.app_id.trim()) errs.app_id = 'App ID 不能为空';
    setFieldErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSubmit = async () => {
    if (!validate()) return;
    setSubmitting(true); setFormError('');
    try { await save(form); setShowForm(false); setForm(emptyChannel()); }
    catch (err: unknown) { setFormError(err instanceof Error ? err.message : '保存失败'); }
    finally { setSubmitting(false); }
  };

  const handleDelete = (id: string) => {
    requestConfirm({
      title: '删除渠道',
      message: `确定删除渠道 "${id}"？此操作不可恢复。`,
      confirmText: '删除', danger: true,
      onConfirm: async () => { setSubmitting(true); try { await remove(id); } finally { setSubmitting(false); } },
    });
  };

  return (
    <div className="page">
      <div className="page-header">
        <button className="page-back" onClick={back} aria-label="返回聊天">
          <Icon name="chevron-left" size={18} />
        </button>
        <h1 className="page-title">渠道管理</h1>
        <div className="page-header-right">
          <button className="btn" onClick={startNew} disabled={submitting}>
            <Icon name="plus" size={14} /> 添加
          </button>
        </div>
      </div>

      <div className="page-body">
        {loading && <SkeletonList count={3} />}

        {loadError && (
          <div className="page-empty">
            <p className="page-error">{loadError}</p>
            <button className="btn" onClick={load} style={{ marginTop: 12 }}>
              <Icon name="spinner" size={12} /> 重试
            </button>
          </div>
        )}

        {!loading && !loadError && channels.length === 0 && !showForm && (
          <EmptyState icon="send" title="暂无渠道" description="点击「添加」配置消息渠道，支持飞书、微信等" />
        )}

        {!loading && channels.length > 0 && (
          <p className="page-section-title">已配置 {channels.length} 个渠道</p>
        )}

        <div className="connector-list">
          {channels.map((ch) => {
            const isExpanded = expanded.has(ch.id);
            return (
              <div key={ch.id} className={`connector-item${ch.enabled ? ' ok' : ''}`}>
                <CollapsibleSection
                  open={isExpanded}
                  onOpenChange={(open) => setExpanded(open ? new Set([ch.id]) : new Set())}
                  trigger={
                    <button className="connector-item-header" type="button">
                      <div className="connector-item-head">
                        <span className={`dot${ch.enabled ? ' green' : ''}`} />
                        <span className="connector-item-name">{ch.name}</span>
                        <span className="connector-item-badge type-kb">{ch.type}</span>
                      </div>
                      <div className="connector-item-meta">
                        <span>{ch.app_id?.slice(0, 20) || '未配置'}</span>
                        <span className="connector-item-arrow">
                          {isExpanded ? <Icon name="chevron-up" size={12} /> : <Icon name="chevron-down" size={12} />}
                        </span>
                      </div>
                    </button>
                  }
                  contentClassName="connector-item-tools"
                >
                  <span className="connector-tool-badge">App ID: {ch.app_id || '-'}</span>
                  <span className="connector-tool-badge">Secret: ****</span>
                  <div className="connector-item-tool-actions" style={{ display: 'flex', gap: 8 }}>
                    <button className="btn" onClick={() => startEdit(ch)} disabled={submitting}>编辑</button>
                    <button className="btn btn-danger" onClick={() => handleDelete(ch.id)} disabled={submitting}>删除</button>
                  </div>
                </CollapsibleSection>
              </div>
            );
          })}
        </div>

        {showForm && (
          <div className="card form-card">
            <div className="card-form-head">
              <span className="card-title">{editingId ? `编辑: ${editingId}` : '新增渠道'}</span>
            </div>
            <div className="form-grid">
              <div className="form-field">
                <label htmlFor="channel-id">标识 *</label>
                <input id="channel-id" value={form.id} onChange={e => setForm({ ...form, id: e.target.value })}
                  className={fieldErrors.id ? 'field-invalid' : ''}
                  placeholder="英文标识，如 feishu-vip" disabled={!!editingId || submitting}
                  aria-invalid={!!fieldErrors.id}
                  aria-describedby={fieldErrors.id ? 'channel-id-error' : undefined} />
                {fieldErrors.id && <span id="channel-id-error" className="field-error">{fieldErrors.id}</span>}
              </div>
              <div className="form-field">
                <label htmlFor="channel-name">名称 *</label>
                <input id="channel-name" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
                  className={fieldErrors.name ? 'field-invalid' : ''}
                  placeholder="显示名称，如 飞书 VIP" disabled={submitting}
                  aria-invalid={!!fieldErrors.name}
                  aria-describedby={fieldErrors.name ? 'channel-name-error' : undefined} />
                {fieldErrors.name && <span id="channel-name-error" className="field-error">{fieldErrors.name}</span>}
              </div>
              <div className="form-field">
                <span id="channel-type-label">类型</span>
                <div className="form-dropdown">
                  <button className="form-select" onClick={() => toggleDropdown('type')} type="button" disabled={submitting}
                    aria-labelledby="channel-type-label"
                    aria-haspopup="listbox"
                    aria-expanded={openDropdown === 'type'}>
                    {form.type === 'wechat' ? '微信 (即将支持)' : '飞书 (Lark)'}
                  </button>
                  {openDropdown === 'type' && (
                    <>
                      <div className="more-backdrop" onClick={() => setOpenDropdown(null)} />
                      <div className="form-dropdown-menu">
                        <button className={`form-dropdown-item${form.type === 'feishu' ? ' selected' : ''}`}
                          onClick={() => { setForm({ ...form, type: 'feishu' }); setOpenDropdown(null); }}>
                          飞书 (Lark)
                        </button>
                        <button className={`form-dropdown-item${form.type === 'wechat' ? ' selected' : ''}`}
                          onClick={() => { setForm({ ...form, type: 'wechat' }); setOpenDropdown(null); }}>
                          微信 (即将支持)
                        </button>
                      </div>
                    </>
                  )}
                </div>
              </div>
              <div className="form-field">
                <label htmlFor="channel-app-id">App ID</label>
                <input id="channel-app-id" value={form.app_id} onChange={e => setForm({ ...form, app_id: e.target.value })}
                  className={fieldErrors.app_id ? 'field-invalid' : ''}
                  placeholder="cli_xxxxxxxx" disabled={submitting}
                  aria-invalid={!!fieldErrors.app_id}
                  aria-describedby={fieldErrors.app_id ? 'channel-app-id-error' : undefined} />
                {fieldErrors.app_id && <span id="channel-app-id-error" className="field-error">{fieldErrors.app_id}</span>}
              </div>
              <div className="form-field">
                <label htmlFor="channel-app-secret">App Secret</label>
                <input id="channel-app-secret" type="password" value={form.app_secret} onChange={e => setForm({ ...form, app_secret: e.target.value })}
                  placeholder={editingId ? '留空表示不修改' : '输入密钥'} disabled={submitting} />
              </div>
            </div>
            {formError && <p className="card-form-error">{formError}</p>}
            <div className="card-form-actions">
              <button className="btn btn-primary" onClick={handleSubmit}
                disabled={submitting || !form.id.trim() || !form.name.trim()}>
                {submitting ? '保存中...' : '保存'}
              </button>
              <button className="btn" onClick={() => setShowForm(false)} disabled={submitting}>取消</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
