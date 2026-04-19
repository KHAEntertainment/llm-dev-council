import { useState, useEffect, useRef } from 'react';
import { api } from '../api';
import './ModelBrowserModal.css';

const SORT_OPTIONS = [
  { id: 'name', label: 'Name' },
  { id: 'context_length', label: 'Context' },
  { id: 'price', label: 'Price' },
];

export default function ModelBrowserModal({
  isOpen,
  onClose,
  onAddModel,
  onRemoveModel,
  onClearModels,
  onSelectModel,
  selectedModelIds = [],
  selectedModelId = null,
  mode = 'add',
  title = 'Add Model',
}) {
  const [models, setModels] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState('');
  const [sortField, setSortField] = useState('name');
  const [sortDir, setSortDir] = useState('asc');
  const [showFreeOnly, setShowFreeOnly] = useState(false);
  const searchRef = useRef(null);

  useEffect(() => {
    if (isOpen) {
      fetchModels();
      setSearch('');
      setTimeout(() => searchRef.current?.focus(), 100);
    }
  }, [isOpen]);

  const fetchModels = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listModels();
      setModels(data.models || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const filtered = models
    .filter((m) => {
      const q = search.toLowerCase();
      const matchesSearch = !q || m.name.toLowerCase().includes(q) || m.id.toLowerCase().includes(q);
      const isFree = m.pricing?.prompt === '0' && m.pricing?.completion === '0';
      const matchesPrice = !showFreeOnly || isFree;
      return matchesSearch && matchesPrice;
    })
    .sort((a, b) => {
      let va, vb;
      if (sortField === 'name') {
        va = a.name.toLowerCase();
        vb = b.name.toLowerCase();
        return sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
      } else if (sortField === 'context_length') {
        va = a.context_length || 0;
        vb = b.context_length || 0;
        return sortDir === 'asc' ? va - vb : vb - va;
      } else if (sortField === 'price') {
        va = parseFloat(a.pricing?.prompt || '999');
        vb = parseFloat(b.pricing?.prompt || '999');
        return sortDir === 'asc' ? va - vb : vb - va;
      }
      return 0;
    });

  const handleModelClick = (modelId) => {
    if (mode === 'add') {
      if (selectedModelIds.includes(modelId)) {
        onRemoveModel?.(modelId);
      } else {
        onAddModel(modelId);
      }
    } else if (mode === 'select') {
      onSelectModel(modelId);
      onClose();
    }
  };

  if (!isOpen) return null;

  const hasSelections = mode === 'add' ? selectedModelIds.length > 0 : !!selectedModelId;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-container" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{title}</h2>
          <button className="modal-close-btn" onClick={onClose}>&times;</button>
        </div>

        <div className="modal-toolbar">
          <input
            ref={searchRef}
            type="text"
            className="model-search-input"
            placeholder="Search models..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <div className="modal-toolbar-right">
            {SORT_OPTIONS.map((opt) => (
              <button
                key={opt.id}
                className={`sort-btn ${sortField === opt.id ? 'active' : ''}`}
                onClick={() => setSortField(opt.id)}
              >
                {opt.label}
              </button>
            ))}
            <button
              className="sort-btn"
              onClick={() => setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))}
              title="Toggle sort direction"
            >
              {sortDir === 'asc' ? '↑' : '↓'}
            </button>
            <button
              className={`sort-btn ${showFreeOnly ? 'active' : ''}`}
              onClick={() => setShowFreeOnly((v) => !v)}
            >
              {showFreeOnly ? 'Free' : 'All'}
            </button>
          </div>
        </div>

        {mode === 'add' && hasSelections && (
          <div className="modal-selection-bar">
            <span className="selection-count">{selectedModelIds.length} model{selectedModelIds.length !== 1 ? 's' : ''} selected</span>
            <button
              className="clear-selection-btn"
              onClick={() => onClearModels?.()}
            >
              Clear Selection
            </button>
          </div>
        )}

        <div className="modal-body">
          {loading && (
            <div className="modal-loading">
              <div className="spinner"></div>
              <span>Loading models from OpenRouter...</span>
            </div>
          )}
          {error && <div className="modal-error">Error: {error}</div>}
          {!loading && !error && (
            <div className="model-list">
              {filtered.length === 0 && (
                <div className="no-models">No models found</div>
              )}
              {filtered.map((model) => {
                const isFree = model.pricing?.prompt === '0' && model.pricing?.completion === '0';
                const isAdded = mode === 'add' && selectedModelIds.includes(model.id);
                const isSelected = mode === 'select' && selectedModelId === model.id;
                return (
                  <div
                    key={model.id}
                    className={`model-card ${isAdded ? 'selected' : ''} ${isSelected ? 'selected chairman-selected' : ''}`}
                    onClick={() => handleModelClick(model.id)}
                  >
                    <div className="model-card-header">
                      <span className="model-card-name">{model.name}</span>
                      <span className={`model-badge ${isFree ? 'free' : 'paid'}`}>
                        {isFree ? 'Free' : 'Paid'}
                      </span>
                      {isAdded && <span className="model-badge added">Added</span>}
                      {isSelected && <span className="model-badge chairman-badge">Chairman</span>}
                    </div>
                    <div className="model-card-id">{model.id}</div>
                    {model.description && (
                      <div className="model-card-desc">{model.description}</div>
                    )}
                    <div className="model-card-meta">
                      <span>Context: {(model.context_length || 0).toLocaleString()}</span>
                      {!isFree && (
                        <span>
                          {'$' + (parseFloat(model.pricing?.prompt || '0') * 1e6).toFixed(2) + ' / $' + (parseFloat(model.pricing?.completion || '0') * 1e6).toFixed(2) + ' per 1M tokens'}
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="modal-footer">
          {mode === 'select' ? (
            <button className="modal-done-btn" onClick={onClose}>Cancel</button>
          ) : (
            <button className="modal-done-btn" onClick={onClose}>
              {hasSelections ? 'Done' : 'Close'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
