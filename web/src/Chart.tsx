import { useEffect, useRef, useState, type ReactNode } from 'react'
import type { Figure } from './api'

// core/'s own Plotly charts, drawn in the browser. plotly.js is big, so it's
// only downloaded the first time a chart is opened.
// The look follows Emma's style_fig() from the Streamlit app: light, compact,
// legend underneath, no toolbar.

type Plotly = {
  react: (el: HTMLElement, data: unknown[], layout: object, config: object) => Promise<unknown>
  purge: (el: HTMLElement) => void
}
let plotly: Promise<Plotly> | null = null
const loadPlotly = () => (plotly ??= import('plotly.js-dist-min').then((m) => (m.default ?? m) as Plotly))

export function PlotlyChart({ figure, height = 300 }: { figure: Figure; height?: number }) {
  const box = useRef<HTMLDivElement>(null)
  const [problem, setProblem] = useState('')

  useEffect(() => {
    const el = box.current
    if (!el) return
    let live = true
    loadPlotly().then((Plotly) => {
      if (!live) return
      const layout = {
        ...figure.layout,
        paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
        height, autosize: true,
        margin: { l: 8, r: 8, t: 40, b: 8, pad: 0 },
        font: { family: "'DM Sans', sans-serif", size: 11, color: '#3b4760' },
        legend: { orientation: 'h', y: -0.2 },
      }
      return Plotly.react(el, figure.data, layout, { displayModeBar: false, responsive: true })
    }).catch(() => live && setProblem('This chart couldn’t be drawn.'))
    return () => {
      live = false
      loadPlotly().then((Plotly) => Plotly.purge(el)).catch(() => {})
    }
  }, [figure, height])

  return problem ? <p className="muted-copy">{problem}</p> : <div ref={box} className="plotly-box" style={{ minHeight: height }} />
}

/**
 * Charts tucked into a section that opens on a tap, like the Streamlit expanders.
 * They're drawn only once it's open, so a closed section costs nothing.
 */
export function ChartGroup({ title, figures, open: startOpen = false, children }: {
  title: string; figures: [Figure | undefined, number][]; open?: boolean; children?: ReactNode
}) {
  const [open, setOpen] = useState(startOpen)
  const ready = figures.filter((f): f is [Figure, number] => !!f[0])
  if (!ready.length) return null
  return (
    <details className="chart-group" open={startOpen} onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary>{title}</summary>
      {children}
      {open && ready.map(([figure, height], i) => <PlotlyChart key={i} figure={figure} height={height} />)}
    </details>
  )
}
