import { getJson } from './client'

export async function checkHealth(signal: AbortSignal): Promise<void> {
  const data = await getJson('/health', signal)
  if (typeof data !== 'object' || data === null || !('status' in data) || data.status !== 'ok') {
    throw new Error('Unexpected health response')
  }
}
