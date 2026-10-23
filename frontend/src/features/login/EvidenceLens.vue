<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, useId } from 'vue'

const uid = useId().replace(/:/g, '')
const clipId = `evidence-clip-${uid}`
const shadowId = `evidence-shadow-${uid}`
const rimId = `evidence-rim-${uid}`
const svg = ref<SVGSVGElement | null>(null)
const position = ref({ x: 400, y: 204 })
const radius = 112
const active = ref(false)
const codeLines = [
  { n: 142, text: 'if (loginFailed) {', type: 'keyword' },
  { n: 143, text: '  audit.log({', type: 'plain' },
  { n: 144, text: "    action: 'login_failed',", type: 'highlight' },
  { n: 145, text: '    reason: error.code,', type: 'highlight' },
  { n: 146, text: '    requestId: request.id,', type: 'plain' },
  { n: 147, text: '    timestamp: Date.now()', type: 'plain' },
  { n: 148, text: '  });', type: 'plain' },
  { n: 149, text: '}', type: 'keyword' },
]
let destination = { ...position.value }
let frame = 0
let lastTime = 0
let reducedMotion: MediaQueryList | undefined
let nextEvidence = 0

function stopMotion() {
  cancelAnimationFrame(frame)
  frame = 0
  lastTime = 0
}

function animate(time: number) {
  const elapsed = lastTime ? Math.min(time - lastTime, 50) : 16
  lastTime = time
  const weight = 1 - Math.exp(-elapsed / 75)
  const dx = destination.x - position.value.x
  const dy = destination.y - position.value.y
  if (Math.abs(dx) + Math.abs(dy) < 0.15) {
    position.value = { ...destination }
    frame = 0
    lastTime = 0
    return
  }
  position.value = { x: position.value.x + dx * weight, y: position.value.y + dy * weight }
  frame = requestAnimationFrame(animate)
}

function moveTo(x: number, y: number) {
  const inset = radius + 8
  destination = { x: Math.max(inset, Math.min(640 - inset, x)), y: Math.max(inset, Math.min(420 - inset, y)) }
  if (reducedMotion?.matches || document.hidden) {
    stopMotion()
    position.value = { ...destination }
  } else if (!frame) {
    frame = requestAnimationFrame(animate)
  }
}

function trackPointer(event: PointerEvent) {
  // Touch interaction uses taps so vertical scrolling stays native.
  if (event.type === 'pointermove' && event.pointerType === 'touch') return
  const matrix = svg.value?.getScreenCTM()
  if (!matrix || !svg.value) return
  const point = svg.value.createSVGPoint()
  point.x = event.clientX
  point.y = event.clientY
  const local = point.matrixTransform(matrix.inverse())
  active.value = true
  moveTo(local.x, local.y)
}

function resetLens() {
  active.value = false
  moveTo(400, 204)
}

function leavePointer(event: PointerEvent) {
  if (event.pointerType !== 'touch') resetLens()
}

function handleKey(event: KeyboardEvent) {
  const offset: Record<string, [number, number]> = {
    ArrowLeft: [-32, 0], ArrowRight: [32, 0], ArrowUp: [0, -26], ArrowDown: [0, 26],
  }
  if (offset[event.key]) {
    event.preventDefault()
    active.value = true
    moveTo(destination.x + offset[event.key][0], destination.y + offset[event.key][1])
  } else if (event.key === 'Home' || event.key === 'Escape') {
    event.preventDefault()
    resetLens()
  }
}

function exploreNext() {
  nextEvidence = (nextEvidence + 1) % 3
  const locations = [{ x: 400, y: 204 }, { x: 163, y: 177 }, { x: 402, y: 265 }]
  const location = locations[nextEvidence]
  active.value = true
  moveTo(location.x, location.y)
}

function settleMotion() {
  stopMotion()
  position.value = { ...destination }
}

function onVisibilityChange() {
  if (document.hidden) settleMotion()
}

onMounted(() => {
  reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
  reducedMotion.addEventListener('change', settleMotion)
  document.addEventListener('visibilitychange', onVisibilityChange)
  if (!reducedMotion.matches && !document.hidden) {
    position.value = { x: 353, y: 190 }
    moveTo(400, 204)
  }
})

onBeforeUnmount(() => {
  stopMotion()
  reducedMotion?.removeEventListener('change', settleMotion)
  document.removeEventListener('visibilitychange', onVisibilityChange)
})
</script>

