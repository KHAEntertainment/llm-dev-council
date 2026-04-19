import { useState } from 'react';
import ModelBrowserModal from './ModelBrowserModal';
import PresetManager from './PresetManager';
import './ModelSelector.css';

function getModelDisplayName(modelId) {
  const parts = modelId.split('/');
  const name = parts.length > 1 ? parts[1] : parts[0];
  return name
    .replace(/-/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatPricePer1M(pricePerToken) {
  const per1M = parseFloat(pricePerToken) * 1e6;
  if (per1M === 0) return 'Free';
  if (per1M < 0.1) return '<$0.10';
  return '$' + per1M.toFixed(2);
}

export default function ModelSelector({
  councilModels,
  chairmanModel,
  onModelsChange,
  modelPricing,
  disabled,
}) {
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [chairmanModalOpen, setChairmanModalOpen] = useState(false);
  const [showCosts, setShowCosts] = useState(false);

  const handleAddModel = (modelId) => {
    if (!councilModels.includes(modelId)) {
      const newModels = [...councilModels, modelId];
      onModelsChange(newModels, chairmanModel);
    }
  };

  const handleRemoveModel = (modelId) => {
    const newModels = councilModels.filter((m) => m !== modelId);
    let newChairman = chairmanModel;
    if (chairmanModel === modelId) {
      newChairman = newModels.length > 0 ? newModels[0] : '';
    }
    onModelsChange(newModels, newChairman);
  };

  const handleClearModels = () => {
    onModelsChange([], '');
  };

  const handleSelectChairman = (modelId) => {
    onModelsChange(councilModels, modelId);
  };

  // Calculate combined cost
  const costSummary = (() => {
    if (!modelPricing || councilModels.length === 0) return null;
    let totalPrompt = 0;
    let totalCompletion = 0;
    let counted = 0;
    councilModels.forEach(id => {
      const p = modelPricing[id];
      if (p) {
        totalPrompt += parseFloat(p.prompt || '0');
        totalCompletion += parseFloat(p.completion || '0');
        counted++;
      }
    });
    // Add chairman (used for stage 3 + title gen)
    const chairmanP = modelPricing[chairmanModel];
    if (chairmanP) {
      totalPrompt += parseFloat(chairmanP.prompt || '0');
      totalCompletion += parseFloat(chairmanP.completion || '0');
    }
    if (counted === 0) return null;
    return {
      promptPer1M: (totalPrompt * 1e6).toFixed(2),
      completionPer1M: (totalCompletion * 1e6).toFixed(2),
      modelCount: counted,
    };
  })();

  return (
    <div className="model-selector">
      <div className="model-selector-row">
        <div className="model-selector-label">Council Members</div>
        <div className="model-selector-actions">
          {councilModels.length > 0 && (
            <button className="clear-btn" onClick={handleClearModels} disabled={disabled}>
              Clear
            </button>
          )}
          <button
            className={`cost-toggle-btn ${showCosts ? 'active' : ''}`}
            onClick={() => setShowCosts(v => !v)}
            disabled={councilModels.length === 0}
          >
            {showCosts ? 'Hide Costs' : 'Show Costs'}
          </button>
        </div>
      </div>
      <div className="model-chips">
        {councilModels.map((modelId) => (
          <span key={modelId} className={`model-chip ${modelId === chairmanModel ? 'is-chairman' : ''}`}>
            <span className="chip-name">{getModelDisplayName(modelId)}</span>
            <span className="chip-id" title={modelId}>{modelId}</span>
            {showCosts && modelPricing?.[modelId] && (
              <span className="chip-cost">
                {formatPricePer1M(modelPricing[modelId].prompt)}/{formatPricePer1M(modelPricing[modelId].completion)}
              </span>
            )}
            {modelId === chairmanModel && <span className="chip-chairman-badge">Chair</span>}
            <button
              className="chip-remove"
              onClick={() => handleRemoveModel(modelId)}
              disabled={disabled}
              title="Remove model"
            >
              &times;
            </button>
          </span>
        ))}
        <button
          className="add-model-btn"
          onClick={() => setAddModalOpen(true)}
          disabled={disabled}
        >
          + Add Model
        </button>
      </div>

      {showCosts && costSummary && (
        <div className="cost-summary">
          <span>Combined: ${costSummary.promptPer1M} input / ${costSummary.completionPer1M} output per 1M tokens (all models + chairman)</span>
        </div>
      )}

      {councilModels.length > 0 && (
        <div className="chairman-selector">
          <span className="chairman-label">Chairman</span>
          <button
            className="chairman-chip"
            onClick={() => setChairmanModalOpen(true)}
            disabled={disabled}
          >
            {chairmanModel ? (
              <>
                <span className="chairman-chip-name">{getModelDisplayName(chairmanModel)}</span>
                <span className="chairman-chip-id">{chairmanModel}</span>
                {showCosts && modelPricing?.[chairmanModel] && (
                  <span className="chip-cost">
                    {formatPricePer1M(modelPricing[chairmanModel].prompt)}/{formatPricePer1M(modelPricing[chairmanModel].completion)}
                  </span>
                )}
              </>
            ) : (
              'Select Chairman'
            )}
          </button>
        </div>
      )}

      <ModelBrowserModal
        isOpen={addModalOpen}
        onClose={() => setAddModalOpen(false)}
        onAddModel={handleAddModel}
        onRemoveModel={handleRemoveModel}
        onClearModels={handleClearModels}
        selectedModelIds={councilModels}
        mode="add"
        title="Add Council Model"
      />

      <ModelBrowserModal
        isOpen={chairmanModalOpen}
        onClose={() => setChairmanModalOpen(false)}
        onSelectModel={handleSelectChairman}
        selectedModelId={chairmanModel}
        mode="select"
        title="Select Chairman"
      />

      <PresetManager
        councilModels={councilModels}
        chairmanModel={chairmanModel}
        onApplyPreset={(models, chairman) => onModelsChange(models, chairman)}
        disabled={disabled}
      />
    </div>
  );
}
