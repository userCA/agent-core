import React, { useState, useEffect, useRef } from 'react';
import { useUIStore } from '../../stores/ui-store';
import { useToastStore } from '../../stores/toast-store';
import { useConfirmStore } from '../../stores/confirm-store';
import { fetchKnowledgeDocs, fetchKnowledgeDoc, uploadKnowledgeDoc, uploadKnowledgeFile, deleteKnowledgeDoc, type KnowledgeDoc, type KnowledgeDocDetail } from '../../api/client';
import Icon from '../shared/Icon';
import Loading from '../shared/Loading';
import { SkeletonList } from '../shared/Skeleton';
import EmptyState from '../shared/EmptyState';
import './Pages.css';

const UPLOAD_TIMEOUT = 120_000; // 2 min timeout for large PDF uploads

export default function KnowledgePage() {
  const setActivePage = useUIStore((s) => s.setActivePage);
  const [docs, setDocs] = useState<KnowledgeDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState('');
  const [content, setContent] = useState('');
  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState('');
  const [uploadError, setUploadError] = useState('');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [details, setDetails] = useState<Record<string, KnowledgeDocDetail | null>>({});
  const fileRef = useRef<HTMLInputElement>(null);

  const [loadError, setLoadError] = useState('');

  const load = () => {
    setLoading(true);
    setLoadError('');
    fetchKnowledgeDocs()
      .then((data) => { setDocs(data); setLoading(false); })
      .catch((err) => { setLoadError(err instanceof Error ? err.message : '加载失败'); setLoading(false); });
  };

  useEffect(() => { load(); }, []);

  const showResult = (chunks: number) => {
    setUploadStatus(`完成 — ${chunks} 个片段已索引`);
    setUploading(false);
    setTimeout(() => { setUploadStatus(''); setUploading(false); }, 3000);
  };

  const showError = (msg: string) => {
    setUploadError(msg);
    setUploading(false);
    setTimeout(() => setUploadError(''), 5000);
  };

  const validateField = (field: string, value: string) => {
    setFieldErrors((prev) => {
      const next = { ...prev };
      if (field === 'name') {
        if (!value.trim()) next.name = '文档名称不能为空';
        else delete next.name;
      } else if (field === 'content') {
        if (!value.trim()) next.content = '文档内容不能为空';
        else delete next.content;
      }
      return next;
    });
  };

  const handleUpload = async () => {
    const errs: Record<string, string> = {};
    if (!name.trim()) errs.name = '文档名称不能为空';
    if (!content.trim()) errs.content = '文档内容不能为空';
    if (Object.keys(errs).length > 0) {
      setFieldErrors(errs);
      return;
    }
    setUploading(true);
    setUploadError('');
    setUploadStatus('正在分块并生成向量...');
    try {
      const result = await uploadKnowledgeDoc(name.trim(), content);
      showResult(result.chunks);
      setName('');
      setContent('');
      setShowForm(false);
      load();
    } catch (err: unknown) {
      showError(err instanceof Error ? err.message : '上传失败');
    }
  };

  const handleFileImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadError('');
    const ext = file.name.split('.').pop()?.toLowerCase();

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), UPLOAD_TIMEOUT);

    try {
      if (ext === 'pdf') {
        setUploadStatus(`正在上传并解析 ${file.name}...`);
        const result = await uploadKnowledgeFile(file);
        showResult(result.chunks);
      } else {
        setUploadStatus(`正在读取 ${file.name}...`);
        const text = await file.text();
        setUploadStatus(`正在分块 (${Math.ceil(text.length / 500)} 个片段)...`);
        const docName = file.name.replace(/\.[^.]+$/, '');
        const result = await uploadKnowledgeDoc(docName, text);
        showResult(result.chunks);
      }
      load();
    } catch (err: unknown) {
      const msg = err instanceof DOMException && err.name === 'AbortError'
        ? '上传超时，文件过大请拆分后重试'
        : err instanceof Error ? err.message : '上传失败，请重试';
      showError(msg);
    } finally {
      clearTimeout(timeout);
      e.target.value = '';
    }
  };

  const toggleExpand = async (docName: string) => {
    if (expanded.has(docName)) {
      setExpanded((prev) => { const n = new Set(prev); n.delete(docName); return n; });
      return;
    }
    setExpanded((prev) => { const n = new Set(prev); n.add(docName); return n; });
    if (!details[docName]) {
      const doc = await fetchKnowledgeDoc(docName);
      setDetails((prev) => ({ ...prev, [docName]: doc }));
    }
  };

  const handleEdit = async (docName: string) => {
    const doc = await fetchKnowledgeDoc(docName);
    if (doc) {
      setName(doc.original_name || doc.name);
      setContent(doc.content || '');
      setShowForm(true);
    }
  };

  const handleDelete = (docName: string) => {
    useConfirmStore.getState().requestConfirm({
      title: '删除文档',
      message: `确定要删除 "${docName}" 吗？此操作不可恢复。`,
      danger: true,
      onConfirm: async () => {
        try {
          await deleteKnowledgeDoc(docName);
          load();
        } catch (err: unknown) {
          const msg = err instanceof Error ? err.message : '删除文档失败';
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
        <h1 className="page-title">知识库</h1>
        <div className="page-header-right">
          <button className="btn" onClick={() => fileRef.current?.click()} disabled={uploading}>
            <Icon name="upload" size={14} /> {uploading ? '上传中...' : '导入文件'}
          </button>
          <input ref={fileRef} type="file" accept=".txt,.md,.json,.csv,.pdf" style={{ display: 'none' }} onChange={handleFileImport} />
          <button className="btn" onClick={() => setShowForm((v) => !v)} disabled={uploading}>
            <Icon name="plus" size={14} /> 新建
          </button>
        </div>
      </div>

      <div className="page-body">
        {(uploading || uploadStatus || uploadError) && (
          <div className={`upload-status${uploadError ? ' upload-error' : ''}`}>
            {uploading && <Icon name="spinner" size={14} className="section-spinner-icon" />}
            <span>{uploadError || uploadStatus}</span>
          </div>
        )}

        {loading && <SkeletonList count={4} />}

        {loadError && (
          <div className="page-empty">
            <p className="page-error">{loadError}</p>
            <button className="btn" onClick={load} style={{ marginTop: 12 }}>
              <Icon name="spinner" size={12} /> 重试
            </button>
          </div>
        )}

        {!loading && !loadError && docs.length === 0 && !showForm && (
          <EmptyState
            icon="file"
            title="暂无知识库文档"
            description={`点击"导入文件"上传 .txt/.md/.pdf 文件，或"新建"手动编写`}
          />
        )}

        {showForm && (
          <div className="card form-card">
            <div className="card-form-head">
              <span className="card-title">新建文档</span>
            </div>
            <div className="form-grid">
              <div className="form-field">
                <span>文档名称</span>
                <input type="text" value={name} placeholder="例如 product-manual"
                  className={fieldErrors.name ? 'field-invalid' : ''}
                  onChange={(e) => setName(e.target.value)}
                  onBlur={(e) => validateField('name', e.target.value)} />
                {fieldErrors.name && <span className="field-error">{fieldErrors.name}</span>}
              </div>
              <div className="form-field">
                <span>内容</span>
                <textarea value={content} rows={6}
                  className={fieldErrors.content ? 'field-invalid' : ''}
                  placeholder="粘贴或编写文档内容..."
                  onChange={(e) => setContent(e.target.value)}
                  onBlur={(e) => validateField('content', e.target.value)} />
                {fieldErrors.content && <span className="field-error">{fieldErrors.content}</span>}
              </div>
            </div>
            <div className="card-form-actions">
              <button className="btn btn-primary" onClick={handleUpload} disabled={uploading || !name.trim() || !content.trim()}>
                {uploading ? '保存中...' : '保存'}
              </button>
              <button className="btn" onClick={() => setShowForm(false)} disabled={uploading}>取消</button>
            </div>
          </div>
        )}

        <div className="expert-list">
          {docs.map((d) => {
            const isExpanded = expanded.has(d.name);
            const detail = details[d.name];
            return (
              <div key={d.name} className="expert-item">
                <div className="expert-item-header">
                  <button className="expert-item-toggle" onClick={() => toggleExpand(d.name)} aria-expanded={isExpanded}>
                    <div className="expert-item-info">
                      <span className="expert-item-name">{d.original_name || d.name}</span>
                    </div>
                    <div className="expert-item-right">
                      <span className="expert-item-meta">
                        {d.chunk_count} 个片段
                      </span>
                      <span className="connector-item-arrow">
                        {isExpanded ? '[-]' : '[+]'}
                      </span>
                    </div>
                  </button>
                  <div className="expert-item-actions">
                    <button className="expert-action-link" onClick={() => handleEdit(d.name)}>
                      [/] 编辑
                    </button>
                    <button className="expert-action-link expert-action-delete" onClick={() => handleDelete(d.name)}>
                      [x] 删除
                    </button>
                  </div>
                </div>
                {isExpanded && (
                  <div className="expert-item-detail">
                    {detail ? (
                      detail.chunks.map((c, i) => (
                        <div key={c.index} className="expert-detail-section">
                          <span className="expert-detail-label">{c.index}</span>
                          <pre className="expert-detail-prompt" style={{ maxHeight: 120 }}>
                            {c.text}{c.full_length > 200 ? '...' : ''}
                          </pre>
                        </div>
                      ))
                    ) : (
                      <span className="expert-detail-empty"><Loading text="加载中..." size="sm" /></span>
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
