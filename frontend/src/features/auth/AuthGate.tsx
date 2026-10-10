import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { api, ApiError } from '@/lib/api'
import { markRequired, setSession, setUser, useAuth } from '@/lib/auth'

function SignIn() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const r = await api.login(email.trim(), password)
      setPassword('')
      setSession(r.token, r.user)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong.')
      setBusy(false)
    }
  }

  return (
    <section aria-labelledby="signin-h" className="mx-auto flex w-full max-w-sm flex-col gap-4 px-6 py-24">
      <h1 id="signin-h" className="text-2xl">Sign in</h1>
      <p className="text-sm text-muted-foreground">There is no sign-up. Ask an administrator for an account.</p>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="signin-email">Email</Label>
          <Input id="signin-email" type="email" autoComplete="username" required value={email}
            onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="signin-password">Password</Label>
          <Input id="signin-password" type="password" autoComplete="current-password" required value={password}
            onChange={(e) => setPassword(e.target.value)} />
        </div>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <div>
          <Button type="submit" size="lg" disabled={busy || !email || !password}>{busy ? 'Signing in' : 'Sign in'}</Button>
        </div>
      </form>
    </section>
  )
}

export async function signOut() {
  try {
    await api.logout()
  } catch {
    /* the token is dropped locally either way */
  }
  markRequired()
}

/** Shows the sign-in form when there is no valid session; otherwise the app. */
export function AuthGate({ children }: { children: ReactNode }) {
  const { status, user } = useAuth()

  // After a reload the token is still there but the name is not: ask who we are. A 401 flips the gate by itself.
  useEffect(() => {
    if (status !== 'signedIn' || user) return
    let cancelled = false
    api.me().then((u) => !cancelled && setUser(u)).catch(() => undefined)
    return () => { cancelled = true }
  }, [status, user])

  return status === 'required' ? <main id="main-content"><SignIn /></main> : <>{children}</>
}
