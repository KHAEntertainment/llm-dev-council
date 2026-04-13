import { useState, useEffect } from 'react';
import { api } from '../api';
import './FolderManager.css';

export default function FolderManager({ onMountsChange }) {
  const [mounts, setMounts] = useState([]);
  const [showInput, setShowInput] = useState(false);
  const [pathInput, setPathInput] = useState('');
  const [error, setError] = useState('');
  const [browsing, setBrowsing] = useState(null);
  const [browseEntries, setBrowseEntries] = useState([]);
  const [browseStack, setBrowseStack] = useState([]);

  const loadMounts = async () => {
    try {
      const data = await api.listMounts();
      setMounts(data);
    } catch (err) {
      console.error('Failed to load mounts:', err);
    }
  };

  useEffect(() => {
    loadMounts();
  }, []);

  const handleMount = async () => {
    if (!pathInput.trim()) return;
    setError('');
    try {
      await api.mountFolder(pathInput.trim());
      setPathInput('');
      setShowInput(false);
      // Reload mounts and notify parent in one pass
      const updated = await api.listMounts();
      setMounts(updated);
      if (onMountsChange) {
        onMountsChange(updated.map((m) => m.path));
      }
    } catch (err) {
      setError(err.message || 'Failed to mount folder');
    }
  };

  const handlePickFolder = async () => {
    if (typeof window.showDirectoryPicker === 'function') {
      try {
        const handle = await window.showDirectoryPicker({ mode: 'readwrite' });
        // Browser can't reveal absolute path; prompt user to type it
        const name = handle.name;
        const confirmed = prompt(
          `Selected folder: "${name}"\n\nThe browser cannot reveal the full path. Please paste the absolute path to this folder:`,
          ''
        );
        if (confirmed && confirmed.trim()) {
          setPathInput(confirmed.trim());
        }
        return true;
      } catch (err) {
        if (err.name !== 'AbortError') {
          console.error('Directory picker error:', err);
        }
        return false;
      }
    } else {
      return false;
    }
  };

  const handleUnmount = async (mountId) => {
    try {
      await api.unmountFolder(mountId);
      // Reload mounts and notify parent in one pass
      const updated = await api.listMounts();
      setMounts(updated);
      if (onMountsChange) {
        onMountsChange(updated.map((m) => m.path));
      }
    } catch (err) {
      console.error('Failed to unmount:', err);
    }
  };

  const handleBrowse = async (path) => {
    try {
      const entries = await api.browseDirectory(path);
      setBrowseEntries(entries);
      setBrowsing(path);
      setBrowseStack((prev) => [...prev, path]);
    } catch (err) {
      console.error('Failed to browse:', err);
    }
  };

  const handleBrowseBack = () => {
    const newStack = [...browseStack];
    newStack.pop();
    if (newStack.length > 0) {
      const prev = newStack[newStack.length - 1];
      setBrowseStack(newStack);
      api.browseDirectory(prev).then((entries) => {
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
    <div className="folder-manager">
      <div className="folder-manager-header">
        <span className="folder-manager-title">Mounted Folders</span>
        <button
          className="folder-mount-btn"
          onClick={async () => {
            if (typeof window.showDirectoryPicker === 'function') {
              const picked = await handlePickFolder();
              // Only show manual input if picker was cancelled/unavailable
              if (!picked) {
                setShowInput(true);
              }
            } else {
              setShowInput(true);
            }
          }}
          title="Mount a folder"
        >
          + Mount
        </button>
      </div>

      {showInput && (
        <div className="folder-mount-input-row">
          <input
            className="folder-path-input"
            type="text"
            placeholder="/absolute/path/to/folder"
            value={pathInput}
            onChange={(e) => setPathInput(e.target.value)}
            onKeyDown={handleKeyDown}
            autoFocus
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
        <div className="folder-empty">No folders mounted</div>
      )}

      <div className="folder-list">
        {mounts.map((m) => (
          <div key={m.mount_id} className="folder-item">
            <span className="folder-item-icon">&#128193;</span>
            <span className="folder-item-path" title={m.path}>
              {m.name}
            </span>
            <button
              className="folder-browse-btn"
              onClick={() => handleBrowse(m.path)}
              title="Browse files"
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