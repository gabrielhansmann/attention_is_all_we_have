import { useSyncExternalStore } from 'react'
import type { AuthUser } from '@/types/api'

// The session token lives in sessionStorage: it survives a reload but not closing the tab. That limits exposure
// compared with localStorage; it is still readable by any script on the page, which is why the app ships no
// third-party scripts. Business data is read from the API and is never saved here.
const KEY = 'bmw-api-token'

type Status = 'signedIn' | 'required'
interface State {
  status: Status
  user: AuthUser | null
}

const read = (): string | null => {
  try {
    return window.sessionStorage.getItem(KEY)
  } catch {
    return null
  }
}
const write = (token: string | null) => {
  try {
    if (token) window.sessionStorage.setItem(KEY, token)
    else window.sessionStorage.removeItem(KEY)
  } catch {
    /* storage unavailable: the session then lasts until reload */
  }
}

let memoryToken: string | null = read()
let state: State = { status: memoryToken ? 'signedIn' : 'required', user: null }
const listeners = new Set<() => void>()
const set = (next: State) => {
  state = next
  listeners.forEach((l) => l())
}

export const getToken = () => memoryToken

/** Called after a successful login. */
export function setSession(token: string, user: AuthUser) {
  memoryToken = token
  write(token)
  set({ status: 'signedIn', user })
}

export function setUser(user: AuthUser) {
  if (state.status === 'signedIn') set({ status: 'signedIn', user })
}

/** The backend answered 401: the token is missing, expired or revoked. */
export function markRequired() {
  memoryToken = null
  write(null)
  if (state.status !== 'required') set({ status: 'required', user: null })
}

export function useAuth(): State {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb)
      return () => listeners.delete(cb)
    },
    () => state,
  )
}
