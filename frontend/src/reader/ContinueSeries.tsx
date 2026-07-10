/**
 * "Continue the series" for the ending screen (WS-G decision G1): queries
 * series-next once on mount and, when a readable next book exists, offers a
 * jump to it carrying the continuation seed (entry node plus, for
 * state-carrying series, the finished book's final var_state) through router
 * location state. Absence of a button is the v1 answer to every miss.
 */

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { Button } from '@ds/components/Button'

import type { SeriesNextBookInfo } from '../api/readerApi'
import type { ContinuationSeed } from '../player/series'
import type { VarState } from '../player/types'

export interface ContinueSeriesProps {
  profileId: string
  storybookId: string
  fetchSeriesNext: (
    profileId: string,
    storybookId: string
  ) => Promise<SeriesNextBookInfo | null>
  finalVarState: VarState
  carriesState: boolean
}

export function ContinueSeries({
  profileId,
  storybookId,
  fetchSeriesNext,
  finalVarState,
  carriesState,
}: ContinueSeriesProps) {
  const navigate = useNavigate()
  const [next, setNext] = useState<SeriesNextBookInfo | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchSeriesNext(profileId, storybookId)
      .then((info) => {
        if (!cancelled) setNext(info)
      })
      .catch((error: unknown) => {
        // #EDGE: external-resources: continuation is best-effort; a failed
        // lookup must never break the ending screen. No button is the v1
        // fallback for every absence, including transport errors.
        // #VERIFY: ContinueSeries.test.tsx "renders nothing when the lookup fails".
        console.error('[reader] series-next lookup failed', {
          profileId,
          storybookId,
          error,
        })
      })
    return () => {
      cancelled = true
    }
  }, [fetchSeriesNext, profileId, storybookId])

  if (!next) return null
  const target = next
  const continueSeries = () => {
    const continuation: ContinuationSeed = {
      entryNode: target.series_entry_node ?? null,
      varState: carriesState ? finalVarState : undefined,
    }
    void navigate(`/read/${profileId}/${target.storybook_id}/${target.version}`, {
      state: { continuation },
    })
  }
  return (
    <Button variant="primary" size="lg" data-testid="continue-series" onClick={continueSeries}>
      Continue the series
    </Button>
  )
}
