export type MiniGameId = 'fishing' | 'catch' | 'tap';

export interface MiniGameResult {
  food_value: number;
  items: string[];
  reaction: string;
  bubble: string;
}

export interface MiniGameProps {
  uid: string;
  onDone: (result: MiniGameResult) => void;
  label?: string;
  onSwitchGame?: () => void;
}
