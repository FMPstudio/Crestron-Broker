import { invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';
import { get, writable } from 'svelte/store';
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
    console.info('[routingStore] refresh() started');
    try {
      console.info('[routingStore] invoking get_routing_snapshot');
      const snapshot = await invoke<RoutingSnapshot>('get_routing_snapshot');
      set(snapshot);
      console.info('[routingStore] refresh() succeeded', {
        sources: snapshot.sources.length,
        inputs: snapshot.inputs.length,
        routes: snapshot.routes.length,
        errors: snapshot.errors.length
      });
    } catch (error) {
      console.error('[routingStore] refresh() failed', error);
      set({
        ...initialState,
        errors: [`Failed to load snapshot: ${String(error)}`],
        lastUpdated: new Date().toISOString()
      });
    }
  };

  const start = async () => {
    console.info('[routingStore] start() called');

    if (unlisten) {
      unlisten();
      unlisten = null;
      console.info('[routingStore] cleared existing listener');
    }

    set({
      ...initialState,
      lastUpdated: new Date().toISOString(),
      errors: ['Loading fresh snapshot…']
    });

    const refreshPromise = refresh();

    void (async () => {
      console.info('[routingStore] registering listener: routing_snapshot_updated');
      try {
        unlisten = await listen<RoutingSnapshot>('routing_snapshot_updated', (event) => {
          console.info('[routingStore] update event received', {
            routes: event.payload.routes.length,
            errors: event.payload.errors.length
          });
          set(event.payload);
        });
        console.info('[routingStore] listener registered successfully');
      } catch (error) {
        console.error('[routingStore] listener registration failed', error);
        const current = get({ subscribe });
        set({
          ...current,
          errors: [...current.errors, `Live updates unavailable: ${String(error)}`],
          lastUpdated: current.lastUpdated || new Date().toISOString()
        });
      }
    })();

    await refreshPromise;
  };

  const stop = async () => {
    console.info('[routingStore] stop() called');
    if (unlisten) {
      unlisten();
      unlisten = null;
      console.info('[routingStore] listener removed');
    }
  };

  return { subscribe, start, stop, refresh };
}

export const routingStore = createRoutingStore();
