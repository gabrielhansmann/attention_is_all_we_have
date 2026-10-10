import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { Lock, Mail } from 'lucide-react'
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
    <section aria-labelledby="signin-h" className="grid min-h-dvh place-items-center bg-canvas-tint px-4 py-12">
      <div className="flex w-full max-w-sm flex-col gap-6 rounded-3xl border border-border bg-background p-8 shadow-md">
        <div className="flex flex-col items-center gap-3 text-center">
          <span className="grid size-12 place-items-center rounded-2xl bg-primary text-lg font-semibold text-primary-foreground" aria-hidden>B</span>
          <div>
            <h1 id="signin-h" className="text-2xl">Sign in</h1>
            <p className="mt-1 text-sm text-muted-foreground">There is no sign-up. Ask an administrator for an account.</p>
          </div>
        </div>
        <form onSubmit={submit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="signin-email">Email</Label>
            <div className="relative">
              <Mail className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <Input id="signin-email" type="email" autoComplete="username" required value={email} className="pl-10"
                onChange={(e) => setEmail(e.target.value)} />
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="signin-password">Password</Label>
            <div className="relative">
              <Lock className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <Input id="signin-password" type="password" autoComplete="current-password" required value={password} className="pl-10"
                onChange={(e) => setPassword(e.target.value)} />
            </div>
          </div>
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
          <Button type="submit" size="lg" disabled={busy || !email || !password}>{busy ? 'Signing in' : 'Sign in'}</Button>
        </form>
      </div>
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
