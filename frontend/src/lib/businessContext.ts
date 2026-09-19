import { createContext, useContext } from 'react'

import type { Business } from '../api/types'

export interface BusinessContextValue {
  business: Business | null
  setBusiness: (b: Business) => void
}

export const BusinessContext = createContext<BusinessContextValue>({ business: null, setBusiness: () => {} })
export const useBusiness = () => useContext(BusinessContext)
