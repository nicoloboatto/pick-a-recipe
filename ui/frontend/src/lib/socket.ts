/**
 * Socket.IO singleton + React hooks.
 *
 * The backend emits:
 *  - room "job_{job_id}": progress/completion events for one job
 *  - room "user_{username}": user-scoped events (recipe previews, approvals)
 * Joining the implicit default namespace is enough — Flask puts each
 * connection into its user room on connect (see app.py socket handlers).
 */
import { useEffect } from 'react'
import { io, type Socket } from 'socket.io-client'
import type {
  ClientToServerEvents,
  JobStatus,
  JobTransitionPayload,
  ServerToClientEvents,
} from '@/types'

export type PickARecipeSocket = Socket<ServerToClientEvents, ClientToServerEvents>

let socket: PickARecipeSocket | null = null

export function getSocket(): PickARecipeSocket {
  if (!socket) {
    socket = io({
      // Same origin in prod; Vite proxies /socket.io in dev
      withCredentials: true,
      transports: ['websocket', 'polling'],
    })
  }
  return socket
}

/**
 * Subscribe to a socket event for the lifetime of the component.
 * Handler identity changes are safe — re-attached on change without
 * reconnecting.
 */
export function useSocketEvent<K extends keyof ServerToClientEvents>(
  event: K,
  handler: (...args: Parameters<ServerToClientEvents[K]>) => void,
): void {
  useEffect(() => {
    // socket.io's generic overload doesn't resolve through mapped key K;
    // this structural view keeps handler fully typed at call sites.
    const s = getSocket() as unknown as {
      on(event: string, listener: (...args: never[]) => void): typeof s
      off(event: string, listener: (...args: never[]) => void): typeof s
    }
    const wrapped = handler as unknown as (...args: never[]) => void
    s.on(event, wrapped)
    return () => {
      s.off(event, wrapped)
    }
  }, [event, handler])
}

/**
 * The backend emits one event per state transition, named `job_<status>`
 * (job_running, job_awaiting_approval, ...). They share one payload shape,
 * so this hook types them without per-call casts in pages.
 */
export function useTransitionEvent(
  status: JobStatus,
  handler: (p: JobTransitionPayload) => void,
): void {
  useRawSocketEvent(`job_${status}`, handler)
}

function useRawSocketEvent(
  event: string,
  handler: (...args: never[]) => void,
): void {
  useEffect(() => {
    const s = getSocket() as unknown as PickARecipeSocket & {
      on(event: string, listener: (...args: never[]) => void): unknown
      off(event: string, listener: (...args: never[]) => void): unknown
    }
    s.on(event, handler)
    return () => {
      s.off(event, handler)
    }
  }, [event, handler])
}

/** Join a job room; re-subscribes if jobId changes. */
export function useJobRoom(
  jobId: string | undefined,
  opts?: { onSubscribed?: () => void },
): void {
  useEffect(() => {
    if (!jobId) return
    const s = getSocket()
    s.emit('subscribe_job', jobId)
    const onSubscribed = (p: { job_id: string; status: string }) => {
      if (p.job_id === jobId) opts?.onSubscribed?.()
    }
    s.on('subscribed', onSubscribed)
    return () => {
      s.off('subscribed', onSubscribed)
      s.emit('unsubscribe_job', jobId)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId])
}
