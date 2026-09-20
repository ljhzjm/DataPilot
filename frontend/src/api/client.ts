interface ApiErrorBody {
  detail?: string
}

export async function apiRequest<T>(
  input: string,
  init?: RequestInit,
): Promise<T> {
  const response = await apiFetch(input, init)
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiErrorBody
    throw new Error(body.detail || `请求失败：${response.status}`)
  }
  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

export async function apiFetch(
  input: string,
  init?: RequestInit,
): Promise<Response> {
  const response = await fetch(input, {
    ...init,
    credentials: 'include',
  })
  if (
    response.status === 401 &&
    !input.startsWith('/api/auth/')
  ) {
    window.dispatchEvent(new Event('datapilot:unauthorized'))
  }
  return response
}