<template>
  <figure class="evidence-lens">
    <div class="lens-stage" :class="{ 'is-exploring': active }" tabindex="0" role="group" aria-label="交互示意：移动鼠标或使用方向键，通过透镜查看需求与示例代码的关联。手机上可点按探索。" @pointermove="trackPointer" @pointerdown="trackPointer" @pointerleave="leavePointer" @keydown="handleKey" @blur="resetLens">
      <svg ref="svg" class="lens-scene" viewBox="0 0 640 420" role="img" aria-labelledby="lens-scene-title" xmlns="http://www.w3.org/2000/svg">
        <title id="lens-scene-title">证据透镜：登录失败记录需求与示例审计代码之间的关联</title>
        <defs>
          <clipPath :id="clipId"><circle :cx="position.x" :cy="position.y" :r="radius - 4" /></clipPath>
          <filter :id="shadowId" x="-35%" y="-35%" width="170%" height="190%" color-interpolation-filters="sRGB"><feDropShadow dx="0" dy="10" stdDeviation="12" flood-color="#625c50" flood-opacity=".17" /></filter>
          <linearGradient :id="rimId" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fff" /><stop offset=".45" stop-color="#d2cabe" /><stop offset=".7" stop-color="var(--surface)" /><stop offset="1" stop-color="#bdb7aa" /></linearGradient>
        </defs>

        <!-- The quiet outer layer conveys structure; the lens reveals its meaning. -->
        <g class="ambient-graph" fill="none" stroke="var(--line)" stroke-width="1">
          <path d="M22 62H163L210 90H315M45 369H225L281 346H568M478 41H573V94H609M21 247H74M549 302H612V355" />
          <path d="M197 129C255 129 252 187 300 187M197 233C251 233 248 237 300 237M197 324C245 324 275 260 300 260M539 183H585L611 160M539 237H579L610 264" />
          <circle cx="163" cy="62" r="3" fill="#beb8ab" /><circle cx="210" cy="90" r="3" fill="#beb8ab" /><circle cx="573" cy="94" r="3" fill="#beb8ab" /><circle cx="612" cy="355" r="3" fill="#beb8ab" /><circle cx="281" cy="346" r="3" fill="#beb8ab" />
        </g>
        <g class="outer-requirements">
          <text x="28" y="82" class="scene-label">交付需求</text>
          <rect x="23" y="98" width="174" height="66" rx="8" /><text x="37" y="125">登录失败时</text><text x="37" y="146">记录具体原因</text>
          <rect x="23" y="201" width="174" height="66" rx="8" /><text x="37" y="228">每条日志保留</text><text x="37" y="249">请求追踪信息</text>
          <rect x="23" y="301" width="174" height="48" rx="8" /><text x="37" y="330">保留事件发生时间</text>
        </g>
        <g class="outer-code">
          <rect x="257" y="81" width="327" height="270" rx="10" fill="var(--surface-muted)" stroke="var(--line)" />
          <path d="M257 117H584" stroke="var(--line)" /><text x="278" y="105" class="scene-label">auth / login.ts</text>
          <g v-for="(line, index) in codeLines" :key="line.n" :transform="`translate(279 ${148 + index * 23})`" fill="#d9d4c9"><rect width="13" height="4" rx="2" /><rect :x="30 + (index > 0 && index < 7 ? 12 : 0)" :width="[118, 91, 204, 182, 194, 187, 37, 14][index]" height="5" rx="2" /></g>
        </g>

        <circle :cx="position.x" :cy="position.y" :r="radius" fill="var(--surface)" :filter="`url(#${shadowId})`" />
        <g :clip-path="`url(#${clipId})`">
          <rect width="640" height="420" fill="var(--surface)" />
          <text x="336" y="128" class="lens-heading">证据链 · 需求 → 代码</text>
          <g class="revealed-requirements">
            <text x="34" y="82" class="scene-label">交付需求</text>
            <rect x="23" y="98" width="174" height="66" rx="8" /><text x="37" y="125">登录失败时</text><text x="37" y="146">记录具体原因</text>
            <rect x="23" y="201" width="174" height="66" rx="8" /><text x="37" y="228">每条日志保留</text><text x="37" y="249">请求追踪信息</text>
            <rect x="23" y="301" width="174" height="48" rx="8" /><text x="37" y="330">保留事件发生时间</text>
          </g>
          <rect x="274" y="174" width="320" height="48" rx="5" fill="var(--brand-soft)" />
          <g class="evidence-links" fill="none" stroke="var(--brand)" stroke-width="1.5">
            <path d="M197 129C254 129 243 188 286 188M197 142C247 142 249 211 286 211M197 233C244 233 248 234 286 234M197 324C250 324 250 257 286 257" />
          </g>
          <g fill="var(--brand)"><circle cx="197" cy="129" r="3.5" /><circle cx="197" cy="233" r="3.5" /><circle cx="197" cy="324" r="3.5" /><circle cx="286" cy="188" r="3" /><circle cx="286" cy="211" r="3" /><circle cx="286" cy="234" r="3" /><circle cx="286" cy="257" r="3" /></g>
          <g v-for="(line, index) in codeLines" :key="line.n" class="revealed-code" :transform="`translate(292 ${143 + index * 23})`">
            <text class="line-number" text-anchor="end" y="0">{{ line.n }}</text><text x="22" y="0" :class="line.type" xml:space="preserve">{{ line.text }}</text>
          </g>
          <g class="citation-sample"><rect x="286" y="331" width="276" height="53" rx="8" /><path d="M303 348h6v7h-4v4h-3v-8Zm10 0h6v7h-4v4h-3v-8Z" fill="var(--brand)" /><text x="329" y="351">需求与实现位置关联</text><text x="329" y="369" class="citation-path">auth/login.ts : 144–147</text></g>
        </g>
        <g :transform="`translate(${position.x} ${position.y})`" fill="none" pointer-events="none">
          <circle :r="radius" :stroke="`url(#${rimId})`" stroke-width="5" />
          <circle :r="radius - 4" stroke="#ffffff" stroke-width="1.5" />
          <path :d="`M${-radius * .7} ${-radius * .71}A${radius - 1} ${radius - 1} 0 0 1 ${radius * .56} ${-radius * .82}`" stroke="white" stroke-width="2.5" stroke-linecap="round" />
        </g>
      </svg>
    </div>
    <figcaption class="lens-caption"><button type="button" @click="exploreNext">切换证据 <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M4 12h16m-6-6 6 6-6 6" /></svg></button></figcaption>
  </figure>
