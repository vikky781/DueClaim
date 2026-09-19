import { useAuthenticator } from '@aws-amplify/ui-react'
import { NavLink, Outlet } from 'react-router'

import { DisclaimerFooter } from './ui'

const navClass = ({ isActive }: { isActive: boolean }) =>
  `text-[14px] transition-colors hover:text-paper ${isActive ? 'text-paper' : 'text-mute'}`

export default function Layout() {
  const { signOut, user } = useAuthenticator((ctx) => [ctx.user])
  const email = user?.signInDetails?.loginId

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-4xl flex-col px-6 py-8 sm:px-8">
      <header className="flex flex-wrap items-baseline justify-between gap-x-8 gap-y-3 border-b border-rule pb-5">
        <NavLink to="/dashboard" className="font-display text-xl font-medium tracking-tight text-paper">
          DueClaim
        </NavLink>
        <nav aria-label="Primary" className="flex items-baseline gap-6">
          <NavLink to="/dashboard" className={navClass}>
            Dashboard
          </NavLink>
          <NavLink to="/invoices/new" className={navClass}>
            New invoice
          </NavLink>
          <NavLink to="/business" className={navClass}>
            Business
          </NavLink>
          <button
            type="button"
            onClick={signOut}
            className="font-mono text-[11px] uppercase tracking-[0.14em] text-mute hover:text-paper"
            title={email ? `Signed in as ${email}` : undefined}
          >
            Sign out
          </button>
        </nav>
      </header>

      <main className="flex-1 pt-10">
        <Outlet />
      </main>

      <DisclaimerFooter />
    </div>
  )
}
