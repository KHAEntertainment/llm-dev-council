import { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import Stage1 from './Stage1';
import Stage2 from './Stage2';
import Stage3 from './Stage3';
import ModelSelector from './ModelSelector';
import './ChatInterface.css';

export default function ChatInterface({
  conversation,
  onSendMessage,
  isLoading,
  councilModels,
  chairmanModel,
  onModelsChange,
  modelPricing,
}) {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [conversation]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (input.trim() && !isLoading) {
      onSendMessage(input);
      setInput('');
    }
  };

  const handleKeyDown = (e) => {
    // Submit on Enter (without Shift)
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  if (!conversation) {
    return (
      <div className="chat-interface">
        <div className="empty-state">
          <h2>Welcome to LLM Council</h2>
          <p>Create a new conversation to get started</p>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-interface">
      <div className="messages-container">
        {conversation.messages.length === 0 ? (
          <div className="empty-state">
            <h2>Start a conversation</h2>
            <p>Configure your council, then ask a question</p>
            <div className="empty-state-models">
              <ModelSelector
                councilModels={councilModels || []}
                chairmanModel={chairmanModel || ''}
                onModelsChange={onModelsChange}
                modelPricing={modelPricing}
                disabled={isLoading}
              />
            </div>
          </div>
        ) : (
          conversation.messages.map((msg, index) => (
            <div key={index} className="message-group">
              {msg.role === 'user' ? (
                <div className="user-message">
                  <div className="message-label">You</div>
                  <div className="message-content">
                    <div className="markdown-content">
                      <ReactMarkdown>{msg.content}</ReactMarkdown>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="assistant-message">
                  <div className="message-label">LLM Council</div>

                  {/* Stage 1 */}
                  {msg.loading?.stage1 && (
                    <div className="stage-loading">
                      <div className="spinner"></div>
                      <span>Running Stage 1: Collecting individual responses...</span>
                    </div>
                  )}
                  {msg.stage1 && <Stage1 responses={msg.stage1} />}

                  {/* Stage 2 */}
                  {msg.loading?.stage2 && (
                    <div className="stage-loading">
                      <div className="spinner"></div>
                      <span>Running Stage 2: Peer rankings...</span>
                    </div>
                  )}
                  {msg.stage2 && (
                    <Stage2
                      rankings={msg.stage2}
                      labelToModel={msg.metadata?.label_to_model}
                      aggregateRankings={msg.metadata?.aggregate_rankings}
                    />
                  )}

                  {/* Stage 3 */}
                  {msg.loading?.stage3 && (
                    <div className="stage-loading">
                      <div className="spinner"></div>
                      <span>Running Stage 3: Final synthesis...</span>
                    </div>
                  )}
                  {msg.stage3 && <Stage3 finalResponse={msg.stage3} />}

                  {/* Run Cost Summary */}
                  {msg.stage3 && modelPricing && councilModels.length > 0 && (
                    <RunCostSummary
                      councilModels={councilModels}
                      chairmanModel={chairmanModel}
                      modelPricing={modelPricing}
                    />
                  )}
                </div>
              )}
            </div>
          ))
        )}

        {isLoading && (
          <div className="loading-indicator">
            <div className="spinner"></div>
            <span>Consulting the council...</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {conversation.messages.length === 0 ? (
        <form className="input-form" onSubmit={handleSubmit}>
          <textarea
            className="message-input"
            placeholder="Ask your question... (Shift+Enter for new line, Enter to send)"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
            rows={3}
          />
          <button
            type="submit"
            className="send-button"
            disabled={!input.trim() || isLoading}
          >
            Send
          </button>
        </form>
      ) : (
        <div className="input-area">
          <ModelSelector
            councilModels={councilModels || []}
            chairmanModel={chairmanModel || ''}
            onModelsChange={onModelsChange}
            modelPricing={modelPricing}
            disabled={isLoading}
          />
          <form className="input-form compact" onSubmit={handleSubmit}>
            <textarea
              className="message-input"
              placeholder="Ask a follow-up... (Shift+Enter for new line, Enter to send)"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isLoading}
              rows={2}
            />
            <button
              type="submit"
              className="send-button"
              disabled={!input.trim() || isLoading}
            >
              Send
            </button>
          </form>
        </div>
      )}
    </div>
  );
}

function RunCostSummary({ councilModels, chairmanModel, modelPricing }) {
  const [showDetails, setShowDetails] = useState(false);

  // Council models: each queried in Stage 1 (1x) and Stage 2 (1x) = 2 prompts
  // Chairman: queried in Stage 3 (1x) + title gen (1x) = 2 prompts
  // Total: (councilModels * 2 + 2) prompt calls, same for completion
  const modelBreakdown = councilModels.map(id => {
    const p = modelPricing[id];
    if (!p) return null;
    const promptPer1M = parseFloat(p.prompt || '0') * 1e6;
    const completionPer1M = parseFloat(p.completion || '0') * 1e6;
    // 2 calls per council model (stage 1 + stage 2)
    return {
      id,
      promptPer1M,
      completionPer1M,
      calls: 2,
    };
  }).filter(Boolean);

  const chairmanBreakdown = chairmanModel && modelPricing[chairmanModel] ? (() => {
    const p = modelPricing[chairmanModel];
    return {
      id: chairmanModel,
      promptPer1M: parseFloat(p.prompt || '0') * 1e6,
      completionPer1M: parseFloat(p.completion || '0') * 1e6,
      calls: 2, // stage 3 + title
    };
  })() : null;

  const allCosts = [...modelBreakdown, chairmanBreakdown].filter(Boolean);
  const totalPromptPer1M = allCosts.reduce((sum, c) => sum + c.promptPer1M * c.calls, 0);
  const totalCompletionPer1M = allCosts.reduce((sum, c) => sum + c.completionPer1M * c.calls, 0);

  if (allCosts.length === 0) return null;

  return (
    <div className="run-cost-summary">
      <div className="run-cost-header" onClick={() => setShowDetails(v => !v)}>
        <span className="run-cost-label">Run Cost Estimate</span>
        <span className="run-cost-toggle">{showDetails ? '▲' : '▼'}</span>
      </div>
      <div className="run-cost-total">
        ~${totalPromptPer1M.toFixed(2)}M input / ${totalCompletionPer1M.toFixed(2)}M output per 1M tokens per run
      </div>
      {showDetails && (
        <div className="run-cost-details">
          {allCosts.map(c => (
            <div key={c.id} className="run-cost-row">
              <span className="run-cost-model">{c.id}</span>
              <span className="run-cost-calls">{c.calls}x calls</span>
              <span className="run-cost-pricing">${c.promptPer1M.toFixed(1)}M / ${c.completionPer1M.toFixed(1)}M</span>
            </div>
          ))}
          <div className="run-cost-note">
            Based on OpenRouter pricing. Actual cost depends on token usage per call.
          </div>
        </div>
      )}
    </div>
  );
}
