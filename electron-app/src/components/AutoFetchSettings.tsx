import { useCallback, useEffect, useState } from 'react'
import type { AutoFetchStatus } from '../shared/ipc'

export function AutoFetchSettings() {
  const [enabled, setEnabled] = useState(false)
  const [interval, setInterval] = useState(30)
  const [notifications, setNotifications] = useState(true)
  const [fetchOnStartup, setFetchOnStartup] = useState(false)
  const [status, setStatus] = useState<AutoFetchStatus | null>(null)
  const [countdown, setCountdown] = useState<number | null>(null)
  const [isUpdating, setIsUpdating] = useState(false)

  // Load initial status
  useEffect(() => {
    const loadStatus = async () => {
      try {
        const currentStatus = await window.electronAPI.autoFetch.getStatus()
        setStatus(currentStatus)
        setEnabled(currentStatus.enabled)
        setInterval(currentStatus.intervalMinutes)
      } catch (error) {
        console.error('Failed to load auto-fetch status:', error)
      }
    }

    loadStatus()

    // Listen for status changes
    const unsubscribe = window.electronAPI.autoFetch.onStatusChanged((payload) => {
      console.log('Auto-fetch status changed:', payload)
      setStatus(payload.status)
    })

    return unsubscribe
  }, [])

  // Update countdown timer
  useEffect(() => {
    if (!enabled || !status?.lastFetchTimestamp) {
      setCountdown(null)
      return undefined
    }

    const timer = window.setInterval(() => {
      if (status?.lastFetchTimestamp) {
        const lastFetch = new Date(status.lastFetchTimestamp).getTime()
        const nextFetch = lastFetch + interval * 60 * 1000
        const remaining = Math.max(0, nextFetch - Date.now())
        setCountdown(Math.floor(remaining / 1000))
      }
    }, 1000)

    return () => {
      window.clearInterval(timer)
    }
  }, [enabled, status?.lastFetchTimestamp, interval])

  const handleToggle = useCallback(
    async (newEnabled: boolean) => {
      setIsUpdating(true)
      try {
        if (newEnabled) {
          const result = await window.electronAPI.autoFetch.start({
            enabled: true,
            intervalMinutes: interval,
            notificationsEnabled: notifications,
            fetchOnStartup,
          })
          if (result.success && result.status) {
            setStatus(result.status)
            setEnabled(true)
            console.log('Auto-fetch started successfully')
          } else {
            console.error('Failed to start auto-fetch:', result.error)
            alert(`Failed to start auto-fetch: ${result.error || 'Unknown error'}`)
          }
        } else {
          const result = await window.electronAPI.autoFetch.stop()
          if (result.success && result.status) {
            setStatus(result.status)
            setEnabled(false)
            console.log('Auto-fetch stopped successfully')
          } else {
            console.error('Failed to stop auto-fetch:', result.error)
            alert(`Failed to stop auto-fetch: ${result.error || 'Unknown error'}`)
          }
        }
      } catch (error) {
        console.error('Error toggling auto-fetch:', error)
        alert(`Error: ${error instanceof Error ? error.message : 'Unknown error'}`)
      } finally {
        setIsUpdating(false)
      }
    },
    [interval, notifications, fetchOnStartup],
  )

  const handleIntervalChange = useCallback(
    async (newInterval: number) => {
      setInterval(newInterval)

      if (!enabled) return // Only update if auto-fetch is enabled

      setIsUpdating(true)
      try {
        const result = await window.electronAPI.autoFetch.updateSettings({
          intervalMinutes: newInterval,
        })
        if (result.success && result.status) {
          setStatus(result.status)
          console.log(`Interval updated to ${newInterval} minutes`)
        } else {
          console.error('Failed to update interval:', result.error)
        }
      } catch (error) {
        console.error('Error updating interval:', error)
      } finally {
        setIsUpdating(false)
      }
    },
    [enabled],
  )

  const handleNotificationsChange = useCallback(
    async (newNotifications: boolean) => {
      setNotifications(newNotifications)

      if (!enabled) return // Only update if auto-fetch is enabled

      setIsUpdating(true)
      try {
        const result = await window.electronAPI.autoFetch.updateSettings({
          notificationsEnabled: newNotifications,
        })
        if (result.success && result.status) {
          setStatus(result.status)
          console.log(`Notifications ${newNotifications ? 'enabled' : 'disabled'}`)
        } else {
          console.error('Failed to update notifications:', result.error)
        }
      } catch (error) {
        console.error('Error updating notifications:', error)
      } finally {
        setIsUpdating(false)
      }
    },
    [enabled],
  )

  const handleFetchOnStartupChange = useCallback(
    async (newFetchOnStartup: boolean) => {
      setFetchOnStartup(newFetchOnStartup)

      if (!enabled) return // Only update if auto-fetch is enabled

      setIsUpdating(true)
      try {
        const result = await window.electronAPI.autoFetch.updateSettings({
          fetchOnStartup: newFetchOnStartup,
        })
        if (result.success && result.status) {
          setStatus(result.status)
          console.log(`Fetch on startup ${newFetchOnStartup ? 'enabled' : 'disabled'}`)
        } else {
          console.error('Failed to update fetch on startup:', result.error)
        }
      } catch (error) {
        console.error('Error updating fetch on startup:', error)
      } finally {
        setIsUpdating(false)
      }
    },
    [enabled],
  )

  const handleFetchNow = useCallback(async () => {
    setIsUpdating(true)
    try {
      const result = await window.electronAPI.autoFetch.fetchNow()
      if (result.success) {
        console.log('Manual fetch completed:', result.result)
        alert('Emails fetched successfully!')
      } else {
        console.error('Manual fetch failed:', result.error)
        alert(`Failed to fetch emails: ${result.error || 'Unknown error'}`)
      }
    } catch (error) {
      console.error('Error fetching now:', error)
      alert(`Error: ${error instanceof Error ? error.message : 'Unknown error'}`)
    } finally {
      setIsUpdating(false)
    }
  }, [])

  const formatTime = (seconds: number): string => {
    const min = Math.floor(seconds / 60)
    const sec = seconds % 60
    return `${min}m ${sec}s`
  }

  const formatRelativeTime = (timestamp: string): string => {
    const diff = Date.now() - new Date(timestamp).getTime()
    const minutes = Math.floor(diff / 60000)
    if (minutes < 1) return 'just now'
    if (minutes < 60) return `${minutes} minute${minutes !== 1 ? 's' : ''} ago`
    const hours = Math.floor(minutes / 60)
    if (hours < 24) return `${hours} hour${hours !== 1 ? 's' : ''} ago`
    const days = Math.floor(hours / 24)
    return `${days} day${days !== 1 ? 's' : ''} ago`
  }

  return (
    <div className="auto-fetch-settings card">
      <h3>⚙️ Auto-Fetch Settings</h3>

      <div className="setting-row">
        <label>
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => handleToggle(e.target.checked)}
            disabled={isUpdating}
          />
          Enable Auto-Fetch
          {enabled && <span className="badge" style={{ marginLeft: '8px', backgroundColor: '#4caf50', color: 'white' }}>Active</span>}
        </label>
      </div>

      <div className="setting-row">
        <label>Fetch Interval:</label>
        <select
          value={interval}
          onChange={(e) => handleIntervalChange(Number(e.target.value))}
          disabled={!enabled || isUpdating}
        >
          <option value={15}>Every 15 minutes</option>
          <option value={30}>Every 30 minutes</option>
          <option value={60}>Every 1 hour</option>
          <option value={120}>Every 2 hours</option>
        </select>
      </div>

      <div className="setting-row">
        <label>
          <input
            type="checkbox"
            checked={notifications}
            onChange={(e) => handleNotificationsChange(e.target.checked)}
            disabled={!enabled || isUpdating}
          />
          Show desktop notifications
        </label>
      </div>

      <div className="setting-row">
        <label>
          <input
            type="checkbox"
            checked={fetchOnStartup}
            onChange={(e) => handleFetchOnStartupChange(e.target.checked)}
            disabled={!enabled || isUpdating}
          />
          Fetch on app startup
        </label>
      </div>

      {enabled && countdown !== null && (
        <div className="status-display" style={{ marginTop: '12px', padding: '12px', backgroundColor: '#f5f5f5', borderRadius: '4px' }}>
          <p style={{ margin: '4px 0', fontWeight: 'bold', color: '#333' }}>
            Next fetch in: {formatTime(countdown)}
          </p>
          {status?.lastFetchTimestamp && (
            <p className="hint" style={{ margin: '4px 0', fontSize: '0.9em', color: '#666' }}>
              Last fetched: {formatRelativeTime(status.lastFetchTimestamp)}
            </p>
          )}
          {status && status.retryCount > 0 && (
            <p style={{ margin: '4px 0', fontSize: '0.9em', color: '#f44336' }}>
              ⚠️ Retry attempts: {status.retryCount}
            </p>
          )}
        </div>
      )}

      <button
        onClick={handleFetchNow}
        disabled={isUpdating}
        className="fetch-now-btn"
        style={{ marginTop: '12px', width: '100%' }}
      >
        {isUpdating ? 'Fetching...' : 'Fetch Now'}
      </button>
    </div>
  )
}
