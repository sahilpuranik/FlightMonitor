import { useState } from 'react'
import './App.css'

function App() {
  const [flight, setFlight] = useState('')
  const [address, setAddress] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  
  const [airportBusy, setAirportBusy] = useState('major-hub')
  const [isHoliday, setIsHoliday] = useState('no')
  const [hasCheckedBags, setHasCheckedBags] = useState('no')

  const handleSubmit = async (e) => {
    e.preventDefault()
    
    if (!flight || !address) {
      setError('Please fill in both fields')
      return
    }

    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const backendUrl = import.meta.env.VITE_BACKEND_URL || window.location.origin
      
      const params = new URLSearchParams({
        flight: flight,
        address: address,
        airport_busy: airportBusy,
        holiday: isHoliday,
        checked_bags: hasCheckedBags
      })
      
      const response = await fetch(`${backendUrl}/when-to-leave?${params}`)

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Failed to calculate')
      }

      const data = await response.json()
      console.log('response:', data)
      setResult(data)
      
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app">
      <header className="header">
        <h1>✈️ FlightMonitor</h1>
        <p>When should I leave to pick someone up?</p>
      </header>

      <main className="main">
        <form onSubmit={handleSubmit} className="form">
          <div className="form-group">
            <label htmlFor="flight">Flight Number</label>
            <input
              type="text"
              id="flight"
              value={flight}
              onChange={(e) => setFlight(e.target.value)}
              placeholder="like AA1234"
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="address">Your Address</label>
            <input
              type="text"
              id="address"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              placeholder="like 123 Main St, New York, NY"
              required
            />
          </div>

            <div className="form-group">
              <label>What type of airport is it?</label>
              <div className="radio-group">
                <label className="radio-label">
                  <input
                    type="radio"
                    name="airportBusy"
                    value="small-hub"
                    checked={airportBusy === 'small-hub'}
                    onChange={(e) => setAirportBusy(e.target.value)}
                  />
                  &nbsp;&nbsp;Small airport
                </label>
                <label className="radio-label">
                  <input
                    type="radio"
                    name="airportBusy"
                    value="major-hub"
                    checked={airportBusy === 'major-hub'}
                    onChange={(e) => setAirportBusy(e.target.value)}
                  />
                  &nbsp;&nbsp;Major hub
                </label>
                <label className="radio-label">
                  <input
                    type="radio"
                    name="airportBusy"
                    value="mega-hub"
                    checked={airportBusy === 'mega-hub'}
                    onChange={(e) => setAirportBusy(e.target.value)}
                  />
                  &nbsp;&nbsp;Mega hub
                </label>
              </div>
            </div>

          <div className="form-group">
            <label>Is it a holiday?</label>
            <div className="radio-group">
              <label className="radio-label">
                <input
                  type="radio"
                  name="holiday"
                  value="no"
                  checked={isHoliday === 'no'}
                  onChange={(e) => setIsHoliday(e.target.value)}
                />
                &nbsp;&nbsp;No holiday
              </label>
              <label className="radio-label">
                <input
                  type="radio"
                  name="holiday"
                  value="small"
                  checked={isHoliday === 'small'}
                  onChange={(e) => setIsHoliday(e.target.value)}
                />
                &nbsp;&nbsp;Minor holiday
              </label>
              <label className="radio-label">
                <input
                  type="radio"
                  name="holiday"
                  value="big"
                  checked={isHoliday === 'big'}
                  onChange={(e) => setIsHoliday(e.target.value)}
                />
                &nbsp;&nbsp;Major holiday
              </label>
            </div>
          </div>

          <div className="form-group">
            <label>Do they have checked bags?</label>
            <div className="radio-group">
              <label className="radio-label">
                <input
                  type="radio"
                  name="checkedBags"
                  value="no"
                  checked={hasCheckedBags === 'no'}
                  onChange={(e) => setHasCheckedBags(e.target.value)}
                />
                &nbsp;&nbsp;No checked bags
              </label>
              <label className="radio-label">
                <input
                  type="radio"
                  name="checkedBags"
                  value="yes"
                  checked={hasCheckedBags === 'yes'}
                  onChange={(e) => setHasCheckedBags(e.target.value)}
                />
                &nbsp;&nbsp;Has checked bags
              </label>
            </div>
          </div>

            <button type="submit" disabled={loading} className="submit-btn">
              {loading ? 'Working on it...' : 'Tell me when to leave!'}
            </button>
        </form>

        {error && (
          <div className="error">
            <h3>Error</h3>
            <p>{error}</p>
          </div>
        )}

        {result && (
          <div className="result">
            <h3>Leave Time</h3>
            <div className="leave-time">{result.leave_time}</div>
            
            <div className="warning">
              <strong>⚠️ Important:</strong> Flight times shown may not reflect real-time delays or early arrivals. 
              Flight data can be delayed by 15-30 minutes. Check airline websites for most current status.
            </div>
            
            <div className="details">
              <div className="detail-item">
                <span className="label">Flight arrives:</span>
                <span>{result.details.arrival_time}</span>
              </div>
              <div className="detail-item">
                <span className="label">Ready for pickup:</span>
                <span>{result.details.airport_exit_time}</span>
              </div>
              <div className="detail-item">
                <span className="label">Drive time:</span>
                <span>{result.details.drive_time_minutes} minutes</span>
              </div>
            </div>

            <details className="debug-section">
              <summary>Debug Info (click to expand)</summary>
              <div className="debug-content">
                <h4>Input Parameters:</h4>
                <pre>{JSON.stringify({
                  flight,
                  address,
                  airport_busy: airportBusy,
                  holiday: isHoliday,
                  checked_bags: hasCheckedBags
                }, null, 2)}</pre>
                
                <h4>Full API Response:</h4>
                <pre>{JSON.stringify(result, null, 2)}</pre>
                
                <h4>Request URL:</h4>
                <code>{import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000'}/when-to-leave?flight={encodeURIComponent(flight)}&address={encodeURIComponent(address)}&airport_busy={airportBusy}&holiday={isHoliday}&checked_bags={hasCheckedBags}</code>
              </div>
            </details>

          </div>
        )}
      </main>
    </div>
  )
}

export default App