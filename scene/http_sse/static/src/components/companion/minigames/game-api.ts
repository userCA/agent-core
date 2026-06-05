import type { MiniGameId } from './types';

interface MinigameConfigResponse {
  game: MiniGameId;
  seed: number;
  signature: string;
  params: {
    rarity_bonus: number;
    max_duration_s: number;
    fish_table?: unknown[];
  };
}

interface FeedResponse {
  valid: boolean;
  reaction?: string;
  bubble?: string;
}

export async function fetchMinigameConfig(uid: string, game: MiniGameId): Promise<MinigameConfigResponse> {
  const res = await fetch(`/api/minigame/config?game=${encodeURIComponent(game)}`, {
    headers: { uid },
  });
  if (!res.ok) {
    throw new Error(`minigame config failed: ${res.status}`);
  }
  return res.json();
}

export async function submitMinigameResult(
  uid: string,
  game: MiniGameId,
  seed: number,
  signature: string,
  result: { food_value: number; items: string[] },
  actions: Array<{ t: number; type: string }>
): Promise<FeedResponse> {
  const res = await fetch('/api/minigame/feed', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      uid,
    },
    body: JSON.stringify({
      uid,
      game,
      seed,
      signature,
      actions,
      result,
    }),
  });
  if (!res.ok) {
    throw new Error(`minigame feed failed: ${res.status}`);
  }
  return res.json();
}

