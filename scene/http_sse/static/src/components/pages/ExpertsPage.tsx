import React, { useState, useMemo } from 'react';
import { useSessionStore } from '../../stores/session-store';
import { useSkillStore } from '../../stores/skill-store';
import { useUIStore } from '../../stores/ui-store';
import { useToastStore } from '../../stores/toast-store';
import { useConfirmStore } from '../../stores/confirm-store';
import { savePersona, deletePersona, fetchConnectors, type PersonaInfo, type ConnectorInfo } from '../../api/client';
import Icon from '../shared/Icon';
import EmptyState from '../shared/EmptyState';
import Loading from '../shared/Loading';
import './Pages.css';

function emptyPersona(): PersonaInfo {
  return { id: '', name: '', description: '', system_prompt: '', enabled_tools: null, knowledge_bases: null };
}

export default function ExpertsPage() {
  const personas = useSessionStore((s) => s.personas);
  const personasLoading = useSessionStore((s) => s.personasLoading);
  const loadPersonas = useSessionStore((s) => s.loadPersonas);
  const allTools = useSkillStore((s) => s.tools.map(t => t.name));
  const loadCapabilities = useSkillStore((s) => s.loadCapabilities);
  const personaId = useSessionStore((s) => s.personaId);
  const setPersonaId = useSessionStore((s) => s.setPersonaId);
  const setActivePage = useUIStore((s) => s.setActivePage);
  const [search, setSearch] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<PersonaInfo>(emptyPersona());
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState('');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const validateField = (name: string, value: string) => {
    setFieldErrors((prev) => {
      const next = { ...prev };
      if (name === 'id' || name === 'name') {
        if (!value.trim()) next[name] = name === 'id' ? 'ID 不能为空' : '名称不能为空';
        else delete next[name];
      }
      return next;
    });
  };

  const isFormValid = !!form.id.trim() && !!form.name.trim();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [connectors, setConnectors] = useState<ConnectorInfo[]>([]);

  React.useEffect(() => { loadPersonas(); loadCapabilities(); }, [loadPersonas, loadCapabilities]);
  React.useEffect(() => { fetchConnectors().then(setConnectors).catch(() => {}); }, []);

  const kbConnectors = connectors.filter((c) => c.type === 'knowledge');
  const selectedKBs: string[] = form.knowledge_bases || [];
  // Categorize tools: local vs MCP (grouped by connector)
  const mcpToolNames = new Set(connectors.flatMap((c) => c.tools));
  const localTools = allTools.filter((t) => !mcpToolNames.has(t));
  const connectorTools = connectors.filter((c) => c.tools.length > 0);
  const [expandedToolGroups, setExpandedToolGroups] = useState<Set<string>>(new Set(['local']));
  const noToolFilter = form.enabled_tools === null || form.enabled_tools === undefined;
  const kbEnabled = selectedKBs.includes('local');

  const toolCountLabel = (names: string[]) => {
    if (noToolFilter) return '全部';
    const selected = names.filter((t) => toolList.includes(t)).length;
    return `${selected}/${names.length}`;
  };

  // Local tools: hide search_knowledge if local KB is not enabled
  const visibleLocalTools = kbEnabled ? localTools : localTools.filter((t) => t !== 'search_knowledge');

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
    setFieldErrors({});
    setShowForm(true);
  };

  const startEdit = (p: PersonaInfo) => {
    setForm({ ...p, system_prompt: p.system_prompt || '', enabled_tools: p.enabled_tools || null, knowledge_bases: p.knowledge_bases || null });
    setEditingId(p.id);
    setFormError('');
    setFieldErrors({});
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

  const toggleKb = (kbName: string) => {
    const next = selectedKBs.includes(kbName)
      ? selectedKBs.filter((x: string) => x !== kbName)
      : [...selectedKBs, kbName];
    let nextTools = toolList;
    // If unchecking local KB, also remove search_knowledge from enabled_tools
    if (kbName === 'local' && !next.includes('local') && nextTools.includes('search_knowledge')) {
      nextTools = nextTools.filter((x: string) => x !== 'search_knowledge');
    }
    setForm({ ...form, knowledge_bases: next, enabled_tools: nextTools.length > 0 ? nextTools : null });
  };

  const handleSubmit = async () => {
    const f = form;
    setFieldErrors({});
    if (!f.id.trim()) { setFieldErrors({ id: 'ID 不能为空' }); return; }
    if (!f.name.trim()) { setFieldErrors({ name: '名称不能为空' }); return; }

    setSubmitting(true);
    setFormError('');
    try {
      await savePersona({
        id: f.id.trim(),
        name: f.name.trim(),
        description: f.description?.trim() || '',
        system_prompt: f.system_prompt?.trim() || '',
        enabled_tools: toolList.length > 0 ? toolList : undefined,
        knowledge_bases: selectedKBs.length > 0 ? selectedKBs : undefined,
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

  const handleDelete = (id: string) => {
    const persona = personas.find((p) => p.id === id);
    useConfirmStore.getState().requestConfirm({
      title: '删除专家',
      message: `确定要删除专家 "${persona?.name || id}" 吗？此操作不可恢复。`,
      danger: true,
      onConfirm: async () => {
        try {
          await deletePersona(id);
          if (personaId === id) setPersonaId(null);
          await loadPersonas();
        } catch (err: unknown) {
          const msg = err instanceof Error ? err.message : '删除专家失败';
          useToastStore.getState().addToast(msg, 'error');
        }
      },
    });
  };

  return (
    <div className="page">
      <div className="page-header">
        <button className="page-back" onClick={() => setActivePage('chat')} aria-label="返回聊天">
          <Icon name="chevron-left" size={18} />
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
        {personasLoading && <Loading />}

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
            {activePersona.knowledge_bases && activePersona.knowledge_bases.length > 0 && (
              <div className="expert-active-tools">
                {activePersona.knowledge_bases.map((kb: string) => (
                  <span key={kb} className="tag type-kb">{kb === 'local' ? '本地知识库' : kb}</span>
                ))}
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

        {!personasLoading && personas.length === 0 && !showForm && (
          <EmptyState icon="briefcase" title="暂无专家" description={`点击"添加"创建第一个`} />
        )}

        {personas.length > 0 && search && filtered.length === 0 && (
          <EmptyState icon="search" title="无匹配专家" />
        )}

        {showForm && (
          <div className="card form-card">
            <div className="card-form-head">
              <span className="card-title">{editingId ? `编辑: ${editingId}` : '添加专家'}</span>
            </div>
            <div className="form-grid">
              <label className="form-field">
                <span>ID (英文标识)</span>
                <input
                  type="text"
                  value={form.id}
                  disabled={!!editingId}
                  placeholder="例如 coder"
                  className={fieldErrors.id ? 'field-invalid' : ''}
                  onChange={(e) => setForm({ ...form, id: e.target.value })}
                  onBlur={(e) => validateField('id', e.target.value)}
                />
                {fieldErrors.id && <span className="field-error">{fieldErrors.id}</span>}
              </label>
              <label className="form-field">
                <span>名称</span>
                <input
                  type="text"
                  value={form.name}
                  placeholder="例如 代码专家"
                  className={fieldErrors.name ? 'field-invalid' : ''}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  onBlur={(e) => validateField('name', e.target.value)}
                />
                {fieldErrors.name && <span className="field-error">{fieldErrors.name}</span>}
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
                <span>关联知识库</span>
                <div className="tool-toggle-grid">
                  <button
                    className={`tool-toggle${selectedKBs.includes('local') ? ' on' : ''}`}
                    onClick={() => toggleKb('local')}
                    type="button"
                  >
                    {selectedKBs.includes('local') && <Icon name="check" size={11} />}
                    本地知识库
                  </button>
                  {kbConnectors.map((c) => {
                    const on = selectedKBs.includes(c.name);
                    return (
                      <button
                        key={c.name}
                        className={`tool-toggle${on ? ' on' : ''}`}
                        onClick={() => toggleKb(c.name)}
                        type="button"
                      >
                        {on && <Icon name="check" size={11} />}
                        {c.name}
                      </button>
                    );
                  })}
                </div>
                {kbConnectors.length === 0 && (
                  <span className="expert-kb-hint" style={{ marginTop: 6 }}>
                    还没有知识库连接器 —
                    <button className="expert-kb-link" onClick={() => { setActivePage('connectors'); }}>添加</button>
                  </span>
                )}
              </div>
              <div className="form-field">
                <span>启用的工具</span>
                <div className="tool-group-list">
                  {/* Local tools */}
                  {visibleLocalTools.length > 0 && (
                    <div className="tool-group">
                      <button
                        className="tool-group-label-btn"
                        onClick={() => {
                          setExpandedToolGroups((prev) => {
                            const n = new Set(prev);
                            if (n.has('local')) n.delete('local'); else n.add('local');
                            return n;
                          });
                        }}
                      >
                        {expandedToolGroups.has('local') ? '[-]' : '[+]'} 本地 ({toolCountLabel(visibleLocalTools)})
                      </button>
                      {expandedToolGroups.has('local') && (
                        <div className="tool-toggle-grid">
                          {visibleLocalTools.map((t: string) => {
                            const on = toolList.includes(t);
                            return (
                              <button key={t} className={`tool-toggle${on ? ' on' : ''}`} onClick={() => toggleFormTool(t)} type="button">
                                {on && <Icon name="check" size={11} />} {t}
                              </button>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  )}
                  {/* MCP connector tools */}
                  {connectorTools.map((c) => (
                    <div key={c.name} className="tool-group">
                      <button
                        className="tool-group-label-btn"
                        onClick={() => {
                          setExpandedToolGroups((prev) => {
                            const n = new Set(prev);
                            if (n.has(c.name)) n.delete(c.name); else n.add(c.name);
                            return n;
                          });
                        }}
                      >
                        {expandedToolGroups.has(c.name) ? '[-]' : '[+]'} {c.name} ({toolCountLabel(c.tools)})
                      </button>
                      {expandedToolGroups.has(c.name) && (
                        <div className="tool-toggle-grid">
                          {c.tools.map((t: string) => {
                            const on = toolList.includes(t);
                            return (
                              <button key={t} className={`tool-toggle${on ? ' on' : ''}`} onClick={() => toggleFormTool(t)} type="button">
                                {on && <Icon name="check" size={11} />} {t}
                              </button>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
            {formError && <p className="card-form-error">{formError}</p>}
            <div className="card-form-actions">
              <button className="btn btn-primary" onClick={handleSubmit} disabled={submitting || !isFormValid}>
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
                    <span
                      className="expert-bracket"
                      onClick={(e) => { e.stopPropagation(); setPersonaId(isActive ? null : p.id); }}
                      title={isActive ? '停用' : '激活'}
                    >
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
                    {p.knowledge_bases && p.knowledge_bases.length > 0 && (
                      <div className="expert-detail-section">
                        <span className="expert-detail-label">知识库</span>
                        <div className="expert-detail-tools">
                          {p.knowledge_bases.map((kb: string) => (
                            <span key={kb} className="tag type-kb">{kb}</span>
                          ))}
                        </div>
                      </div>
                    )}
                    {p.enabled_tools && p.enabled_tools.length > 0 && (
                      <div className="expert-detail-section">
                        <span className="expert-detail-label">工具</span>
                        <div className="expert-detail-tools">
                          {p.enabled_tools.map((t: string) => (
                            <span key={t} className="tag">{t}</span>
                          ))}
                        </div>
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
