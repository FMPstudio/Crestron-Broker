<script lang="ts">
  export let inputId: number;
  export let multicastIp: string;
  export let active = false;
</script>

<article class:active class="node-card input-card" data-input-id={inputId}>
  <span class="status-dot" aria-hidden="true"></span>
  <div class="content">
    <p class="title">Input {inputId}</p>
    <p class="meta">{multicastIp}</p>
  </div>
</article>
