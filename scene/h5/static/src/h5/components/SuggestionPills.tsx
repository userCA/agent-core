import React, { useCallback } from 'react';
import {
  Search, GitCompare, Play, Wand2, Bug, FileText,
} from 'lucide-react';
import './SuggestionPills.css';

interface Props {
  onPick: (text: string) => void;
}

const PILLS = [
  { icon: <Search size={14} />,     label: '搜索认证', text: '搜索认证相关代码' },
  { icon: <GitCompare size={14} />, label: '代码对比', text: '查看 git diff' },
  { icon: <Play size={14} />,       label: '运行测试', text: '运行测试' },
  { icon: <Wand2 size={14} />,      label: '重构',     text: '重构代码' },
  { icon: <Bug size={14} />,        label: '调试',     text: '调试错误' },
  { icon: <FileText size={14} />,   label: '文档',     text: '写文档' },
];

export default function SuggestionPills({ onPick }: Props) {
  const handleClick = useCallback(
    (text: string) => { onPick(text); },
    [onPick],
  );

  return (
    <div className="suggestion-pills">
      <div className="pills-scroll">
        {PILLS.map((p) => (
          <button
            key={p.label}
            className="pill-btn"
            onClick={() => handleClick(p.text)}
          >
            {p.icon}
            <span>{p.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
