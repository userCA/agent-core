import React, { useState, useMemo, useRef } from 'react';
import { useSkillStore } from '../../stores/skill-store';
import { useUIStore } from '../../stores/ui-store';
import { useToastStore } from '../../stores/toast-store';
import { importSkill } from '../../api/client';
import * as Switch from '@radix-ui/react-switch';
import * as Dialog from '@radix-ui/react-dialog';
import Icon from '../shared/Icon';
import TooltipWrap from '../shared/TooltipWrap';
import Loading from '../shared/Loading';
import EmptyState from '../shared/EmptyState';
import EvolutionPanel from './EvolutionPanel';
import CollapsibleSection from '../shared/CollapsibleSection';
import './Pages.css';

interface Props { onBack?: () => void; }

export default function SkillsPage({ onBack }: Props) {
  const skills = useSkillStore((s) => s.skills);
  const tools = useSkillStore((s) => s.tools);
  const loading = useSkillStore((s) => s.loading);
  const enabled = useSkillStore((s) => s.enabled);
  const loadCapabilities = useSkillStore((s) => s.loadCapabilities);
  const toggleSkill = useSkillStore((s) => s.toggleSkill);
  const setH5ActiveTab = useUIStore((s) => s.setH5ActiveTab);
  const back = onBack ?? (() => setH5ActiveTab('chat'));
  const fileRef = useRef<HTMLInputElement>(null);
  const [importing, setImporting] = useState(false);
  const [search, setSearch] = useState('');

  // Tools section state
  const [toolSearch, setToolSearch] = useState('');
  const [expandedTools, setExpandedTools] = useState<Set<string>>(new Set());
  const [toolPage, setToolPage] = useState(1);
  const TOOLS_PER_PAGE = 24;
  const DESC_PREVIEW_LEN = 60;

  // Create skill modal state
  const [showCreate, setShowCreate] = useState(false);
  const [createName, setCreateName] = useState('');
  const [createDesc, setCreateDesc] = useState('');
  const [createContent, setCreateContent] = useState('');
  const [creating, setCreating] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const validateField = (field: string, value: string) => {
    setFieldErrors((prev) => {
      const next = { ...prev };
      if (field === 'name') {
        if (!value.trim()) next.name = '名称不能为空';
        else delete next.name;
      } else if (field === 'content') {
        if (!value.trim()) next.content = '内容不能为空';
        else delete next.content;
      }
      return next;
    });
  };

  React.useEffect(() => {
    loadCapabilities();
  }, [loadCapabilities]);

  const filtered = useMemo(() => {
    if (!search.trim()) return skills;
    const q = search.toLowerCase();
    return skills.filter((s) =>
      s.name.toLowerCase().includes(q) || s.description.toLowerCase().includes(q)
    );
  }, [skills, search]);

  const enabledCount = skills.filter((s) => enabled.has(s.name)).length;

  const filteredTools = useMemo(() => {
    if (!toolSearch.trim()) return tools;
    const q = toolSearch.toLowerCase();
    return tools.filter((t) =>
      t.name.toLowerCase().includes(q) || t.description.toLowerCase().includes(q)
    );
  }, [tools, toolSearch]);

  const totalToolPages = Math.ceil(filteredTools.length / TOOLS_PER_PAGE);
  const pagedTools = useMemo(() => {
    const start = (toolPage - 1) * TOOLS_PER_PAGE;
    return filteredTools.slice(start, start + TOOLS_PER_PAGE);
  }, [filteredTools, toolPage, TOOLS_PER_PAGE]);

  // Reset page when search changes
  const handleToolSearch = (v: string) => {
    setToolSearch(v);
    setToolPage(1);
  };

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    try {
      const content = await file.text();
      const name = file.name.replace(/\.md$/i, '');
      await importSkill(name, content);
      await loadCapabilities();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '导入技能失败';
      useToastStore.getState().addToast(msg, 'error');
    } finally {
      setImporting(false);
      e.target.value = '';
    }
  };

  const resetCreateForm = () => {
    setCreateName('');
    setCreateDesc('');
    setCreateContent('');
  };

  const handleCreate = async () => {
    const name = createName.trim();
    const errs: Record<string, string> = {};
    if (!name) errs.name = '名称不能为空';
    if (!createContent.trim()) errs.content = '内容不能为空';
    if (Object.keys(errs).length > 0) {
      setFieldErrors(errs);
      return;
    }
    setCreating(true);
    try {
      // Generate proper YAML frontmatter
      let frontmatter = '---\n';
      frontmatter += `name: ${name}\n`;
      if (createDesc.trim()) {
        frontmatter += `description: ${createDesc.trim()}\n`;
      }
      frontmatter += '---\n\n';
      const fullContent = frontmatter + createContent.trim() + '\n';
      await importSkill(name, fullContent);
      await loadCapabilities();
      setShowCreate(false);
      resetCreateForm();
      useToastStore.getState().addToast(`技能 "${name}" 创建成功`, 'success');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '创建技能失败';
      useToastStore.getState().addToast(msg, 'error');
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="page">
      <div className="page-header">
        <button className="page-back" onClick={back} aria-label="返回聊天">
          <Icon name="chevron-left" size={18} />
        </button>
        <h1 className="page-title">技能管理</h1>
        <div className="page-header-right">
          <div className="page-search">
            <Icon name="search" size={14} />
            <input
              type="text"
              placeholder="搜索技能..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              aria-label="搜索技能"
            />
          </div>
          <TooltipWrap label="粘贴技能描述创建">
            <button
              className="btn"
              onClick={() => {
                resetCreateForm();
                setShowCreate(true);
              }}
              disabled={importing}
            >
              <Icon name="plus" size={14} /> 创建
            </button>
          </TooltipWrap>
          <TooltipWrap label="导入 .md 技能文件">
            <button
              className="btn"
              onClick={() => fileRef.current?.click()}
            disabled={importing}
          >
            <Icon name="upload" size={14} /> {importing ? '导入中...' : '导入'}
          </button>
          </TooltipWrap>
          <input ref={fileRef} type="file" accept=".md" style={{ display: 'none' }} onChange={handleImport} />
        </div>
      </div>

      <div className="page-body">
        {loading && <Loading />}

        {!loading && skills.length === 0 && (
          <EmptyState icon="code" title="暂无技能" description={`点击"导入"按钮添加技能文件`} />
        )}

        {!loading && skills.length > 0 && search && filtered.length === 0 && (
          <EmptyState icon="search" title="无匹配技能" />
        )}

        {!loading && skills.length > 0 && (
          <p className="page-section-title">
            已启用 {enabledCount}/{skills.length}
          </p>
        )}

        <div className="card-grid">
          {filtered.map((s) => {
            const isOn = enabled.has(s.name);
            return (
              <div key={s.name} className={`card${!isOn ? ' off' : ''}`}>
                <div className="card-head">
                  <span className="card-icon"><Icon name="code" size={16} /></span>
                  <span className="card-title">{s.name}</span>
                  <Switch.Root
                    className="skill-toggle"
                    checked={isOn}
                    onCheckedChange={() => toggleSkill(s.name)}
                    aria-label={s.name}
                  >
                    <Switch.Thumb className="skill-toggle-knob" />
                  </Switch.Root>
                </div>
                <p className="card-desc">{s.description}</p>
                <div className="card-meta">
                  <code>/skill:{s.name}</code>
                </div>
                <EvolutionPanel skillName={s.name} />
              </div>
            );
          })}
        </div>

        {tools.length > 0 && (
          <>
            <h2 className="page-section-title">可用工具 ({filteredTools.length}{filteredTools.length !== tools.length ? ` / ${tools.length}` : ''})</h2>

            <div className="page-search" style={{ marginBottom: 8 }}>
              <Icon name="search" size={14} />
              <input
                type="text"
                placeholder="搜索工具名称或描述..."
                value={toolSearch}
                onChange={(e) => handleToolSearch(e.target.value)}
                aria-label="搜索工具"
              />
            </div>

            {filteredTools.length === 0 ? (
              <p className="page-empty">无匹配工具</p>
            ) : (
              <>
                <div className="card-grid">
                  {pagedTools.map((t) => {
                    const isOpen = expandedTools.has(t.name);
                    const needsExpand = t.description.length > DESC_PREVIEW_LEN;
                    const preview = needsExpand && !isOpen
                      ? t.description.slice(0, DESC_PREVIEW_LEN) + '…'
                      : t.description;
                    return (
                      <CollapsibleSection
                        key={t.name}
                        open={isOpen}
                        onOpenChange={(open) => {
                          if (!needsExpand) return;
                          setExpandedTools((prev) => {
                            const next = new Set(prev);
                            if (open) next.add(t.name);
                            else next.delete(t.name);
                            return next;
                          });
                        }}
                        trigger={
                          <div className={`card${needsExpand ? ' card-clickable' : ''}`}>
                            <div className="card-head">
                              <span className="card-title">{t.name}</span>
                              {needsExpand && (
                                <Icon name={isOpen ? 'chevron-up' : 'chevron-down'} size={12} />
                              )}
                            </div>
                            <p className="card-desc">{preview}</p>
                          </div>
                        }
                        contentClassName="card-desc-extra"
                      >
                        {needsExpand && (
                          <p className="card-desc">{t.description.slice(DESC_PREVIEW_LEN)}</p>
                        )}
                      </CollapsibleSection>
                    );
                  })}
                </div>

                {totalToolPages > 1 && (
                  <div style={{ display: 'flex', justifyContent: 'center', gap: 8, marginTop: 12 }}>
                    <button
                      className="btn"
                      disabled={toolPage <= 1}
                      onClick={() => setToolPage((p) => Math.max(1, p - 1))}
                    >
                      上一页
                    </button>
                    <span style={{ fontSize: 12, color: 'var(--ash)', fontFamily: 'var(--font-mono)', display: 'flex', alignItems: 'center' }}>
                      {toolPage} / {totalToolPages}
                    </span>
                    <button
                      className="btn"
                      disabled={toolPage >= totalToolPages}
                      onClick={() => setToolPage((p) => Math.min(totalToolPages, p + 1))}
                    >
                      下一页
                    </button>
                  </div>
                )}
              </>
            )}
          </>
        )}
      </div>

      {/* Create skill modal */}
      <Dialog.Root open={showCreate} onOpenChange={(open) => { if (!creating) setShowCreate(open); }}>
        <Dialog.Portal>
          <Dialog.Overlay className="modal-backdrop" />
          <Dialog.Content
            className="modal-content"
            style={{ maxWidth: 560 }}
            aria-describedby="create-skill-desc"
          >
            <Dialog.Title className="modal-title">创建技能</Dialog.Title>
              <p id="create-skill-desc" className="sr-only">
                填写技能名称、描述和内容以创建新技能。
              </p>
              <label className="auth-field">
                <span>名称 <span className="required" style={{ color: 'var(--danger)' }}>*</span></span>
                <input
                  type="text"
                  value={createName}
                  onChange={(e) => setCreateName(e.target.value)}
                  onBlur={(e) => validateField('name', e.target.value)}
                  placeholder="英文名称，如 my-skill"
                  disabled={creating}
                  autoFocus
                  className={fieldErrors.name ? 'field-invalid' : ''}
                />
                {fieldErrors.name && <span className="field-error">{fieldErrors.name}</span>}
              </label>
              <label className="auth-field">
                <span>描述</span>
                <input
                  type="text"
                  value={createDesc}
                  onChange={(e) => setCreateDesc(e.target.value)}
                  placeholder="可选，简要描述技能用途"
                  disabled={creating}
                />
              </label>
              <label className="auth-field">
                <span>内容 <span style={{ color: 'var(--danger)' }}>*</span></span>
                <textarea
                  value={createContent}
                  onChange={(e) => setCreateContent(e.target.value)}
                  onBlur={(e) => validateField('content', e.target.value)}
                  placeholder="粘贴 Markdown 技能描述..."
                  disabled={creating}
                  rows={12}
                  style={{ resize: 'vertical', minHeight: 200 }}
                  className={fieldErrors.content ? 'field-invalid' : ''}
                />
                {fieldErrors.content && <span className="field-error">{fieldErrors.content}</span>}
              </label>
              <div className="auth-actions">
                <Dialog.Close asChild>
                  <button
                    className="btn"
                    onClick={() => { if (!creating) { setShowCreate(false); } }}
                    disabled={creating}
                  >
                    取消
                  </button>
                </Dialog.Close>
                <button
                  className="btn btn-primary"
                  onClick={handleCreate}
                  disabled={creating || !createName.trim() || !createContent.trim()}
                >
                  {creating ? '创建中...' : '创建'}
                </button>
              </div>
            </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  );
}
