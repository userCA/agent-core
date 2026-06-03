import React, { useEffect, useState, useMemo } from 'react';
import { fetchConnectors, addConnector, removeConnector, type ConnectorInfo, type AddConnectorPayload } from '../../api/client';
import { useUIStore } from '../../stores/ui-store';
import { useConfirmStore } from '../../stores/confirm-store';
import Icon from '../shared/Icon';
import Loading from '../shared/Loading';
import { SkeletonList } from '../shared/Skeleton';
import EmptyState from '../shared/EmptyState';
import './Pages.css';

const TRANSPORT_OPTIONS: { value: string; label: string }[] = [
  { value: 'stdio', label: 'STDIO (命令行)' },
  { value: 'sse', label: 'SSE (远程)' },
  { value: 'streamable_http', label: 'HTTP (远程)' },
];

function emptyPayload(): AddConnectorPayload {
  return { name: '', transport: 'stdio', command: '', args: [], url: '', env: {}, type: 'tool' };
}

export default function ConnectorsPage() {
  const setActivePage = useUIStore((s) => s.setActivePage);
  const [connectors, setConnectors] = useState<ConnectorInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<AddConnectorPayload>(emptyPayload());
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState('');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [openDropdown, setOpenDropdown] = useState<string | null>(null);

  const validateField = (name: string, value: string) => {
    setFieldErrors((prev) => {
      const next = { ...prev };
      if (name === 'name') {
        if (!value.trim()) next.name = '名称不能为空';
        else delete next.name;
      } else if (name === 'url') {
        if (form.transport !== 'stdio' && !value.trim()) next.url = '远程连接需要填写 URL';
        else delete next.url;
      } else if (name === 'command') {
        if (form.transport === 'stdio' && !value.trim()) next.command = 'STDIO 连接需要填写命令';
        else delete next.command;
      }
      return next;
    });
  };

  const isFormValid = !!form.name.trim() &&
    (form.transport === 'stdio' ? !!form.command?.trim() : !!form.url?.trim());
  const [typeFilter, setTypeFilter] = useState<string>('all'); // 'all' | 'tool' | 'knowledge'

  const toggleDropdown = (name: string) => {
    setOpenDropdown((prev) => (prev === name ? null : name));
  };

  const load = () => {
    setLoading(true);
    fetchConnectors()
      .then((data) => { setConnectors(data); setLoading(false); })
      .catch((err) => { setError(err.message); setLoading(false); });
  };

  useEffect(() => { load(); }, []);

  // Esc to close
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      if (openDropdown) { setOpenDropdown(null); return; }
      if (showForm && !submitting) { setShowForm(false); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [showForm, submitting, openDropdown]);

  const filtered = useMemo(() => {
    let list = connectors;
    if (typeFilter !== 'all') list = list.filter((c) => (c.type || 'tool') === typeFilter);
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter((c) => c.name.toLowerCase().includes(q) || c.tools.some((t) => t.toLowerCase().includes(q)));
    }
    return list;
  }, [connectors, search, typeFilter]);

  const toggleExpand = (name: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const handleAdd = () => {
    setForm(emptyPayload());
    setFormError('');
    setFieldErrors({});
    setShowForm(true);
  };

  const handleSubmit = async () => {
    const f = form;
    setFieldErrors({});
    if (!f.name.trim()) { setFieldErrors({ name: '名称不能为空' }); return; }
    if (f.transport !== 'stdio' && !f.url?.trim()) { setFieldErrors({ url: '远程连接需要填写 URL' }); return; }
    if (f.transport === 'stdio' && !f.command?.trim()) { setFieldErrors({ command: 'STDIO 连接需要填写命令' }); return; }

    setSubmitting(true);
    setFormError('');
    try {
      await addConnector({
        name: f.name.trim(),
        transport: f.transport,
        command: f.transport === 'stdio' ? f.command?.trim() || undefined : undefined,
        args: f.transport === 'stdio' && f.args && f.args.length > 0 ? f.args : undefined,
        url: f.transport !== 'stdio' ? f.url?.trim() || undefined : undefined,
        env: f.env && Object.keys(f.env).length > 0 ? f.env : undefined,
        type: f.type || 'tool',
      });
      setShowForm(false);
      load(); // Reload list after adding
    } catch (err: unknown) {
      setFormError(err instanceof Error ? err.message : '添加失败');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = (name: string) => {
    useConfirmStore.getState().requestConfirm({
      title: '删除连接器',
      message: `确定要删除连接器 "${name}" 吗？此操作不可恢复。`,
      danger: true,
      onConfirm: async () => {
        try {
          await removeConnector(name);
          load();
        } catch (err: unknown) {
          setError(err instanceof Error ? err.message : '删除失败');
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
        <h1 className="page-title">连接器管理</h1>
        <div className="page-header-right">
          <div className="page-search">
            <Icon name="search" size={14} />
            <input
              type="text"
              placeholder="搜索连接器或工具..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              aria-label="搜索连接器"
            />
          </div>
          <button className="btn" onClick={handleAdd}>
            <Icon name="plus" size={14} /> 添加
          </button>
        </div>
      </div>

      <div className="page-body">
        {!loading && connectors.length > 0 && (
          <div className="page-filter-row">
            {[
              { key: 'all', label: '全部' },
              { key: 'tool', label: '工具' },
              { key: 'knowledge', label: '知识库' },
            ].map((f) => (
              <button
                key={f.key}
                className={`filter-tab${typeFilter === f.key ? ' active' : ''}`}
                onClick={() => setTypeFilter(f.key)}
              >
                {f.label}
              </button>
            ))}
          </div>
        )}
        {loading && <SkeletonList count={4} />}
        {error && (
          <div className="page-empty">
            <p className="page-error">{error}</p>
            <button className="btn" onClick={load} style={{ marginTop: 12 }}>
              <Icon name="spinner" size={12} /> 重试
            </button>
          </div>
        )}

        {!loading && !error && connectors.length === 0 && !showForm && (
          <EmptyState
            icon="tool"
            title="暂无连接器"
            description={`在项目根目录创建 .mcp.json 或点击"添加"`}
          />
        )}

        {!loading && connectors.length > 0 && search && filtered.length === 0 && (
          <EmptyState icon="search" title="无匹配连接器" />
        )}

        {showForm && (
          <div className="card form-card">
            <div className="card-form-head">
              <span className="card-title">{form.name ? `编辑: ${form.name}` : '添加连接器'}</span>
            </div>
            <div className="form-grid">
              <label className="form-field">
                <span>名称</span>
                <input
                  type="text"
                  value={form.name}
                  placeholder="例如 amap"
                  className={fieldErrors.name ? 'field-invalid' : ''}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  onBlur={(e) => validateField('name', e.target.value)}
                />
                {fieldErrors.name && <span className="field-error">{fieldErrors.name}</span>}
              </label>
              <label className="form-field">
                <span>传输方式</span>
                <div className="form-dropdown">
                  <button className="form-select" onClick={() => toggleDropdown('transport')} type="button">
                    {TRANSPORT_OPTIONS.find((o) => o.value === form.transport)?.label || '选择...'}
                  </button>
                  {openDropdown === 'transport' && (
                    <>
                      <div className="more-backdrop" onClick={() => setOpenDropdown(null)} />
                      <div className="form-dropdown-menu">
                      {TRANSPORT_OPTIONS.map((o) => (
                        <button key={o.value} className={`form-dropdown-item${form.transport === o.value ? ' selected' : ''}`}
                          onClick={() => { setForm({ ...form, transport: o.value }); setOpenDropdown(null); }}>
                          {o.label}
                        </button>
                      ))}
                    </div>
                    </>
                  )}
                </div>
              </label>
              <label className="form-field">
                <span>类型</span>
                <div className="form-dropdown">
                  <button className="form-select" onClick={() => toggleDropdown('type')} type="button">
                    {form.type === 'knowledge' ? '知识库' : '工具'}
                  </button>
                  {openDropdown === 'type' && (
                    <>
                      <div className="more-backdrop" onClick={() => setOpenDropdown(null)} />
                      <div className="form-dropdown-menu">
                      <button className={`form-dropdown-item${form.type !== 'knowledge' ? ' selected' : ''}`}
                        onClick={() => { setForm({ ...form, type: 'tool' }); setOpenDropdown(null); }}>
                        工具
                      </button>
                      <button className={`form-dropdown-item${form.type === 'knowledge' ? ' selected' : ''}`}
                        onClick={() => { setForm({ ...form, type: 'knowledge' }); setOpenDropdown(null); }}>
                        知识库
                      </button>
                    </div>
                    </>
                  )}
                </div>
              </label>
              {form.transport === 'stdio' ? (
                <>
                  <label className="form-field">
                    <span>命令</span>
                    <input
                      type="text"
                      value={form.command || ''}
                      placeholder="例如 npx"
                      className={fieldErrors.command ? 'field-invalid' : ''}
                      onChange={(e) => setForm({ ...form, command: e.target.value })}
                      onBlur={(e) => validateField('command', e.target.value)}
                    />
                    {fieldErrors.command && <span className="field-error">{fieldErrors.command}</span>}
                  </label>
                  <label className="form-field">
                    <span>参数 (逗号分隔)</span>
                    <input type="text" value={(form.args || []).join(', ')} placeholder="例如 -y, @amap/amap-maps-mcp-server"
                      onChange={(e) => setForm({ ...form, args: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })} />
                  </label>
                </>
              ) : (
                <label className="form-field">
                  <span>URL</span>
                  <input
                    type="text"
                    value={form.url || ''}
                    placeholder="https://mcp.example.com/sse"
                    className={fieldErrors.url ? 'field-invalid' : ''}
                    onChange={(e) => setForm({ ...form, url: e.target.value })}
                    onBlur={(e) => validateField('url', e.target.value)}
                  />
                  {fieldErrors.url && <span className="field-error">{fieldErrors.url}</span>}
                </label>
              )}
              <label className="form-field">
                <span>环境变量 (JSON, 可选)</span>
                <input type="text" value={form.env ? JSON.stringify(form.env) : ''} placeholder='{"API_KEY": "xxx"}'
                  onChange={(e) => {
                    try { setForm({ ...form, env: e.target.value ? JSON.parse(e.target.value) : {} }); } catch { /* wait for valid JSON */ }
                  }} />
              </label>
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

        <div className="connector-list">
          {filtered.map((c) => {
            const isExpanded = expanded.has(c.name);
            const isConnected = c.status === 'connected';
            return (
              <div key={c.name} className={`connector-item${isConnected ? ' ok' : ' err'}`}>
                <button
                  className="connector-item-header"
                  onClick={() => toggleExpand(c.name)}
                  aria-expanded={isExpanded}
                >
                  <div className="connector-item-head">
                    <span className={`dot${isConnected ? ' green' : ' red'}`} />
                    <span className="connector-item-name">{c.name}</span>
                    <span className="connector-item-badge">{c.transport}</span>
                    {(c.type || 'tool') === 'knowledge' && <span className="connector-item-badge type-kb">知识库</span>}
                  </div>
                  <div className="connector-item-meta">
                    <span>{c.tools.length} 工具</span>
                    <span className="connector-item-arrow">
                      {isExpanded ? <Icon name="chevron-up" size={12} /> : <Icon name="chevron-down" size={12} />}
                    </span>
                  </div>
                </button>
                {isExpanded && (
                  <div className="connector-item-tools">
                    {c.tools.length === 0 ? (
                      <span className="connector-item-empty">暂无工具</span>
                    ) : (
                      c.tools.map((t) => (
                        <span key={t} className="connector-tool-badge">{t}</span>
                      ))
                    )}
                    <div className="connector-item-tool-actions">
                      <button className="btn btn-danger" onClick={() => handleDelete(c.name)} title="删除连接器">
                        <Icon name="cancel" size={12} /> 删除
                      </button>
                    </div>
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
