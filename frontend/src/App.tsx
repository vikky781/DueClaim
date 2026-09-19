import { Authenticator, ThemeProvider, View } from '@aws-amplify/ui-react'
import { Navigate, Route, Routes } from 'react-router'

import { AUTH_CONFIGURED, theme } from './amplify'
import Layout from './components/Layout'
import { BusinessProvider, RequireBusiness } from './components/RequireBusiness'
import { DISCLAIMER } from './lib/text'
import BusinessPage from './pages/BusinessPage'
import DashboardPage from './pages/DashboardPage'
import InvoiceDetailPage from './pages/InvoiceDetailPage'
import NewInvoicePage from './pages/NewInvoicePage'

function AuthHeader() {
  return (
    <View textAlign="center" paddingTop="2.5rem" paddingBottom="1.5rem">
      <div className="font-display text-3xl font-medium tracking-tight text-paper">DueClaim</div>
      <div className="mt-2 font-mono text-[11px] uppercase tracking-[0.18em] text-mute">MSMED Act 2006 · s.16</div>
    </View>
  )
}

function AuthFooter() {
  return (
    <View padding="1.5rem 2rem 2.5rem" maxWidth="32rem" margin="0 auto">
      <p className="text-center text-[12px] leading-relaxed text-mute">{DISCLAIMER}</p>
    </View>
  )
}

function MissingConfig() {
  return (
    <div className="mx-auto max-w-xl px-6 py-24">
      <h1 className="font-display text-3xl text-paper">Auth is not configured</h1>
      <p className="mt-4 text-[15px] leading-relaxed text-mute">
        Set <code className="font-mono text-paper">VITE_USER_POOL_ID</code> and{' '}
        <code className="font-mono text-paper">VITE_USER_POOL_CLIENT_ID</code> (the UserPoolId and UserPoolClientId
        stack outputs) in <code className="font-mono text-paper">frontend/.env</code> or the Amplify Hosting
        environment variables, then rebuild.
      </p>
    </div>
  )
}

export default function App() {
  if (!AUTH_CONFIGURED) return <MissingConfig />

  return (
    <ThemeProvider theme={theme} colorMode="dark">
      <Authenticator
        loginMechanisms={['email']}
        signUpAttributes={['email']}
        components={{ Header: AuthHeader, Footer: AuthFooter }}
        variation="default"
      >
        <Routes>
          <Route element={<BusinessProvider />}>
            <Route element={<Layout />}>
              <Route path="/business" element={<BusinessPage />} />
              <Route element={<RequireBusiness />}>
                <Route path="/dashboard" element={<DashboardPage />} />
                <Route path="/invoices/new" element={<NewInvoicePage />} />
                <Route path="/invoices/:id" element={<InvoiceDetailPage />} />
              </Route>
              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Route>
          </Route>
        </Routes>
      </Authenticator>
    </ThemeProvider>
  )
}
