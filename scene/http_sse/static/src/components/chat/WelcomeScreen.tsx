import React, { useState, useEffect } from 'react';
import Icon from '../shared/Icon';
import './WelcomeScreen.css';

interface ScenePrompt {
  label: string;
  text: string;
  icon: string;
}

interface SceneCategory {
  id: string;
  label: string;
  icon: string;
  prompts: ScenePrompt[];
}

const SCENES: SceneCategory[] = [
  {
    id: 'code',
    label: '代码开发',
    icon: 'code',
    prompts: [
      { label: '写 Python', text: '帮我写一段 Python 快速排序代码，并解释原理', icon: 'code' },
      { label: '写 React', text: '帮我写一个 React 函数组件，包含 useState 和 useEffect 的示例', icon: 'code' },
      { label: 'Debug', text: '请帮我分析这段代码的问题并给出修复方案', icon: 'bug' },
      { label: 'Code Review', text: '请对以下代码进行审查，指出潜在问题和改进建议', icon: 'search' },
    ],
  },
  {
    id: 'office',
    label: '日常办公',
    icon: 'briefcase',
    prompts: [
      { label: '写邮件', text: '帮我写一封正式的商务邮件，主题为项目进度汇报', icon: 'mail' },
      { label: '写文档', text: '帮我写一份产品需求文档的模板', icon: 'file' },
      { label: '会议纪要', text: '请将以下内容整理成结构化的会议纪要', icon: 'clipboard' },
      { label: '翻译', text: '请将以下内容翻译成英文，保持专业语气', icon: 'globe' },
    ],
  },
  {
    id: 'creative',
    label: '设计创意',
    icon: 'palette',
    prompts: [
      { label: '生成图片', text: '请帮我生成一张展示未来城市景观的图片', icon: 'image' },
      { label: '写文案', text: '帮我写一段有吸引力的产品推广文案', icon: 'pen' },
      { label: '头脑风暴', text: '围绕"智能家居"主题进行头脑风暴，列出10个创新点', icon: 'lightbulb' },
      { label: '命名建议', text: '为我的新产品起一个简洁有记忆点的名字', icon: 'tag' },
    ],
  },
  {
    id: 'research',
    label: '深度研究',
    icon: 'search',
    prompts: [
      { label: '搜索资料', text: '请搜索并总结关于人工智能最新进展的资料', icon: 'search' },
      { label: '数据分析', text: '请分析以下数据并给出可视化建议', icon: 'chart' },
      { label: '文献综述', text: '请帮我撰写一段关于机器学习的文献综述', icon: 'book' },
      { label: '技术调研', text: '对比分析 React 和 Vue 的优缺点', icon: 'scale' },
    ],
  },
];

interface Props {
  onSelect?: (text: string) => void;
}

export default function WelcomeScreen({ onSelect }: Props) {
  const [activeScene, setActiveScene] = useState<string>('code');
  const [mounted, setMounted] = useState(false);
  const scene = SCENES.find((s) => s.id === activeScene) ?? SCENES[0];

  useEffect(() => {
    setMounted(true);
  }, []);

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

      {/* Scene tabs */}
      <div className="scene-tabs">
        {SCENES.map((s) => (
          <button
            key={s.id}
            className={`scene-tab${activeScene === s.id ? ' active' : ''}`}
            onClick={() => setActiveScene(s.id)}
            aria-pressed={activeScene === s.id}
          >
            <Icon name={s.icon} size={14} />
            {s.label}
          </button>
        ))}
      </div>

      {/* Prompt grid for active scene */}
      <div className="prompt-grid">
        {scene.prompts.map((p, idx) => (
          <button
            key={`${scene.id}-${p.label}`}
            className={`prompt-card${mounted ? ' animated' : ''}`}
            onClick={() => onSelect?.(p.text)}
            style={{ animationDelay: `${idx * 0.08}s` }}
          >
            <span className="prompt-icon">
              <Icon name={p.icon} size={16} />
            </span>
            <span className="prompt-label">{p.label}</span>
          </button>
        ))}
      </div>

    </div>
  );
}
