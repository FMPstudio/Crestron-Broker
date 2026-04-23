<script lang="ts">
  import type { EdgePath } from '../types';

  export let paths: EdgePath[] = [];
  export let overlayEl: SVGSVGElement | undefined;
</script>

<svg
  class="connection-layer"
  viewBox="0 0 1000 1000"
  preserveAspectRatio="none"
  aria-hidden="true"
  bind:this={overlayEl}
>
  <defs>
    <filter id="lineGlow" x="-25%" y="-25%" width="150%" height="150%">
      <feGaussianBlur stdDeviation="3" result="blur" />
      <feMerge>
        <feMergeNode in="blur" />
        <feMergeNode in="SourceGraphic" />
      </feMerge>
    </filter>
    <linearGradient id="lineGradient" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#58f3a3" stop-opacity="0.6" />
      <stop offset="100%" stop-color="#7df8bd" stop-opacity="0.95" />
    </linearGradient>
  </defs>
  {#each paths as path (path.id)}
    <path d={path.d} class="route-path" />
  {/each}
</svg>
