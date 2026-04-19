import { useState, useEffect } from 'react';
import { api } from '../api';
import './MCPManager.css';

export default function MCPManager() {
  const [servers, setServers] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [advancedMode, setAdvancedMode] = useState(false);
  const [testingId, setTestingId] = useState(null);
  const [error, setError] = useState('');

  // Form state
  const [form, setForm] = useState({
    name: '',
    transport: 'sse',
    scope: 'council',
    enabled: true,
    url: '',
    headers: [],
    auth_token: '',
    advancedJson: '',
  });

  const loadServers = async () => {
    try {
      const data = await api.listMCPServers();
      setServers(data);
    } catch (err) {
      console.error('Failed to load MCP servers:', err);
    }
  };

  useEffect(() => {
    loadServers();
  }, []);

  const resetForm = () => {
    setForm({
      name: '',
      transport: 'sse',
      scope: 'council',
      enabled: true,
      url: '',
      headers: [],
      auth_token: '',
      advancedJson: '',
    });
    setError('');
  };

  const handleAdd = () => {
    resetForm();
    setShowForm(true);
  };

  const handleCancel = () => {
    setShowForm(false);
    resetForm();
  };

  const addHeader = () => {
    setForm((prev) => ({ ...prev, headers: [...prev.headers, { key: '', value: '' }] }));
  };

  const updateHeader = (index, field, value) => {
    setForm((prev) => {
      const headers = [...prev.headers];
      headers[index] = { ...headers[index], [field]: value };
      return { ...prev, headers };
    });
  };

  const removeHeader = (index) => {
    setForm((prev) => ({
      ...prev,
      headers: prev.headers.filter((_, i) => i !== index),
    }));
  };

  const buildPayload = () => {
    if (advancedMode) {
      try {
        const parsed = JSON.parse(form.advancedJson);
        return {
          name: form.name,
          transport: 'stdio',
          scope: form.scope,
          enabled: form.enabled,
          ...parsed,
        };
      } catch (e) {
        throw new Error('Invalid JSON in advanced config: ' + e.message);
      }
    }

    const headers = {};
    form.headers.forEach((h) => {
      if (h.key.trim()) headers[h.key.trim()] = h.value;
    });

    return {
      name: form.name,
      transport: form.transport,
      scope: form.scope,
      enabled: form.enabled,
      url: form.url || undefined,
      headers: Object.keys(headers).length > 0 ? headers : undefined,
      auth_token: form.auth_token || undefined,
    };
  };

  const handleSubmit = async () => {
    if (!form.name.trim()) {
      setError('Name is required');
      return;
    }
    setError('');
    try {
      const payload = buildPayload();
      await api.createMCPServer(payload);
      setShowForm(false);
      resetForm();
      await loadServers();
    } catch (err) {
      setError(err.message || 'Failed to add server');
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this MCP server?')) return;
    try {
      await api.deleteMCPServer(id);
      await loadServers();
    } catch (err) {
      console.error('Failed to delete MCP server:', err);
    }
  };

  const handleTest = async (id) => {
    setTestingId(id);
    try {
      const result = await api.testMCPServer(id);
      alert(result.connected
        ? `Connected! ${result.tool_count} tool(s) available.`
        : `Connection failed: ${result.error}`
      );
    } catch (err) {
      alert('Test failed: ' + (err.message || 'Unknown error'));
    } finally {
      setTestingId(null);
    }
  };

  const transportLabel = (t) => {
    if (t === 'streamable_http') return 'HTTP';
    return t.toUpperCase();
  };

  return (
    <div className="mcp-manager">
      <div className="mcp-manager-header">
        <span className="mcp-manager-title">MCP Servers</span>
        <button className="mcp-add-btn" onClick={handleAdd} title="Add MCP server">
          + Add
        </button>
      </div>

      {showForm && (
        <div className="mcp-form">
          <div className="mcp-form-mode-toggle">
            <button
              className={!advancedMode ? 'active' : ''}
              onClick={() => setAdvancedMode(false)}
            >
              Simple
            </button>
            <button
              className={advancedMode ? 'active' : ''}
              onClick={() => setAdvancedMode(true)}
            >
              Advanced
            </button>
          </div>

          <div className="mcp-form-row">
            <label>Name</label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
              placeholder="e.g. Memory Server"
            />
          </div>

          {!advancedMode && (
            <>
              <div className="mcp-form-row">
                <label>Transport</label>
                <select
                  value={form.transport}
                  onChange={(e) => setForm((p) => ({ ...p, transport: e.target.value }))}
                >
                  <option value="sse">SSE</option>
                  <option value="streamable_http">HTTP</option>
                </select>
              </div>

              <div className="mcp-form-row">
                <label>URL</label>
                <input
                  type="text"
                  value={form.url}
                  onChange={(e) => setForm((p) => ({ ...p, url: e.target.value }))}
                  placeholder="http://localhost:3001/sse"
                />
              </div>

              <div className="mcp-form-row">
                <label>Headers</label>
                <div className="mcp-headers">
                  {form.headers.map((h, i) => (
                    <div className="mcp-header-row" key={i}>
                      <input
                        type="text"
                        placeholder="Key"
                        value={h.key}
                        onChange={(e) => updateHeader(i, 'key', e.target.value)}
                      />
                      <input
                        type="text"
                        placeholder="Value"
                        value={h.value}
                        onChange={(e) => updateHeader(i, 'value', e.target.value)}
                      />
                      <button onClick={() => removeHeader(i)}>×</button>
                    </div>
                  ))}
                  <button className="mcp-add-header" onClick={addHeader}>
                    + Add header
                  </button>
                </div>
              </div>

              <div className="mcp-form-row">
                <label>Bearer Token</label>
                <input
                  type="password"
                  value={form.auth_token}
                  onChange={(e) => setForm((p) => ({ ...p, auth_token: e.target.value }))}
                  placeholder="Optional OAuth token"
                />
              </div>
            </>
          )}

          {advancedMode && (
            <div className="mcp-form-row">
              <label>Stdio Config (JSON)</label>
              <textarea
                rows={6}
                value={form.advancedJson}
                onChange={(e) => setForm((p) => ({ ...p, advancedJson: e.target.value }))}
                placeholder={'{\n  "command": "npx",\n  "args": ["-y", "@anthropic/memory-server"],\n  "env": {}\n}'}
              />
            </div>
          )}

          <div className="mcp-form-row">
            <label>Scope</label>
            <div className="mcp-scope-toggle">
              <button
                className={form.scope === 'council' ? 'active' : ''}
                onClick={() => setForm((p) => ({ ...p, scope: 'council' }))}
              >
                Entire Council
              </button>
              <button
                className={form.scope === 'chairman' ? 'active' : ''}
                onClick={() => setForm((p) => ({ ...p, scope: 'chairman' }))}
              >
                Chairman Only
              </button>
            </div>
          </div>

          {error && <div className="mcp-form-error">{error}</div>}

          <div className="mcp-form-actions">
            <button className="mcp-submit-btn" onClick={handleSubmit}>
              Save
            </button>
            <button className="mcp-cancel-btn" onClick={handleCancel}>
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="mcp-server-list">
        {servers.length === 0 && !showForm && (
          <div className="mcp-empty">No MCP servers configured</div>
        )}
        {servers.map((s) => (
          <div key={s.id} className={`mcp-server-item ${!s.enabled ? 'disabled' : ''}`}>
            <div className="mcp-server-info">
              <div className="mcp-server-name">{s.name}</div>
              <div className="mcp-server-meta">
                <span className="mcp-badge transport">{transportLabel(s.transport)}</span>
                <span className={`mcp-badge scope ${s.scope}`}>{s.scope}</span>
                {s.url && <span className="mcp-badge url">{s.url}</span>}
              </div>
            </div>
            <div className="mcp-server-actions">
              <button
                className="mcp-test-btn"
                onClick={() => handleTest(s.id)}
                disabled={testingId === s.id}
              >
                {testingId === s.id ? 'Testing…' : 'Test'}
              </button>
              <button className="mcp-delete-btn" onClick={() => handleDelete(s.id)}>
                ×
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
