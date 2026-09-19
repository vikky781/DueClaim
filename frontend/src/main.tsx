import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import '@aws-amplify/ui-react/styles.css'
import './index.css'

import { configureAmplify } from './amplify'
import App from './App.tsx'

configureAmplify()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
