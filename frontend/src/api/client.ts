const baseUrl = import.meta.env.VITE_API_BASE_URL?.replace(/\/+$/, '')

export async function getJson(path: string, signal: AbortSignal): Promise<unknown> {
  if (!baseUrl) throw new Error('VITE_API_BASE_URL is not configured')

  const response = await fetch(`${baseUrl}${path}`, {
    signal,
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw new Error(`API returned HTTP ${response.status}`)
  return response.json()
}
