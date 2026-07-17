import { describe, expect, it, vi } from 'vitest'

import {
  BUDGET_EXCEEDED_MESSAGE,
  formatBudgetBanner,
  isBudgetExceededError,
  makeBudgetApi,
  type FamilyBudgetView,
} from './budgetApi'

function fakeAxios() {
  return { get: vi.fn() }
}

describe('makeBudgetApi', () => {
  it('reads the family budget from GET /v1/families/me/budget', async () => {
    const api = fakeAxios()
    const budget: FamilyBudgetView = {
      quota: 5,
      spent_this_month: 2,
      remaining: 3,
      children: [],
    }
    api.get.mockResolvedValue({ data: budget })
    const result = await makeBudgetApi(api as never).get()
    expect(api.get).toHaveBeenCalledWith('/v1/families/me/budget')
    expect(result).toEqual(budget)
  })
})

describe('formatBudgetBanner', () => {
  it('formats the plural case', () => {
    expect(
      formatBudgetBanner({ quota: 5, spent_this_month: 2, remaining: 3, children: [] })
    ).toBe('3 of 5 stories left this month')
  })

  it('formats the singular-quota case', () => {
    expect(
      formatBudgetBanner({ quota: 1, spent_this_month: 0, remaining: 1, children: [] })
    ).toBe('1 of 1 story left this month')
  })

  it('formats the zero-remaining case', () => {
    expect(
      formatBudgetBanner({ quota: 5, spent_this_month: 5, remaining: 0, children: [] })
    ).toBe('0 of 5 stories left this month')
  })
})

describe('isBudgetExceededError', () => {
  it('is true for a 409 whose message mentions budget', () => {
    const err = {
      isAxiosError: true,
      response: { status: 409, data: { message: 'monthly story budget reached' } },
    }
    expect(isBudgetExceededError(err)).toBe(true)
  })

  it('is false for a 409 with a different message (e.g. the pending cap)', () => {
    const err = {
      isAxiosError: true,
      response: { status: 409, data: { message: 'too many pending requests for this profile' } },
    }
    expect(isBudgetExceededError(err)).toBe(false)
  })

  it('is false for a non-409 axios error', () => {
    const err = { isAxiosError: true, response: { status: 403, data: { message: 'budget' } } }
    expect(isBudgetExceededError(err)).toBe(false)
  })

  it('is false for a non-axios error', () => {
    expect(isBudgetExceededError(new Error('monthly story budget reached'))).toBe(false)
  })

  it('is false when the response body has no message', () => {
    const err = { isAxiosError: true, response: { status: 409, data: {} } }
    expect(isBudgetExceededError(err)).toBe(false)
  })
})

describe('BUDGET_EXCEEDED_MESSAGE', () => {
  it('mentions waiting for next month', () => {
    expect(BUDGET_EXCEEDED_MESSAGE).toMatch(/next month/i)
  })
})
