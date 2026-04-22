<script lang="ts">
  import { onDestroy, onMount, tick } from 'svelte';
  import ConnectionCanvas, { type EdgePath } from './lib/components/ConnectionCanvas.svelte';
  import InputCard from './lib/components/InputCard.svelte';
  import SourceCard from './lib/components/SourceCard.svelte';
  import { routingStore } from './lib/stores/routingStore';
  import type { RoutingSnapshot } from './lib/types';

  let snapshot: RoutingSnapshot = {
    sources: [],
    inputs: [],
    routes: [],
    lastUpdated: new Date().toISOString(),
    errors: []
  };

  let layoutRoot: HTMLDivElement;
  let edgePaths: EdgePath[] = [];

  const unsubscribe = routingStore.subscribe(async (value) => {
    snapshot = value;
    await tick();
    computePaths();
  });

  const computePaths = () => {
    if (!layoutRoot) return;

    const bounds = layoutRoot.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return;

    edgePaths = snapshot.routes
      .map((route) => {
        const sourceEl = layoutRoot.querySelector(`[data-device-id="${route.deviceId}"]`) as HTMLElement | null;
        const inputEl = layoutRoot.querySelector(`[data-input-id="${route.inputId}"]`) as HTMLElement | null;

        if (!sourceEl || !inputEl) {
          return null;
        }

        const source = sourceEl.getBoundingClientRect();
        const input = inputEl.getBoundingClientRect();

        const startX = ((source.right - bounds.left) / bounds.width) * 1000;
        const startY = ((source.top + source.height / 2 - bounds.top) / bounds.height) * 1000;
        const endX = ((input.left - bounds.left) / bounds.width) * 1000;
        const endY = ((input.top + input.height / 2 - bounds.top) / bounds.height) * 1000;

        const horizontalDelta = Math.max(80, (endX - startX) * 0.55);
        const d = `M ${startX} ${startY} C ${startX + horizontalDelta} ${startY}, ${endX - horizontalDelta} ${endY}, ${endX} ${endY}`;

        return {
          id: `${route.deviceId}-${route.inputId}`,
          d
        };
      })
      .filter((path): path is EdgePath => path !== null);
  };

  const formatUpdatedTime = (iso: string) => {
    const parsed = new Date(iso);
    if (Number.isNaN(parsed.getTime())) return 'Unknown update time';
    return parsed.toLocaleString();
  };

  onMount(async () => {
    await routingStore.start();
    const observer = new ResizeObserver(() => computePaths());
    observer.observe(layoutRoot);
    window.addEventListener('resize', computePaths);

    return () => {
      observer.disconnect();
      window.removeEventListener('resize', computePaths);
    };
  });

  onDestroy(async () => {
    unsubscribe();
    await routingStore.stop();
  });
</script>

<main>
  <header>
    <h1>Crestron / Matrox Routing Monitor</h1>
    <p>Visualization only · no routing controls</p>
  </header>

  {#if snapshot.errors.length > 0}
    <section class="warning-panel">
      <h2>Data warnings</h2>
      <ul>
        {#each snapshot.errors as err}
          <li>{err}</li>
        {/each}
      </ul>
    </section>
  {/if}

  <section class="layout" bind:this={layoutRoot}>
    <div class="column">
      <h2>Sources</h2>
      <div class="stack">
        {#each snapshot.sources as source (source.deviceId)}
          <SourceCard deviceId={source.deviceId} ip={source.ip} active={source.active} />
        {/each}
      </div>
    </div>

    <ConnectionCanvas paths={edgePaths} />

    <div class="column">
      <h2>Inputs</h2>
      <div class="stack">
        {#each snapshot.inputs as input (input.inputId)}
          <InputCard inputId={input.inputId} multicastIp={input.multicastIp} active={input.active} />
        {/each}
      </div>
    </div>
  </section>

  <footer>
    Last update: {formatUpdatedTime(snapshot.lastUpdated)}
  </footer>
</main>
