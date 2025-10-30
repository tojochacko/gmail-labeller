import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import App from '../src/App'
import { emitOAuthCompletion, oauthMocks } from './setup'

const STORAGE_KEY = 'gmail-labeler-session'

beforeEach(() => {
  window.localStorage.clear()
  Object.values(oauthMocks).forEach((mock) => mock.mockClear())
})

describe('App onboarding flow', () => {
  it('starts OAuth flow when the form is submitted', async () => {
    render(<App />)

    const emailInput = screen.getByLabelText(/Gmail address/i)
    fireEvent.change(emailInput, { target: { value: 'user@example.com' } })

    await act(async () => {
      fireEvent.submit(emailInput.closest('form') as HTMLFormElement)
    })

    await waitFor(() => expect(oauthMocks.oauthStartMock).toHaveBeenCalledTimes(1))

    expect(JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? '{}')).toMatchObject({
      email: 'user@example.com',
    })
  })

  it('displays connection success when OAuth completion event fires', async () => {
    render(<App />)

    const emailInput = screen.getByLabelText(/Gmail address/i)
    fireEvent.change(emailInput, { target: { value: 'user@example.com' } })

    await act(async () => {
      fireEvent.submit(emailInput.closest('form') as HTMLFormElement)
    })

    act(() => {
      emitOAuthCompletion({ connected: true, expiresAt: new Date().toISOString() })
    })

    await waitFor(() => expect(screen.getAllByText(/Connected to Gmail/i).length).toBeGreaterThan(0))
    expect(screen.getByText(/Connected to Gmail/i)).toBeInTheDocument()
  })

  it('fetches emails once connected', async () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ userId: 'user-123', email: 'user@example.com' }),
    )
    oauthMocks.oauthStatusMock.mockResolvedValueOnce({
      connected: true,
      expiresAt: new Date().toISOString(),
    })

    render(<App />)

    await waitFor(() => {
      expect(screen.getAllByText(/Connected to Gmail/i).length).toBeGreaterThan(0)
    })

    const buttons = screen.getAllByRole('button', { name: /Fetch latest emails/i })
    const fetchButton = buttons[buttons.length - 1]
    await act(async () => {
      fireEvent.click(fetchButton)
    })

    await waitFor(() => expect(oauthMocks.emailsFetchMock).toHaveBeenCalledTimes(1))
    expect(screen.getByText('Test email')).toBeInTheDocument()
  })

  it('applies labels and triggers agent runs', async () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ userId: 'user-123', email: 'user@example.com' }),
    )
    oauthMocks.oauthStatusMock.mockResolvedValueOnce({
      connected: true,
      expiresAt: new Date().toISOString(),
    })

    render(<App />)

    await waitFor(() => {
      expect(screen.getAllByText(/Connected to Gmail/i).length).toBeGreaterThan(0)
    })

    const labelButtons = screen.getAllByRole('button', { name: /Apply Autogen label/i })
    await act(async () => {
      fireEvent.click(labelButtons[labelButtons.length - 1])
    })

    await waitFor(() => expect(oauthMocks.labelsApplyMock).toHaveBeenCalledTimes(1))

    const agentButtons = screen.getAllByRole('button', { name: /Trigger agent/i })
    await act(async () => {
      fireEvent.click(agentButtons[agentButtons.length - 1])
    })

    await waitFor(() => expect(oauthMocks.runsTriggerMock).toHaveBeenCalledTimes(1))
  })
})
