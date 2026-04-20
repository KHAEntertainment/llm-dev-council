import { useEffect, useState, useCallback } from 'react';
import { api } from '../api';
import './AccountGitHubSettings.css';

export default function AccountGitHubSettings() {
  const [status, setStatus] = useState(null);
  const [tokenInput, setTokenInput] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const loadStatus = useCallback(async () => {
    try {
      const data = await api.getGithubStatus();
      setStatus(data);
    } catch (err) {
      setError(err.message || 'Failed to load GitHub status');
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadStatus();
  }, [loadStatus]);

  const handleOAuth = async () => {
    setError('');
    setMessage('');
    try {
      const data = await api.startGithubOAuth(window.location.origin);
      window.open(data.authorization_url, '_blank', 'noopener,noreferrer');
      setMessage('Complete GitHub authorization in the browser, then refresh status.');
    } catch (err) {
      setError(err.message || 'Failed to start GitHub OAuth');
    }
  };

  const handleSaveToken = async () => {
    if (!tokenInput.trim()) return;
    setError('');
    setMessage('');
    try {
      const data = await api.saveGithubToken(tokenInput.trim());
      setStatus(data);
      setTokenInput('');
      setMessage('GitHub token saved locally.');
    } catch (err) {
      setError(err.message || 'Failed to save GitHub token');
    }
  };

  const handleDisconnect = async () => {
    setError('');
    setMessage('');
    try {
      const data = await api.disconnectGithub();
      setStatus(data);
      setMessage('Stored GitHub token removed.');
    } catch (err) {
      setError(err.message || 'Failed to disconnect GitHub');
    }
  };

  return (
    <div className="account-github-settings">
      <div className="account-status-row">
        <span className="account-status-label">Connection</span>
        <span className={`account-status-value ${status?.connected ? 'connected' : ''}`}>
          {status?.connected ? 'Connected' : 'Not connected'}
        </span>
      </div>
      <div className="account-status-row">
        <span className="account-status-label">Token source</span>
        <span className="account-status-value">{status?.token_source || 'None'}</span>
      </div>
      <div className="account-status-row">
        <span className="account-status-label">Copilot models</span>
        <span className="account-status-value">{status?.copilot_available ? 'Available' : 'Hidden'}</span>
      </div>
      {status?.login && (
        <div className="account-status-row">
          <span className="account-status-label">GitHub user</span>
          <span className="account-status-value">{status.login}</span>
        </div>
      )}

      <div className="account-actions">
        <button className="account-primary-btn" onClick={handleOAuth}>
          Connect GitHub
        </button>
        <button className="account-secondary-btn" onClick={loadStatus}>
          Refresh
        </button>
        <button className="account-danger-btn" onClick={handleDisconnect} disabled={!status?.stored_token}>
          Disconnect
        </button>
      </div>

      <div className="account-token-box">
        <label htmlFor="github-token-input">Headless token fallback</label>
        <div className="account-token-row">
          <input
            id="github-token-input"
            type="password"
            value={tokenInput}
            onChange={(e) => setTokenInput(e.target.value)}
            placeholder="GitHub token"
          />
          <button className="account-secondary-btn" onClick={handleSaveToken}>
            Save
          </button>
        </div>
        <p>
          Environment tokens use COPILOT_GITHUB_TOKEN, GH_TOKEN, or GITHUB_TOKEN and are never shown here.
        </p>
      </div>

      {message && <div className="account-message">{message}</div>}
      {error && <div className="account-error">{error}</div>}
    </div>
  );
}
