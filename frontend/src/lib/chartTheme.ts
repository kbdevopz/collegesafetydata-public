/**
 * Chart colours for each theme, from the site's tokens (src/index.css).
 * Series colours are a colour-blind-safe set (after Okabe and Ito), each at
 * least 4.5:1 against the chart background, since legends are set in them;
 * bars are at least 3:1. Lines also differ by dash, so no
 * series is told apart by colour alone. Single-series charts are neutral,
 * with the accent only for the selected item.
 */
import { useTheme } from '../hooks/useTheme'

export interface ChartTheme {
  grid: string // gridlines and axis lines
  text: string // tick labels, legends
  tooltipBg: string
  tooltipBorder: string
  tooltipText: string
  bar: string // the bars of a single series
  selected: string // the selected bar or item
  band: string // shading of years with a comparability note (used at low opacity)
  series: string[] // categorical series, in order
}

const LIGHT: ChartTheme = {
  grid: '#E1E4E8',
  text: '#5C636D',
  tooltipBg: '#FFFFFF',
  tooltipBorder: '#C9CED4',
  tooltipText: '#3D434B',
  bar: '#848C96',
  selected: '#1D5A96',
  band: '#16191D',
  series: ['#1D5A96', '#C2500B', '#0B7E61', '#AE437D', '#9A6A00'],
}

const DARK: ChartTheme = {
  grid: '#2C3137',
  text: '#9CA3AD',
  tooltipBg: '#181B1F',
  tooltipBorder: '#3D434B',
  tooltipText: '#C3C8CF',
  bar: '#6F7782',
  selected: '#8CB8E6',
  band: '#E9EBEE',
  series: ['#7FB2E6', '#F08D50', '#3FC3A0', '#E690C3', '#E2B54E'],
}

// Dash patterns for line series, in the same order as the colours
export const SERIES_DASHES: (string | undefined)[] = [undefined, '7 4', '2 3', '10 3 2 3', '4 2']

export function chartTheme(dark: boolean): ChartTheme {
  return dark ? DARK : LIGHT
}

export function useChartTheme(): ChartTheme {
  const { resolvedTheme } = useTheme()
  return chartTheme(resolvedTheme === 'dark')
}

/** Recharts tooltip styling for a theme */
export function tooltipProps(t: ChartTheme) {
  return {
    contentStyle: {
      backgroundColor: t.tooltipBg,
      border: `1px solid ${t.tooltipBorder}`,
      borderRadius: '4px',
      fontSize: '13px',
      boxShadow: 'none',
    },
    labelStyle: { color: t.tooltipText, fontWeight: 600 },
    itemStyle: { color: t.tooltipText },
  }
}

/** The hover cursor of a bar chart (a light band) and of a line chart (a rule) */
export const barCursor = (t: ChartTheme) => ({ fill: t.band, fillOpacity: 0.06 })
export const lineCursor = (t: ChartTheme) => ({ stroke: t.text, strokeWidth: 1, strokeDasharray: '3 3' })
