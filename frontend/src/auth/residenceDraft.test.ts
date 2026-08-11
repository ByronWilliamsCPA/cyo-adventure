import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { clearResidenceDraft, readResidenceDraft, rememberResidenceDraft } from './residenceDraft'

beforeEach(() => {
  sessionStorage.clear()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('residenceDraft', () => {
  it('round-trips the picked country', () => {
    rememberResidenceDraft('GB')
    expect(readResidenceDraft()).toBe('GB')
  })

  it('reads as the empty select value when nothing was picked', () => {
    // '' and not null: the consent form seeds a <select> directly from this,
    // and '' is already that select's "Select a country" placeholder value.
    // Returning null would render a select with no matching option.
    expect(readResidenceDraft()).toBe('')
  })

  it('forgets the country on clear', () => {
    rememberResidenceDraft('US')
    clearResidenceDraft()
    expect(readResidenceDraft()).toBe('')
  })

  it('stays out of localStorage', () => {
    // This value belongs to one sign-up attempt in one tab. A handed-over or
    // shared device must not surface one adult's country to the next one, so
    // persistence beyond the tab session is the defect being pinned here.
    rememberResidenceDraft('CA')
    expect(Object.keys(localStorage)).toHaveLength(0)
  })

  it('survives storage being unavailable', () => {
    // Private mode, quota, or a browser that refuses storage. Losing the
    // draft costs one re-pick; throwing would take down the verification
    // screen's submit path, which is the only way forward for this guardian.
    const boom = () => {
      throw new Error('storage disabled')
    }
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(boom)
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(boom)
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(boom)

    expect(() => rememberResidenceDraft('US')).not.toThrow()
    expect(readResidenceDraft()).toBe('')
    expect(() => clearResidenceDraft()).not.toThrow()
  })
})
