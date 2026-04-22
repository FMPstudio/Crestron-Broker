<script lang="ts">
  export let deviceId: string;
  export let ip: string;
  export let active = false;
</script>

<article class:active class="node-card source-card" data-device-id={deviceId}>
  <span class="status-dot" aria-hidden="true"></span>
  <div class="content">
    <p class="title">Source {deviceId}</p>
    <p class="meta">{ip}</p>
  </div>
</article>
