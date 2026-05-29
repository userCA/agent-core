import React, { useState, useMemo } from 'react';
import { useSessionStore } from '../../stores/session-store';
import { useUIStore } from '../../stores/ui-store';
import { savePersona, deletePersona, type PersonaInfo } from '../../api/client';
import Icon from '../shared/Icon';
import './Pages.css';

function emptyPersona(): PersonaInfo {
  return { id: '', name: '', description: '', system_prompt: '', enabled_tools: null };
}

const KNOWN_TOOLS = ['read', 'write', 'edit', 'bash', 'ls', 'find', 'grep', 'confirm'];

export default function ExpertsPage() {
  const personas = useSessionStore((s) => s.personas);
  const loadPersonas = useSessionStore((s) => s.loadPersonas);
  const personaId = useSessionStore((s) => s.personaId);
  const setPersonaId = useSessionStore((s) => s.setPersonaId);
  const setActivePage = useUIStore((s) => s.setActivePage);
  const [search, setSearch] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<PersonaInfo>(emptyPersona());
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState('');
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  React.useEffect(() => { loadPersonas(); }, [loadPersonas]);

  const filtered = useMemo(() => {
    if (!search.trim()) return personas;
    const q = search.toLowerCase();
    return personas.filter((p) =>
      p.name.toLowerCase().includes(q) || p.description.toLowerCase().includes(q)
    );
  }, [personas, search]);

  const activePersona = personas.find((p) => p.id === personaId);

  const toggleExpand = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const startNew = () => {
    setForm(emptyPersona());
    setEditingId(null);
    setFormError('');
    setShowForm(true);
  };

  const startEdit = (p: PersonaInfo) => {
    setForm({ ...p, system_prompt: p.system_prompt || '', enabled_tools: p.enabled_tools || null });
    setEditingId(p.id);
    setFormError('');
    setShowForm(true);
  };

  const toolList: string[] = form.enabled_tools || [];

  const toggleFormTool = (t: string) => {
    if (toolList.includes(t)) {
      setForm({ ...form, enabled_tools: toolList.filter((x: string) => x !== t) });
    } else {
      setForm({ ...form, enabled_tools: [...toolList, t] });
    }
  };

  const handleSubmit = async () => {
    const f = form;
    if (!f.id.trim()) { setFormError('ID 不能为空'); return; }
    if (!f.name.trim()) { setFormError('名称不能为空'); return; }

    setSubmitting(true);
    setFormError('');
    try {
      await savePersona({
        id: f.id.trim(),
        name: f.name.trim(),
        description: f.description?.trim() || '',
        system_prompt: f.system_prompt?.trim() || '',
        enabled_tools: toolList.length > 0 ? toolList : undefined,
      });
      await loadPersonas();
      setShowForm(false);
      setEditingId(null);
    } catch (err: unknown) {
      setFormError(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!window.confirm(`确定要删除专家 "${id}" 吗？`)) return;
    try {
      await deletePersona(id);
      if (personaId === id) setPersonaId(null);
      await loadPersonas();
    } catch {
      // ignore
    }
  };

  return (
    <div className="page">
      <div className="page-header">
        <button className="page-back" onClick={() => setActivePage('chat')} aria-label="返回聊天">
          <Icon name="chevron-up" size={18} style={{ transform: 'rotate(-90deg)' }} />
        </button>
        <h1 className="page-title">专家管理</h1>
        <div className="page-header-right">
          <div className="page-search">
            <Icon name="search" size={14} />
            <input
              type="text"
              placeholder="搜索专家..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              aria-label="搜索专家"
            />
          </div>
          <button className="btn" onClick={startNew}>
            <Icon name="plus" size={14} /> 添加
          </button>
        </div>
      </div>

      <div className="page-body">
        {/* Active expert card */}
        {activePersona && (
          <div className="expert-active-card">
            <div className="expert-active-head">
              <span className="expert-active-head-text">
                <span className="expert-bracket">[*]</span> {activePersona.name}
              </span>
              <span className="expert-active-desc">{activePersona.description}</span>
            </div>
            {activePersona.system_prompt && (
              <div className="expert-active-prompt">
                <span className="expert-active-label">System Prompt</span>
                <p>{activePersona.system_prompt.slice(0, 120)}{activePersona.system_prompt.length > 120 ? '...' : ''}</p>
              </div>
            )}
            {activePersona.enabled_tools && activePersona.enabled_tools.length > 0 && (
              <div className="expert-active-tools">
                {activePersona.enabled_tools.map((t: string) => (
                  <span key={t} className="tag">{t}</span>
                ))}
              </div>
            )}
          </div>
        )}

        {personas.length === 0 && !showForm && (
          <p className="page-empty">暂无专家。点击"添加"创建第一个。</p>
        )}

        {personas.length > 0 && search && filtered.length === 0 && (
          <p className="page-empty">无匹配专家</p>
        )}

        {showForm && (
          <div className="card form-card">
            <div className="card-form-head">
              <span className="card-title">{editingId ? `编辑: ${editingId}` : '添加专家'}</span>
            </div>
            <div className="form-grid">
              <label className="form-field">
                <span>ID (英文标识)</span>
                <input type="text" value={form.id} disabled={!!editingId}
                  placeholder="例如 coder"
                  onChange={(e) => setForm({ ...form, id: e.target.value })} />
              </label>
              <label className="form-field">
                <span>名称</span>
                <input type="text" value={form.name} placeholder="例如 代码专家"
                  onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </label>
              <label className="form-field">
                <span>描述</span>
                <input type="text" value={form.description || ''} placeholder="简短描述专家的用途"
                  onChange={(e) => setForm({ ...form, description: e.target.value })} />
              </label>
              <label className="form-field">
                <span>System Prompt</span>
                <textarea value={form.system_prompt || ''} rows={3}
                  placeholder="定义专家的行为和知识范围..."
                  onChange={(e) => setForm({ ...form, system_prompt: e.target.value })} />
              </label>
              <div className="form-field">
                <span>启用的工具</span>
                <div className="tool-toggle-grid">
                  {KNOWN_TOOLS.map((t: string) => {
                    const on = toolList.includes(t);
                    return (
                      <button
                        key={t}
                        className={`tool-toggle${on ? ' on' : ''}`}
                        onClick={() => toggleFormTool(t)}
                        type="button"
                      >
                        {on && <Icon name="check" size={11} />}
                        {t}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
            {formError && <p className="card-form-error">{formError}</p>}
            <div className="card-form-actions">
              <button className="btn btn-primary" onClick={handleSubmit} disabled={submitting}>
                {submitting ? '保存中...' : '保存'}
              </button>
              <button className="btn" onClick={() => setShowForm(false)}>取消</button>
            </div>
          </div>
        )}

        <div className="expert-list">
          {filtered.map((p) => {
            const isActive = p.id === personaId;
            const isExpanded = expanded.has(p.id);
            const toolCount = p.enabled_tools?.length || 0;
            return (
              <div key={p.id} className="expert-item">
                <div className="expert-item-header">
                  <button className="expert-item-toggle" onClick={() => toggleExpand(p.id)} aria-expanded={isExpanded}>
                    <span className="expert-bracket" onClick={(e) => { e.stopPropagation(); setPersonaId(isActive ? null : p.id); }} title={isActive ? '停用' : '激活'}>
                      [{isActive ? '*' : ' '}]
                    </span>
                    <div className="expert-item-info">
                      <span className="expert-item-name">{p.name}</span>
                      <span className="expert-item-desc">{p.description}</span>
                    </div>
                    <div className="expert-item-right">
                      <span className="expert-item-meta">
                        {toolCount > 0 && <span>{toolCount} 工具</span>}
                      </span>
                      <span className="connector-item-arrow">
                        {isExpanded ? '[-]' : '[+]'}
                      </span>
                    </div>
                  </button>
                  <div className="expert-item-actions">
                    <button className="expert-action-link" onClick={() => startEdit(p)}>[/] 编辑</button>
                    <button className="expert-action-link expert-action-delete" onClick={() => handleDelete(p.id)}>[x] 删除</button>
                  </div>
                </div>
                {isExpanded && (
                  <div className="expert-item-detail">
                    {p.system_prompt && (
                      <div className="expert-detail-section">
                        <span className="expert-detail-label">System Prompt</span>
                        <pre className="expert-detail-prompt">{p.system_prompt}</pre>
                      </div>
                    )}
                    {p.enabled_tools && p.enabled_tools.length > 0 && (
                      <div className="expert-detail-tools">
                        {p.enabled_tools.map((t: string) => (
                          <span key={t} className="tag">{t}</span>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
