import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { api, ApiError } from '@/lib/api'
import { setSession, setUser, useAuth } from '@/lib/auth'

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
    <section aria-labelledby="signin-h" className="mx-auto flex w-full max-w-md flex-col gap-4 border border-border p-6">
      <h2 id="signin-h" className="text-xl">Sign in to your workspace</h2>
      <p className="text-sm text-muted-foreground">
        Your workspace reads stored evidence and runs research. There is no sign-up here:
        ask an administrator to create one for you.
      </p>
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

/** Shows the sign-in form when the backend has said "not authenticated"; otherwise the live views and who is signed in. */
export function AuthGate({ children }: { children: ReactNode }) {
  const { status, user } = useAuth()

  // After a reload the token is still there but the name is not: ask who we are. A 401 flips the gate by itself.
  useEffect(() => {
    if (status !== 'signedIn' || user) return
    let cancelled = false
    api.me().then((u) => !cancelled && setUser(u)).catch(() => undefined)
    return () => { cancelled = true }
  }, [status, user])

  if (status === 'required') return <main className="main-content flex min-h-dvh flex-col gap-8"><h1>BMW Product Intelligence</h1><SignIn /></main>
  return <>{children}</>
}
