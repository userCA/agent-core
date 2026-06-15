import React from 'react';
import type { LucideProps } from 'lucide-react';
import {
  AlertTriangle,
  BarChart,
  BookOpen,
  Brain,
  Briefcase,
  Bug,
  Calendar,
  Cat,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Circle,
  Clipboard,
  Clock,
  Code,
  Eye,
  FileText,
  Globe,
  Heart,
  Image,
  Key,
  Lightbulb,
  LineChart,
  Loader2,
  Mail,
  Menu,
  MessageSquare,
  Mic,
  Minus,
  Moon,
  Palette,
  PanelLeft,
  PanelRight,
  PenLine,
  Play,
  Plus,
  Scale,
  Search,
  Send,
  Settings,
  Sparkles,
  Sun,
  Tag,
  Trash2,
  Upload,
  User,
  Wrench,
  X,
} from 'lucide-react';

type IconName =
  | 'think'
  | 'tool'
  | 'check'
  | 'alert'
  | 'plus'
  | 'minus'
  | 'chevron-down'
  | 'chevron-up'
  | 'chevron-left'
  | 'chevron-right'
  | 'spinner'
  | 'running'
  | 'ready'
  | 'cancel'
  | 'key'
  | 'recording'
  | 'send'
  | 'upload'
  | 'panel-left'
  | 'panel-right'
  | 'message'
  | 'code'
  | 'briefcase'
  | 'palette'
  | 'search'
  | 'bug'
  | 'mail'
  | 'file'
  | 'clipboard'
  | 'globe'
  | 'image'
  | 'pen'
  | 'lightbulb'
  | 'tag'
  | 'chart'
  | 'book'
  | 'scale'
  | 'sun'
  | 'moon'
  | 'clock'
  | 'trash'
  | 'settings'
  | 'menu'
  | 'user'
  | 'close'
  | 'x'
  | 'cat'
  | 'heart'
  | 'bar-chart'
  | 'sparkles'
  | 'eye'
  | 'calendar';

export const ICON_SIZES = {
  sm: 12,
  md: 16,
  lg: 20,
} as const;

interface Props {
  name: IconName | string;
  size?: number;
  className?: string;
  style?: React.CSSProperties;
  'aria-label'?: string;
}

const ICON_MAP: Record<string, React.ComponentType<LucideProps>> = {
  think: Brain,
  tool: Wrench,
  check: Check,
  alert: AlertTriangle,
  plus: Plus,
  minus: Minus,
  'chevron-down': ChevronDown,
  'chevron-up': ChevronUp,
  'chevron-left': ChevronLeft,
  'chevron-right': ChevronRight,
  spinner: Loader2,
  running: Play,
  ready: Circle,
  cancel: X,
  key: Key,
  recording: Mic,
  send: Send,
  upload: Upload,
  'panel-left': PanelLeft,
  'panel-right': PanelRight,
  message: MessageSquare,
  code: Code,
  briefcase: Briefcase,
  palette: Palette,
  search: Search,
  bug: Bug,
  mail: Mail,
  file: FileText,
  clipboard: Clipboard,
  globe: Globe,
  image: Image,
  pen: PenLine,
  lightbulb: Lightbulb,
  tag: Tag,
  chart: LineChart,
  book: BookOpen,
  scale: Scale,
  sun: Sun,
  moon: Moon,
  clock: Clock,
  trash: Trash2,
  settings: Settings,
  menu: Menu,
  user: User,
  close: X,
  x: X,
  cat: Cat,
  heart: Heart,
  'bar-chart': BarChart,
  sparkles: Sparkles,
  eye: Eye,
  calendar: Calendar,
};

export default function Icon({
  name,
  size = 16,
  className = '',
  style,
  'aria-label': ariaLabel,
}: Props) {
  const LucideIcon = ICON_MAP[name];
  if (!LucideIcon) {
    if (import.meta.env.DEV) {
      // eslint-disable-next-line no-console
      console.warn(`[Icon] Unknown icon name: ${name}`);
    }
    return (
      <span
        className={className}
        style={{ ...style, width: size, height: size, display: 'inline-block' }}
        aria-label={ariaLabel}
        aria-hidden={ariaLabel ? undefined : 'true'}
      />
    );
  }

  const isSpinner = name === 'spinner';
  return (
    <LucideIcon
      size={size}
      className={`${className}${isSpinner ? ' lucide-spin' : ''}`}
      style={style}
      aria-hidden={ariaLabel ? undefined : 'true'}
      aria-label={ariaLabel}
    />
  );
}
