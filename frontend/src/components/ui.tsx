import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import { cva, type VariantProps } from 'class-variance-authority'
import { clsx } from 'clsx'
import { X } from '@phosphor-icons/react'

const buttonVariants = cva('button', { variants: { variant: { primary: 'button-primary', secondary: 'button-secondary', ghost: 'button-ghost', danger: 'button-danger' }, size: { default: '', small: 'button-small', icon: 'button-icon' } }, defaultVariants: { variant: 'primary', size: 'default' } })
export function Button({ className, variant, size, asChild, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : 'button'
  return <Comp className={clsx(buttonVariants({ variant, size }), className)} {...props} />
}
export function Dialog({ open, onOpenChange, title, description, children, wide }: { open: boolean; onOpenChange: (value: boolean) => void; title: string; description?: string; children: React.ReactNode; wide?: boolean }) {
  const returnFocus = React.useRef<HTMLElement | null>(null)
  return <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="dialog-overlay" />
      <DialogPrimitive.Content className={clsx('dialog-content', wide && 'dialog-wide')} onOpenAutoFocus={() => { returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null }} onCloseAutoFocus={event => { event.preventDefault(); returnFocus.current?.focus() }}>
        <div className="dialog-header"><div><DialogPrimitive.Title>{title}</DialogPrimitive.Title><DialogPrimitive.Description>{description || 'Review and update the details for this workspace.'}</DialogPrimitive.Description></div>
          <DialogPrimitive.Close asChild><Button variant="ghost" size="icon" aria-label="Close dialog"><X size={22} /></Button></DialogPrimitive.Close></div>
        {children}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  </DialogPrimitive.Root>
}
export function Badge({ children, tone = 'neutral' }: { children: React.ReactNode; tone?: 'neutral' | 'blue' | 'success' | 'warning' | 'error' }) {
  return <span className={clsx('badge', `badge-${tone}`)}>{children}</span>
}
export function Empty({ title, children }: { title: string; children: React.ReactNode }) {
  return <div className="empty-state"><h3>{title}</h3><p>{children}</p></div>
}
