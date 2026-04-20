import { useState, useEffect, useCallback } from 'react';
import { api } from '../api';
import './FolderManager.css';
import './GitHubRepoManager.css';

function mountRootPath(mount) {
  const base = `github://${mount.owner}/${mount.repo}@${mount.ref}`;
  return mount.path ? `${base}/${mount.path}` : base;
}

export default function GitHubRepoManager({
  conversationId,
  githubMounts = [],
  onGithubMountsChange,
}) {
  const [mounts, setMounts] = useState(githubMounts);
  const [showInput, setShowInput] = useState(false);
  const [repoInput, setRepoInput] = useState('');
  const [refInput, setRefInput] = useState('');
  const [pathInput, setPathInput] = useState('');
  const [error, setError] = useState('');
  const [browsing, setBrowsing] = useState(null);
  const [browseEntries, setBrowseEntries] = useState([]);
  const [browseStack, setBrowseStack] = useState([]);

  const loadMounts = useCallback(async () => {
    if (!conversationId) {
      setMounts([]);
      return;
    }
    try {
      const data = await api.listGithubMounts(conversationId);
      setMounts(data);
    } catch (err) {
      console.error('Failed to load GitHub mounts:', err);
      setMounts(githubMounts);
    }
  }, [conversationId, githubMounts]);

  useEffect(() => {
    setMounts(githubMounts);
  }, [githubMounts]);

  useEffect(() => {
    loadMounts();
  }, [loadMounts]);

  const publishMounts = (updated) => {
    setMounts(updated);
    if (onGithubMountsChange) {
      onGithubMountsChange(updated);
    }
  };

  const handleMount = async () => {
    if (!repoInput.trim() || !conversationId) return;
    setError('');
    try {
      await api.mountGithubRepo(
        conversationId,
        repoInput.trim(),
        refInput.trim(),
        pathInput.trim()
      );
      const updated = await api.listGithubMounts(conversationId);
      setRepoInput('');
      setRefInput('');
      setPathInput('');
      setShowInput(false);
      publishMounts(updated);
    } catch (err) {
      setError(err.message || 'Failed to mount GitHub repository');
    }
  };

  const handleUnmount = async (mountId) => {
    if (!conversationId) return;
    try {
      await api.unmountGithubRepo(conversationId, mountId);
      const updated = await api.listGithubMounts(conversationId);
      publishMounts(updated);
    } catch (err) {
      setError(err.message || 'Failed to unmount GitHub repository');
    }
  };

  const handleBrowse = async (path) => {
    if (!conversationId) return;
    try {
      const entries = await api.browseGithubRepo(conversationId, path);
      setBrowseEntries(entries);
      setBrowsing(path);
      setBrowseStack((prev) => [...prev, path]);
    } catch (err) {
      setError(err.message || 'Failed to browse GitHub repository');
    }
  };

  const handleBrowseBack = () => {
    const newStack = [...browseStack];
    newStack.pop();
    if (newStack.length > 0) {
      const prev = newStack[newStack.length - 1];
      setBrowseStack(newStack);
      api.browseGithubRepo(conversationId, prev).then((entries) => {
        setBrowseEntries(entries);
        setBrowsing(prev);
      }).catch((err) => {
        console.error('Failed to browse back:', err);
        setBrowsing(null);
        setBrowseEntries([]);
        setBrowseStack([]);
      });
    } else {
      setBrowsing(null);
      setBrowseEntries([]);
      setBrowseStack([]);
    }
  };

  const closeBrowser = () => {
    setBrowsing(null);
    setBrowseEntries([]);
    setBrowseStack([]);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleMount();
    }
    if (e.key === 'Escape') {
      setShowInput(false);
      setError('');
    }
  };

  return (
    <div className="github-repo-manager">
      <div className="folder-manager-header">
        <span className="folder-manager-title">GitHub Repos</span>
        <button
          className="folder-mount-btn"
          onClick={() => setShowInput(true)}
          title="Mount a GitHub repository"
          disabled={!conversationId}
        >
          + Repo
        </button>
      </div>

      {showInput && (
        <div className="github-repo-input">
          <input
            className="folder-path-input"
            type="text"
            placeholder="owner/repo"
            value={repoInput}
            onChange={(e) => setRepoInput(e.target.value)}
            onKeyDown={handleKeyDown}
            autoFocus
          />
          <input
            className="folder-path-input github-short-input"
            type="text"
            placeholder="ref"
            value={refInput}
            onChange={(e) => setRefInput(e.target.value)}
            onKeyDown={handleKeyDown}
          />
          <input
            className="folder-path-input github-short-input"
            type="text"
            placeholder="path"
            value={pathInput}
            onChange={(e) => setPathInput(e.target.value)}
            onKeyDown={handleKeyDown}
          />
          <button className="folder-mount-confirm" onClick={handleMount}>
            Mount
          </button>
          <button className="folder-mount-cancel" onClick={() => { setShowInput(false); setError(''); }}>
            Cancel
          </button>
        </div>
      )}

      {error && <div className="folder-error">{error}</div>}

      {mounts.length === 0 && !showInput && (
        <div className="folder-empty">No repositories mounted</div>
      )}

      <div className="folder-list">
        {mounts.map((m) => (
          <div key={m.mount_id} className="folder-item">
            <span className="folder-item-icon">GH</span>
            <span className="folder-item-path" title={m.display_name || mountRootPath(m)}>
              {m.display_name || `${m.owner}/${m.repo}@${m.ref}`}
            </span>
            <span className="github-readonly">Read-only</span>
            <button
              className="folder-browse-btn"
              onClick={() => handleBrowse(mountRootPath(m))}
              title="Browse repository"
            >
              Browse
            </button>
            <button
              className="folder-unmount-btn"
              onClick={() => handleUnmount(m.mount_id)}
              title="Unmount"
            >
              &times;
            </button>
          </div>
        ))}
      </div>

      {browsing && (
        <div className="folder-browser-overlay">
          <div className="folder-browser">
            <div className="folder-browser-header">
              <button className="folder-browser-back" onClick={handleBrowseBack} disabled={browseStack.length <= 1}>
                &#8592;
              </button>
              <span className="folder-browser-path">{browsing}</span>
              <button className="folder-browser-close" onClick={closeBrowser}>&times;</button>
            </div>
            <div className="folder-browser-entries">
              {browseEntries.map((entry) => (
                <div
                  key={entry.path}
                  className={`folder-browser-entry ${entry.type}`}
                  onClick={() => entry.type === 'directory' && handleBrowse(entry.path)}
                >
                  <span className="entry-icon">
                    {entry.type === 'directory' ? '\u{1F4C1}' : '\u{1F4C4}'}
                  </span>
                  <span className="entry-name">{entry.name}</span>
                  {entry.size != null && (
                    <span className="entry-size">
                      {entry.size < 1024
                        ? `${entry.size} B`
                        : entry.size < 1048576
                        ? `${(entry.size / 1024).toFixed(1)} KB`
                        : `${(entry.size / 1048576).toFixed(1)} MB`}
                    </span>
                  )}
                </div>
              ))}
              {browseEntries.length === 0 && (
                <div className="folder-browser-empty">Empty directory</div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
