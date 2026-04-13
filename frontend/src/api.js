/**
 * API client for the LLM Council backend.
 */

const API_BASE = 'http://localhost:8001';

export const api = {
  /**
   * List conversations, optionally filtered by archive status.
   */
  async listConversations(archived = false) {
    const response = await fetch(`${API_BASE}/api/conversations?archived=${archived}`);
    if (!response.ok) {
      throw new Error('Failed to list conversations');
    }
    return response.json();
  },

  /**
   * Create a new conversation.
   */
  async createConversation(councilModels = null, chairmanModel = null) {
    const body = {};
    if (councilModels) body.council_models = councilModels;
    if (chairmanModel) body.chairman_model = chairmanModel;

    const response = await fetch(`${API_BASE}/api/conversations`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      throw new Error('Failed to create conversation');
    }
    return response.json();
  },

  /**
   * Get a specific conversation.
   */
  async getConversation(conversationId) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}`
    );
    if (!response.ok) {
      throw new Error('Failed to get conversation');
    }
    return response.json();
  },

  /**
   * Send a message in a conversation.
   */
  async sendMessage(conversationId, content) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}/message`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ content }),
      }
    );
    if (!response.ok) {
      throw new Error('Failed to send message');
    }
    return response.json();
  },

  /**
   * Send a message and receive streaming updates.
   */
  async sendMessageStream(conversationId, content, onEvent) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}/message/stream`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ content }),
      }
    );

    if (!response.ok) {
      throw new Error('Failed to send message');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value);
      const lines = chunk.split('\n');

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6);
          try {
            const event = JSON.parse(data);
            onEvent(event.type, event);
          } catch (e) {
            console.error('Failed to parse SSE event:', e);
          }
        }
      }
    }
  },

  /**
   * Fetch available models from OpenRouter.
   */
  async listModels() {
    const response = await fetch(`${API_BASE}/api/models`);
    if (!response.ok) {
      throw new Error('Failed to fetch models');
    }
    return response.json();
  },

  /**
   * Get the current global council configuration.
   */
  async getConfig() {
    const response = await fetch(`${API_BASE}/api/config`);
    if (!response.ok) {
      throw new Error('Failed to get config');
    }
    return response.json();
  },

  /**
   * Update the global council configuration.
   */
  async updateConfig(councilModels, chairmanModel) {
    const body = {};
    if (councilModels !== undefined) body.council_models = councilModels;
    if (chairmanModel !== undefined) body.chairman_model = chairmanModel;

    const response = await fetch(`${API_BASE}/api/config`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      throw new Error('Failed to update config');
    }
    return response.json();
  },

  /**
   * Update a conversation's model configuration.
   */
  async updateConversationModels(conversationId, councilModels, chairmanModel) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}/models`,
      {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          council_models: councilModels,
          chairman_model: chairmanModel,
        }),
      }
    );
    if (!response.ok) {
      throw new Error('Failed to update conversation models');
    }
    return response.json();
  },

  /**
   * List all saved presets.
   */
  async listPresets() {
    const response = await fetch(`${API_BASE}/api/presets`);
    if (!response.ok) {
      throw new Error('Failed to list presets');
    }
    return response.json();
  },

  /**
   * Save a new preset.
   */
  async savePreset(name, councilModels, chairmanModel) {
    const response = await fetch(`${API_BASE}/api/presets`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        name,
        council_models: councilModels,
        chairman_model: chairmanModel,
      }),
    });
    if (!response.ok) {
      throw new Error('Failed to save preset');
    }
    return response.json();
  },

  /**
   * Delete a preset.
   */
  async deletePreset(presetId) {
    const response = await fetch(`${API_BASE}/api/presets/${presetId}`, {
      method: 'DELETE',
    });
    if (!response.ok) {
      throw new Error('Failed to delete preset');
    }
    return response.json();
  },

  /**
   * Delete a conversation.
   */
  async deleteConversation(conversationId) {
    const response = await fetch(`${API_BASE}/api/conversations/${conversationId}`, {
      method: 'DELETE',
    });
    if (!response.ok) {
      throw new Error('Failed to delete conversation');
    }
    return response.json();
  },

  /**
   * Archive or unarchive a conversation.
   */
  async archiveConversation(conversationId, archived) {
    const response = await fetch(`${API_BASE}/api/conversations/${conversationId}/archive`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ archived }),
    });
    if (!response.ok) {
      throw new Error('Failed to archive conversation');
    }
    return response.json();
  },

  /**
   * Export a conversation and trigger a download.
   */
  async exportConversation(conversationId, format) {
    const response = await fetch(`${API_BASE}/api/conversations/${conversationId}/export?format=${format}`);
    if (!response.ok) {
      throw new Error('Failed to export conversation');
    }
    const blob = await response.blob();
    const disposition = response.headers.get('Content-Disposition') || '';
    const filenameMatch = disposition.match(/filename="?([^"]+)"?/);
    const filename = filenameMatch ? filenameMatch[1] : `conversation.${format === 'markdown' ? 'md' : format}`;

    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  },
};
