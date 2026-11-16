/**
 * The one formatter of figures on the site (pages, head tags and the edge
 * worker), with no dependencies so that every bundle can use it.
 */

/**
 * A number for reading: thousands separators ("1,234"), and with `decimals`
 * exactly that many decimals ("1,234.50"); without it, the decimals the
 * number has (up to 3).
 */
export function formatNumber(n: number, decimals?: number): string {
  return decimals === undefined
    ? n.toLocaleString('en-US')
    : n.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}
