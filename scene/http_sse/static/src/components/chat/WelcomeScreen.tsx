import React from 'react';
import './WelcomeScreen.css';

const EXAMPLES = [
  { label: '[+] 打个招呼', text: '你好，请介绍一下你自己' },
  { label: '[+] 列出文件', text: '当前目录有哪些文件？' },
  { label: '[+] 写代码', text: '帮我写一段 Python 快速排序' },
];

interface Props {
  onSelect?: (text: string) => void;
}

export default function WelcomeScreen({ onSelect }: Props) {
  return (
    <div className="welcome">
      <pre className="welcome-logo">{`
              ██            ██
             ████          ████
            ██████        ██████
           ██████████████████████
          ████    ████████    ████
          ████                ████
          ████  ██  ██  ██  ████
          ████    ██████    ████
           ██████████████████████
             ████          ████
              ████████████████
                ████    ████
                 ██      ██
      `}</pre>
      <h1 className="welcome-title">咪兔</h1>
      <p className="welcome-subtitle">你的 AI 伙伴 — 随时为你提供帮助</p>
      <div className="welcome-examples">
        {EXAMPLES.map((ex) => (
          <button
            key={ex.label}
            className="example-chip"
            onClick={() => onSelect?.(ex.text)}
          >
            {ex.label}
          </button>
        ))}
      </div>
    </div>
  );
}
