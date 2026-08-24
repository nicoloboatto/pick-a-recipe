import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { SessionUser } from '@/types'

/**
 * Current Flask session user. Returns null while loading or when logged out
 * (the api layer hard-redirects to /login on 401, so a thrown query here is
 * transient).
 */
export function useSession() {
  return useQuery<SessionUser>({
    queryKey: ['session'],
    queryFn: () => api.me(),
    staleTime: 5 * 60 * 1000,
    retry: false,
  })
}
