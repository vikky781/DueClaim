/**
 * Amplify Auth configuration + an Amplify UI theme built from the DueClaim
 * tokens in index.css, so the <Authenticator> looks native to the app rather
 * than pasted in from the default bright-blue theme.
 */

import { Amplify } from 'aws-amplify'
import { createTheme, defaultDarkModeOverride } from '@aws-amplify/ui-react'

export const AUTH_CONFIGURED = Boolean(
  import.meta.env.VITE_USER_POOL_ID && import.meta.env.VITE_USER_POOL_CLIENT_ID,
)

export function configureAmplify(): void {
  if (!AUTH_CONFIGURED) return
  Amplify.configure({
    Auth: {
      Cognito: {
        userPoolId: import.meta.env.VITE_USER_POOL_ID!,
        userPoolClientId: import.meta.env.VITE_USER_POOL_CLIENT_ID!,
        loginWith: { email: true },
        signUpVerificationMethod: 'code',
        userAttributes: { email: { required: true } },
      },
    },
  })
}

// Same values as :root @theme in index.css. Kept literal because Amplify's
// theme is JS, and referencing CSS vars here would break its color math.
const c = {
  ink: '#151412',
  slate: '#1e1c19',
  rule: '#2d2a25',
  paper: '#ece6da',
  mute: '#8c8577',
  brass: '#d9a441',
  brassDeep: '#a9782a',
  alert: '#d0654f',
}

export const theme = createTheme({
  name: 'dueclaim',
  overrides: [defaultDarkModeOverride],
  tokens: {
    fonts: {
      default: {
        variable: '"IBM Plex Sans", system-ui, sans-serif',
        static: '"IBM Plex Sans", system-ui, sans-serif',
      },
    },
    radii: { small: '4px', medium: '6px', large: '8px' },
    colors: {
      background: { primary: c.ink, secondary: c.slate, tertiary: c.slate },
      font: {
        primary: c.paper,
        secondary: c.mute,
        tertiary: c.mute,
        interactive: c.brass,
        hover: c.paper,
        focus: c.paper,
        active: c.paper,
        error: c.alert,
      },
      border: { primary: c.rule, secondary: c.rule, tertiary: c.rule, focus: c.brass, error: c.alert },
      brand: {
        primary: {
          10: c.slate,
          20: c.rule,
          40: c.brassDeep,
          60: c.brassDeep,
          80: c.brass,
          90: c.brass,
          100: c.brass,
        },
      },
    },
    components: {
      authenticator: {
        router: { backgroundColor: c.ink, borderColor: c.rule, borderWidth: '1px', boxShadow: 'none' },
        form: { padding: '2rem' },
        footer: { paddingBottom: '1.5rem' },
        state: { inactive: { backgroundColor: c.ink } },
      },
      button: {
        primary: {
          backgroundColor: c.brass,
          color: c.ink,
          borderColor: c.brass,
          _hover: { backgroundColor: c.brassDeep, color: c.ink, borderColor: c.brassDeep },
          _focus: { backgroundColor: c.brassDeep, color: c.ink, boxShadow: `0 0 0 3px ${c.ink}, 0 0 0 5px ${c.brass}` },
          _active: { backgroundColor: c.brassDeep, color: c.ink },
        },
        link: {
          color: c.brass,
          _hover: { color: c.paper, backgroundColor: 'transparent' },
          _focus: { color: c.paper, backgroundColor: 'transparent' },
          _active: { color: c.paper, backgroundColor: 'transparent' },
        },
      },
      tabs: {
        borderColor: c.rule,
        item: {
          color: c.mute,
          borderColor: 'transparent',
          _hover: { color: c.paper },
          _focus: { color: c.paper },
          _active: { color: c.brass, borderColor: c.brass, backgroundColor: 'transparent' },
        },
      },
      fieldcontrol: {
        color: c.paper,
        borderColor: c.rule,
        _focus: { borderColor: c.brass, boxShadow: `0 0 0 1px ${c.brass}` },
      },
      field: { label: { color: c.mute } },
      heading: { color: c.paper },
      text: { color: c.paper, error: { color: c.alert } },
      alert: { error: { backgroundColor: c.slate, color: c.alert } },
    },
  },
})
