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
  async sendMessage(conversationId, content, attachments = null) {
    const body = { content };
    if (attachments && attachments.length > 0) body.attachments = attachments;

    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}/message`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
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
  async sendMessageStream(conversationId, content, onEvent, attachments = null, allowWrites = false, enableMcpTools = false) {
    const body = { content };
    if (attachments && attachments.length > 0) body.attachments = attachments;
    if (allowWrites) body.allow_writes = true;
    if (enableMcpTools) body.enable_mcp_tools = true;

    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}/message/stream`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
      }
    );

    if (!response.ok) {
      throw new Error('Failed to send message');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      // Keep the last (possibly incomplete) line in the buffer
      buffer = lines.pop() || '';

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

    // Process any remaining data in buffer
    if (buffer.startsWith('data: ')) {
      const data = buffer.slice(6);
      try {
        const event = JSON.parse(data);
        onEvent(event.type, event);
      } catch {
        // Incomplete frame at stream end, ignore
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

  // --- Filesystem API ---

  /**
   * Mount a folder path on the host filesystem.
   */
  async mountFolder(path) {
    const response = await fetch(`${API_BASE}/api/fs/mount`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path }),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || 'Failed to mount folder');
    }
    return response.json();
  },

  /**
   * Unmount a folder.
   */
  async unmountFolder(mountId) {
    const response = await fetch(`${API_BASE}/api/fs/mount/${mountId}`, {
      method: 'DELETE',
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || 'Failed to unmount folder');
    }
    return response.json();
  },

  /**
   * List current mounts.
   */
  async listMounts() {
    const response = await fetch(`${API_BASE}/api/fs/mounts`);
    if (!response.ok) throw new Error('Failed to list mounts');
    return response.json();
  },

  /**
   * Browse a directory within a mounted folder.
   */
  async browseDirectory(path) {
    const response = await fetch(`${API_BASE}/api/fs/browse?path=${encodeURIComponent(path)}`);
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || 'Failed to browse directory');
    }
    return response.json();
  },

  /**
   * Read a file from a mounted folder.
   */
  async readFile(path) {
    const response = await fetch(`${API_BASE}/api/fs/read?path=${encodeURIComponent(path)}`);
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || 'Failed to read file');
    }
    return response.json();
  },

  /**
   * Search files within mounted folders.
   */
  async searchFiles(path, pattern) {
    const response = await fetch(`${API_BASE}/api/fs/search?path=${encodeURIComponent(path)}&pattern=${encodeURIComponent(pattern)}`);
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || 'Failed to search files');
    }
    return response.json();
  },

  /**
   * Write a file to disk (chairman only, requires approval).
   */
  async writeFile(path, content, proposalId) {
    const response = await fetch(`${API_BASE}/api/fs/write`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, content, proposal_id: proposalId }),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || 'Failed to write file');
    }
    return response.json();
  },

  /**
   * Update mounted paths for a conversation.
   */
  async updateConversationMounts(conversationId, mountedPaths) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}/mounts`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mounted_paths: mountedPaths }),
      }
    );
    if (!response.ok) throw new Error('Failed to update conversation mounts');
    return response.json();
  },

  // --- GitHub Account API ---

  async getGithubStatus() {
    const response = await fetch(`${API_BASE}/api/account/github/status`);
    if (!response.ok) throw new Error('Failed to get GitHub status');
    return response.json();
  },

  async saveGithubToken(token) {
    const response = await fetch(`${API_BASE}/api/account/github/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || 'Failed to save GitHub token');
    }
    return response.json();
  },

  async disconnectGithub() {
    const response = await fetch(`${API_BASE}/api/account/github`, {
      method: 'DELETE',
    });
    if (!response.ok) throw new Error('Failed to disconnect GitHub');
    return response.json();
  },

  async startGithubOAuth(frontendRedirect = window.location.origin) {
    const response = await fetch(`${API_BASE}/api/account/github/oauth/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ frontend_redirect: frontendRedirect }),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || 'Failed to start GitHub OAuth');
    }
    return response.json();
  },

  // --- GitHub Repository Mount API ---

  async mountGithubRepo(conversationId, repo, ref = '', path = '') {
    const response = await fetch(`${API_BASE}/api/conversations/${conversationId}/github-mounts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        repo,
        ref: ref || null,
        path: path || null,
      }),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || 'Failed to mount GitHub repository');
    }
    return response.json();
  },

  async updateConversationGithubMounts(conversationId, githubMounts) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}/github-mounts`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ github_mounts: githubMounts }),
      }
    );
    if (!response.ok) throw new Error('Failed to update GitHub mounts');
    return response.json();
  },

  async listGithubMounts(conversationId) {
    const response = await fetch(`${API_BASE}/api/conversations/${conversationId}/github-mounts`);
    if (!response.ok) throw new Error('Failed to list GitHub mounts');
    return response.json();
  },

  async unmountGithubRepo(conversationId, mountId) {
    const response = await fetch(`${API_BASE}/api/conversations/${conversationId}/github-mounts/${mountId}`, {
      method: 'DELETE',
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || 'Failed to unmount GitHub repository');
    }
    return response.json();
  },

  async browseGithubRepo(conversationId, path) {
    const response = await fetch(`${API_BASE}/api/conversations/${conversationId}/github/browse?path=${encodeURIComponent(path)}`);
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || 'Failed to browse GitHub repository');
    }
    return response.json();
  },

  async readGithubFile(conversationId, path) {
    const response = await fetch(`${API_BASE}/api/conversations/${conversationId}/github/read?path=${encodeURIComponent(path)}`);
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || 'Failed to read GitHub file');
    }
    return response.json();
  },

  async searchGithubFiles(conversationId, path, pattern) {
    const response = await fetch(`${API_BASE}/api/conversations/${conversationId}/github/search?path=${encodeURIComponent(path)}&pattern=${encodeURIComponent(pattern)}`);
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || 'Failed to search GitHub files');
    }
    return response.json();
  },

  // --- MCP Server API ---

  async listMCPServers() {
    const response = await fetch(`${API_BASE}/api/mcp/servers`);
    if (!response.ok) throw new Error('Failed to list MCP servers');
    return response.json();
  },

  async createMCPServer(payload) {
    const response = await fetch(`${API_BASE}/api/mcp/servers`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || 'Failed to add MCP server');
    }
    return response.json();
  },

  async deleteMCPServer(serverId) {
    const response = await fetch(`${API_BASE}/api/mcp/servers/${serverId}`, {
      method: 'DELETE',
    });
    if (!response.ok) throw new Error('Failed to delete MCP server');
    return response.json();
  },

  async testMCPServer(serverId) {
    const response = await fetch(`${API_BASE}/api/mcp/servers/${serverId}/test`, {
      method: 'POST',
    });
    if (!response.ok) throw new Error('Failed to test MCP server');
    return response.json();
  },
};
