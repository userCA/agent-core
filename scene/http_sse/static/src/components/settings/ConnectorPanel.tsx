import React, { useEffect, useState } from 'react';
import { fetchConnectors, type ConnectorInfo } from '../../api/client';
import Icon from '../shared/Icon';
import './ConnectorPanel.css';

interface Props {
  onClose: () => void;
}

export default function ConnectorPanel({ onClose }: Props) {
  const [connectors, setConnectors] = useState<ConnectorInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    fetchConnectors()
      .then((data) => {
        setConnectors(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  const toggleExpand = (name: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  return (
    <div className="connector-panel-overlay" onClick={onClose} role="dialog" aria-modal="true" aria-label="连接器管理">
      <div className="connector-panel" onClick={(e) => e.stopPropagation()}>
        <div className="connector-panel-header">
          <h2 className="connector-panel-title">
            <Icon name="tool" size={14} /> 连接器
          </h2>
          <button className="connector-panel-close" onClick={onClose} aria-label="关闭">
            <Icon name="cancel" size={14} />
          </button>
        </div>

        <div className="connector-panel-body">
          {loading && <div className="connector-empty">加载中...</div>}
          {error && <div className="connector-empty connector-error">{error}</div>}
          {!loading && !error && connectors.length === 0 && (
            <div className="connector-empty">暂无连接器</div>
          )}

          {connectors.map((c) => {
            const isExpanded = expanded.has(c.name);
            const isConnected = c.status === 'connected';
            return (
              <div key={c.name} className={`connector-card${isConnected ? ' connected' : ' error'}`}>
                <button
                  className="connector-card-header"
                  onClick={() => toggleExpand(c.name)}
                  aria-expanded={isExpanded}
                >
                  <span className="connector-name">
                    <span className={`connector-status-dot${isConnected ? ' ok' : ' err'}`} />
                    {c.name}
                  </span>
                  <span className="connector-meta">
                    <span className="connector-transport">{c.transport}</span>
                    <span className="connector-tool-count">{c.tools.length} 工具</span>
                    <span className="connector-arrow">
                      {isExpanded ? <Icon name="chevron-up" size={12} /> : <Icon name="chevron-down" size={12} />}
                    </span>
                  </span>
                </button>
                {isExpanded && (
                  <div className="connector-tools">
                    {c.tools.map((t) => (
                      <span key={t} className="connector-tool-tag">
                        {t}
                      </span>
                    ))}
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
