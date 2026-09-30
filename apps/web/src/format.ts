const compact = new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 })
const whole = new Intl.NumberFormat('en-US')

export const formatCount = (n: number): string => (n >= 10_000 ? compact.format(n) : whole.format(n))

export const formatPercent = (rate: number, digits = 1): string => `${(rate * 100).toFixed(digits)}%`

export function formatHours(hours: number | null): string {
  if (hours === null) return '—'
  if (hours < 1) return `${Math.round(hours * 60)} min`
  if (hours < 48) return `${hours.toFixed(1)} h`
  return `${(hours / 24).toFixed(1)} d`
}

export function formatWeek(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

export function formatDate(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

const SUBCATEGORY_LABELS: Record<string, string> = {
  lan: 'Site network outage',
  vpn: 'VPN connection failures',
  email: 'Email not syncing',
  certificate: 'Expired TLS certificate',
  handheld: 'Handheld scanners not syncing',
  wireless: 'Wi-Fi drops',
  wan: 'Slow internet (WAN)',
  sap: 'SAP performance',
  wms: 'WMS wave release',
}

export function describeSubcategory(subcategory: string): string {
  return SUBCATEGORY_LABELS[subcategory] ?? subcategory.replace(/-/g, ' ')
}
