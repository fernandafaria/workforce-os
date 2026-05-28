import { create } from 'zustand';

interface FreeTierState {
  queryCount: number;
  maxQueries: number;
  increment: () => void;
  canQuery: () => boolean;
  remaining: () => number;
  reset: () => void;
}

const FREE_TIER_LIMIT = 3;

export const useFreeTier = create<FreeTierState>((set, get) => ({
  queryCount: parseInt(localStorage.getItem('wf_queryCount') || '0', 10),
  maxQueries: FREE_TIER_LIMIT,

  increment: () => {
    const next = get().queryCount + 1;
    localStorage.setItem('wf_queryCount', String(next));
    set({ queryCount: next });
  },

  canQuery: () => get().queryCount < FREE_TIER_LIMIT,

  remaining: () => Math.max(0, FREE_TIER_LIMIT - get().queryCount),

  reset: () => {
    localStorage.removeItem('wf_queryCount');
    set({ queryCount: 0 });
  },
}));
