import { useState, useEffect, useCallback } from 'react';
import { api } from '../api';
import './PresetManager.css';

export default function PresetManager({
  councilModels,
  chairmanModel,
  onApplyPreset,
  disabled,
}) {
  const [presets, setPresets] = useState([]);
  const [showSaveInput, setShowSaveInput] = useState(false);
  const [presetName, setPresetName] = useState('');

  const loadPresets = useCallback(async () => {
    try {
      const data = await api.listPresets();
      setPresets(data);
    } catch (err) {
      console.error('Failed to load presets:', err);
    }
  }, []);

  useEffect(() => {
    loadPresets();
  }, [loadPresets]);

  const handleSave = async () => {
    if (!presetName.trim() || councilModels.length === 0 || !chairmanModel) return;
    try {
      await api.savePreset(presetName.trim(), councilModels, chairmanModel);
      setPresetName('');
      setShowSaveInput(false);
      loadPresets();
    } catch (err) {
      console.error('Failed to save preset:', err);
    }
  };

  const handleDelete = async (presetId) => {
    try {
      await api.deletePreset(presetId);
      loadPresets();
    } catch (err) {
      console.error('Failed to delete preset:', err);
    }
  };

  const handleApply = (preset) => {
    onApplyPreset(preset.council_models, preset.chairman_model);
  };

  return (
    <div className="preset-manager">
      <div className="preset-header">
        <span className="preset-label">Saved Combinations</span>
        <button
          className="preset-save-btn"
          onClick={() => setShowSaveInput((v) => !v)}
          disabled={disabled || councilModels.length === 0 || !chairmanModel}
          title="Save current combination"
        >
          {showSaveInput ? 'Cancel' : 'Save'}
        </button>
      </div>

      {showSaveInput && (
        <div className="preset-save-form">
          <input
            type="text"
            className="preset-name-input"
            placeholder="Combination name..."
            value={presetName}
            onChange={(e) => setPresetName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSave()}
            autoFocus
          />
          <button
            className="preset-confirm-btn"
            onClick={handleSave}
            disabled={!presetName.trim()}
          >
            Save
          </button>
        </div>
      )}

      {presets.length === 0 && !showSaveInput && (
        <div className="preset-empty">No saved combinations yet</div>
      )}

      {presets.length > 0 && (
        <div className="preset-list">
          {presets.map((preset) => (
            <div key={preset.id} className="preset-item">
              <button className="preset-item-info" onClick={() => handleApply(preset)} disabled={disabled}>
                <span className="preset-item-name">{preset.name}</span>
                <span className="preset-item-meta">
                  {preset.council_models.length} models
                </span>
              </button>
              <button
                className="preset-item-delete"
                onClick={(e) => { e.stopPropagation(); handleDelete(preset.id); }}
                title="Delete preset"
              >
                &times;
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
