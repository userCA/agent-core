import React, { useState, useMemo, useRef } from 'react';
import { useSkillStore } from '../../stores/skill-store';
import { useUIStore } from '../../stores/ui-store';
import { importSkill } from '../../api/client';
import Icon from '../shared/Icon';
import './Pages.css';

export default function SkillsPage() {
  const skills = useSkillStore((s) => s.skills);
  const tools = useSkillStore((s) => s.tools);
  const loading = useSkillStore((s) => s.loading);
  const enabled = useSkillStore((s) => s.enabled);
  const loadCapabilities = useSkillStore((s) => s.loadCapabilities);
  const toggleSkill = useSkillStore((s) => s.toggleSkill);
  const setActivePage = useUIStore((s) => s.setActivePage);
  const fileRef = useRef<HTMLInputElement>(null);
  const [importing, setImporting] = useState(false);
  const [search, setSearch] = useState('');

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

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    try {
      const content = await file.text();
      const name = file.name.replace(/\.md$/i, '');
      await importSkill(name, content);
      await loadCapabilities();
    } catch {
      // ignore import errors
    } finally {
      setImporting(false);
      e.target.value = '';
    }
  };

  return (
    <div className="page">
      <div className="page-header">
        <button className="page-back" onClick={() => setActivePage('chat')} aria-label="返回聊天">
          <Icon name="chevron-up" size={18} style={{ transform: 'rotate(-90deg)' }} />
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
          <button
            className="btn"
            onClick={() => fileRef.current?.click()}
            title="导入 .md 技能文件"
            disabled={importing}
          >
            <Icon name="upload" size={14} /> {importing ? '导入中...' : '导入'}
          </button>
          <input ref={fileRef} type="file" accept=".md" style={{ display: 'none' }} onChange={handleImport} />
        </div>
      </div>

      <div className="page-body">
        {loading && <p className="page-empty">加载中...</p>}

        {!loading && skills.length === 0 && <p className="page-empty">暂无技能</p>}

        {!loading && skills.length > 0 && search && filtered.length === 0 && (
          <p className="page-empty">无匹配技能</p>
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
                  <button
                    className={`skill-toggle${isOn ? ' on' : ''}`}
                    onClick={() => toggleSkill(s.name)}
                    role="switch"
                    aria-checked={isOn}
                    aria-label={s.name}
                  >
                    <span className="skill-toggle-knob" />
                  </button>
                </div>
                <p className="card-desc">{s.description}</p>
                <div className="card-meta">
                  <code>/skill:{s.name}</code>
                </div>
              </div>
            );
          })}
        </div>

        {tools.length > 0 && (
          <>
            <h2 className="page-section-title">内置工具 ({tools.length})</h2>
            <div className="tag-cloud">
              {tools.map((t) => (
                <span key={t} className="tag">{t}</span>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
