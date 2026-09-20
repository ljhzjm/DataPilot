export interface AuthUser {
  id: string
  username: string
  display_name: string
  created_at: string
}

export interface AuthWorkspace {
  id: string
  name: string
  slug: string
  role: string
}

export interface AuthSession {
  user: AuthUser
  workspace: AuthWorkspace
}
