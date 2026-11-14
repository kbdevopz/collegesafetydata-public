/**
 * The build identifier: the SHA-256 of the build record
 * (/data/build_inputs.json) that the audit (/audit.json) checked. The build
 * record lists the checksum of every source file read and every data file
 * published, so the identifier names one exact set of published data.
 */

import { useEffect, useState } from 'react'

export interface BuildInfo {
  /** Full SHA-256 of /data/build_inputs.json */
  sha256: string
  /** First 12 characters, for display */
  id: string
  /** When the audit ran (ISO-like timestamp from audit.json) */
  auditedAt: string | null
  /** Audit result, e.g. "PASS" */
  status: string | null
}

let cache: Promise<BuildInfo | null> | null = null
// The build info once known (seeded by the prerenderer, or fetched), so a
// page drawn after that starts with it
let known: BuildInfo | null = null

/** The build info from /audit.json, read at build time by the prerenderer (src/entry-server.tsx). */
export function buildInfoFromAudit(a: unknown): BuildInfo | null {
  const audit = a as { audited_build?: { site_record_sha256?: unknown }; generated_at?: unknown; overall_status?: unknown } | null
  const sha = audit?.audited_build?.site_record_sha256
  if (typeof sha !== 'string' || sha.length < 12) return null
  return {
    sha256: sha,
    id: sha.slice(0, 12),
    auditedAt: typeof audit?.generated_at === 'string' ? audit.generated_at : null,
    status: typeof audit?.overall_status === 'string' ? audit.overall_status : null,
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
