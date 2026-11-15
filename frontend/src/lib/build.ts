/**
 * The build identifier: the SHA-256 of the build record
 * (/data/build_inputs.json) that the audit (/audit.json) checked. The build
 * record lists the checksum of every source file read and every data file
 * published, so the identifier names one exact set of published data.
 *
 * Also the audit's checks (name, status and the text of any error or
 * warning) and the rows of its interval-calibration check, so pages can
 * show what the audit found rather than a fixed list.
 */

import { useEffect, useState } from 'react'

export interface AuditCheck {
  name: string
  status: string
  errors: string[]
  warnings: string[]
}

// One row of the calibration check: coverage of the intervals for one rate
// code, period and band of yearly counts (`units` institutions)
export interface CalibrationRow {
  code: string
  period: string
  band: string
  units: number
  observed: number
  expected: number
  tested: boolean
  ok: boolean
}

export interface BuildInfo {
  /** Full SHA-256 of /data/build_inputs.json */
  sha256: string
  /** First 12 characters, for display */
  id: string
  /** When the audit ran (ISO-like timestamp from audit.json) */
  auditedAt: string | null
  /** Audit result, e.g. "PASS" */
  status: string | null
  /** Every check of the audit, in its order */
  checks: AuditCheck[]
  /** The calibration check's rows (empty when the audit has none) */
  calibration: CalibrationRow[]
}

let cache: Promise<BuildInfo | null> | null = null
// The build info once known (seeded by the prerenderer, or fetched), so a
// page drawn after that starts with it
let known: BuildInfo | null = null

const strings = (v: unknown): string[] =>
  Array.isArray(v) ? v.filter((s): s is string => typeof s === 'string') : typeof v === 'string' ? [v] : []

/** The build info from /audit.json, read at build time by the prerenderer (src/entry-server.tsx). */
export function buildInfoFromAudit(a: unknown): BuildInfo | null {
  const audit = a as {
    audited_build?: { site_record_sha256?: unknown }
    generated_at?: unknown
    overall_status?: unknown
    checks?: unknown
  } | null
  const sha = audit?.audited_build?.site_record_sha256
  if (typeof sha !== 'string' || sha.length < 12) return null
  const rawChecks = Array.isArray(audit?.checks) ? (audit.checks as Record<string, unknown>[]) : []
  const checks: AuditCheck[] = rawChecks.map((c) => ({
    name: typeof c.name === 'string' ? c.name : '',
    status: typeof c.status === 'string' ? c.status : '',
    errors: strings(c.errors),
    warnings: strings(c.warnings),
  }))
  const calibrationCheck = rawChecks.find((c) => c.name === 'Interval Calibration')
  const rows = (calibrationCheck?.details as { rows?: unknown } | undefined)?.rows
  const calibration: CalibrationRow[] = Array.isArray(rows)
    ? (rows as Record<string, unknown>[])
        .filter((r) => typeof r.code === 'string' && typeof r.observed === 'number' && typeof r.expected === 'number')
        .map((r) => ({
          code: r.code as string,
          period: String(r.period ?? ''),
          band: String(r.band ?? ''),
          units: typeof r.units === 'number' ? r.units : 0,
          observed: r.observed as number,
          expected: r.expected as number,
          tested: r.tested === true,
          ok: r.ok === true,
        }))
    : []
  return {
    sha256: sha,
    id: sha.slice(0, 12),
    auditedAt: typeof audit?.generated_at === 'string' ? audit.generated_at : null,
    status: typeof audit?.overall_status === 'string' ? audit.overall_status : null,
    checks,
    calibration,
  }
}

/** Used by the prerenderer, so the static HTML names the build. */
export function seedBuildInfo(info: BuildInfo | null): void {
  known = info
  cache = Promise.resolve(info)
}

export function fetchBuildInfo(): Promise<BuildInfo | null> {
  if (!cache) {
    cache = fetch('/audit.json')
      .then((r) => (r.ok ? r.json() : null))
      .then(buildInfoFromAudit)
      .catch(() => null)
      .then((info) => {
        known = info
        return info
      })
  }
  return cache
}

export function useBuildInfo(): BuildInfo | null {
  const [info, setInfo] = useState<BuildInfo | null>(known)
  useEffect(() => {
    let live = true
    fetchBuildInfo().then((b) => {
      if (live) setInfo(b)
    })
    return () => {
      live = false
    }
  }, [])
  return info
}
