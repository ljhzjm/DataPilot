import type { AuthSession } from '../types/auth'
import { apiRequest } from './client'

export function getCurrentSession(): Promise<AuthSession> {
  return apiRequest<AuthSession>('/api/auth/me')
}

export function login(
  username: string,
  password: string,
): Promise<AuthSession> {
  return apiRequest<AuthSession>('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
}

export function register(
  username: string,
  password: string,
  displayName: string,
): Promise<AuthSession> {
  return apiRequest<AuthSession>('/api/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      username,
      password,
      display_name: displayName,
    }),
  })
}

export async function logout(): Promise<void> {
  const response = await apiRequest<Record<string, never>>('/api/auth/logout', {
    method: 'POST',
  })
  void response
}
