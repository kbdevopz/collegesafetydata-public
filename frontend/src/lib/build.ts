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

export function fetchBuildInfo(): Promise<BuildInfo | null> {
  if (!cache) {
    cache = fetch('/audit.json')
      .then((r) => (r.ok ? r.json() : null))
      .then((a) => {
        const sha = a?.audited_build?.site_record_sha256
        if (typeof sha !== 'string' || sha.length < 12) return null
        return {
          sha256: sha,
          id: sha.slice(0, 12),
          auditedAt: typeof a.generated_at === 'string' ? a.generated_at : null,
          status: typeof a.overall_status === 'string' ? a.overall_status : null,
        }
      })
      .catch(() => null)
  }
  return cache
}

export function useBuildInfo(): BuildInfo | null {
  const [info, setInfo] = useState<BuildInfo | null>(null)
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