</template>

<style scoped>
.evidence-lens { margin: 16px -18px 0; }
.lens-stage { position: relative; overflow: hidden; border-radius: 12px; cursor: crosshair; touch-action: pan-y; }
.lens-stage:focus-visible { outline: 2px solid var(--brand); outline-offset: 2px; }
.lens-stage.is-exploring .evidence-links { stroke: var(--brand); }
.lens-scene { display: block; width: 100%; height: auto; overflow: visible; user-select: none; }
.scene-label { fill: var(--muted); font: 11px "Segoe UI", "Microsoft YaHei", sans-serif; }
.outer-requirements rect { fill: var(--surface-muted); stroke: var(--line); }
.outer-requirements text:not(.scene-label) { fill: var(--muted); font-size: 12px; }
.revealed-requirements rect { fill: var(--brand-soft); stroke: var(--brand-soft); }
.revealed-requirements text:not(.scene-label) { fill: var(--brand); font-size: 12px; }
.lens-heading { fill: var(--brand); font-size: 12px; font-weight: 600; letter-spacing: .025em; }
.revealed-code { font: 12px Consolas, "SFMono-Regular", monospace; }
.line-number { fill: var(--muted); font-size: 10px; }
.revealed-code .plain { fill: var(--ink); }
.revealed-code .keyword { fill: var(--brand); }
.revealed-code .highlight { fill: var(--brand); }
.citation-sample rect { fill: var(--brand-soft); stroke: var(--brand-soft); }
.citation-sample text { fill: var(--brand); font-size: 11px; }
.citation-sample .citation-path { fill: var(--muted); font: 10px Consolas, monospace; }
.lens-caption { display: flex; align-items: center; justify-content: flex-end; gap: 12px; padding: 6px 18px 0; font-size: 11px; line-height: 1.7; color: var(--muted); }
.lens-caption button { display: inline-flex; align-items: center; gap: 5px; min-height: 32px; padding: 4px 0 4px 8px; background: transparent; color: var(--brand); font: inherit; white-space: nowrap; border-radius: 4px; }
.lens-caption button:hover { color: var(--brand); background: var(--brand-soft); }
.lens-caption button:focus-visible { outline: 2px solid var(--brand); outline-offset: 3px; }
.lens-caption button svg { width: 15px; height: 15px; }
@media (max-width: 700px) {
  .evidence-lens { max-width: 520px; margin: 12px auto 0; }
  .lens-caption { padding: 4px 0 0; font-size: 10px; }
}
</style>
