import { invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';
import { writable } from 'svelte/store';
import type { RoutingSnapshot } from '../types';

const initialState: RoutingSnapshot = {
  sources: [],
  inputs: [1, 2, 3, 4].map((inputId) => ({
    inputId,
    multicastIp: '—',
    active: false,
    connectedDeviceId: null
  })),
  routes: [],
  lastUpdated: new Date().toISOString(),
  errors: ['Waiting for backend data…']
};

function createRoutingStore() {
  const { subscribe, set } = writable<RoutingSnapshot>(initialState);
  let unlisten: UnlistenFn | null = null;

  const refresh = async () => {
    try {
      const snapshot = await invoke<RoutingSnapshot>('get_routing_snapshot');
      set(snapshot);
    } catch (error) {
      set({
        ...initialState,
        errors: [`Failed to load snapshot: ${String(error)}`],
        lastUpdated: new Date().toISOString()
      });
    }
  };

  const start = async () => {
    await refresh();
    unlisten = await listen<RoutingSnapshot>('routing_snapshot_updated', (event) => {
      set(event.payload);
    });
  };

  const stop = async () => {
    if (unlisten) {
      unlisten();
      unlisten = null;
    }
  };

  return { subscribe, start, stop, refresh };
}

export const routingStore = createRoutingStore();
