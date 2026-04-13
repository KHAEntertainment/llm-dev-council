import { useState, useEffect } from 'react';
import Sidebar from './components/Sidebar';
import ChatInterface from './components/ChatInterface';
import { api } from './api';
import './App.css';

function App() {
  const [conversations, setConversations] = useState([]);
  const [currentConversationId, setCurrentConversationId] = useState(null);
  const [currentConversation, setCurrentConversation] = useState(null);
  const [isLoading, setIsLoading] = useState(false);

  // Per-conversation model config state
  const [councilModels, setCouncilModels] = useState([]);
  const [chairmanModel, setChairmanModel] = useState('');

  // Default config from server
  const [defaultConfig, setDefaultConfig] = useState(null);

  // Model pricing data (id -> {prompt, completion} per token)
  const [modelPricing, setModelPricing] = useState({});

  // Archive view state
  const [showArchived, setShowArchived] = useState(false);

  // Mounted folder paths for current conversation
  const [mountedPaths, setMountedPaths] = useState([]);

  // Pending write proposals from chairman
  const [pendingWrites, setPendingWrites] = useState(null);

  const handleToggleArchived = () => {
    setShowArchived((prev) => !prev);
  };

  // Reload conversations when archive toggle changes
  useEffect(() => {
    loadConversations();
  }, [showArchived]);

  // Load conversations and default config on mount
  useEffect(() => {
    loadConversations();
    loadDefaultConfig();
    loadModelPricing();
  }, []);

  const loadModelPricing = async () => {
    try {
      const data = await api.listModels();
      const pricing = {};
      (data.models || []).forEach(m => {
        pricing[m.id] = m.pricing;
      });
      setModelPricing(pricing);
    } catch (error) {
      console.error('Failed to load model pricing:', error);
    }
  };

  const loadDefaultConfig = async () => {
    try {
      const config = await api.getConfig();
      setDefaultConfig(config);
      // If no conversation is selected, use defaults
      if (!currentConversationId) {
        setCouncilModels(config.council_models || []);
        setChairmanModel(config.chairman_model || '');
      }
    } catch (error) {
      console.error('Failed to load default config:', error);
    }
  };

  // Load conversation details when selected
  useEffect(() => {
    if (currentConversationId) {
      loadConversation(currentConversationId);
    }
  }, [currentConversationId]);

  const loadConversations = async () => {
    try {
      const convs = await api.listConversations(showArchived);
      setConversations(convs);
      // Clear current conversation if it no longer exists in the list
      if (currentConversationId && !convs.find(c => c.id === currentConversationId)) {
        setCurrentConversationId(null);
        setCurrentConversation(null);
      }
    } catch (error) {
      console.error('Failed to load conversations:', error);
    }
  };

  const loadConversation = async (id) => {
    try {
      const conv = await api.getConversation(id);
      setCurrentConversation(conv);
      // Load this conversation's model config
      const models = conv.council_models || defaultConfig?.council_models || [];
      const chairman = conv.chairman_model || defaultConfig?.chairman_model || '';
      setCouncilModels(models);
      setChairmanModel(chairman);
      // Load mounted paths
      setMountedPaths(conv.mounted_paths || []);
    } catch (error) {
      console.error('Failed to load conversation:', error);
    }
  };

  const handleNewConversation = async () => {
    try {
      // Use current model config for the new conversation
      const models = councilModels.length > 0 ? councilModels : (defaultConfig?.council_models || null);
      const chairman = chairmanModel || (defaultConfig?.chairman_model || null);
      const newConv = await api.createConversation(models, chairman);
      setConversations([
        { id: newConv.id, created_at: newConv.created_at, message_count: 0, title: 'New Conversation' },
        ...conversations,
      ]);
      setCurrentConversationId(newConv.id);
    } catch (error) {
      console.error('Failed to create conversation:', error);
    }
  };

  const handleSelectConversation = (id) => {
    setCurrentConversationId(id);
  };

  const handleModelsChange = async (newModels, newChairman) => {
    setCouncilModels(newModels);
    setChairmanModel(newChairman);

    // If we have a current conversation, update its model config on the server
    if (currentConversationId && newModels.length > 0 && newChairman) {
      try {
        await api.updateConversationModels(currentConversationId, newModels, newChairman);
      } catch (error) {
        console.error('Failed to update conversation models:', error);
      }
    }
  };

  const handleMountsChange = async (newMounts) => {
    setMountedPaths(newMounts);
    if (currentConversationId) {
      try {
        await api.updateConversationMounts(currentConversationId, newMounts);
      } catch (error) {
        console.error('Failed to update conversation mounts:', error);
      }
    }
  };

  const handleApproveWrites = async (approvedWrites) => {
    for (const write of approvedWrites) {
      try {
        await api.writeFile(write.path, write.content);
      } catch (error) {
        console.error('Failed to write file:', error);
      }
    }
    setPendingWrites(null);
  };

  const handleRejectWrites = () => {
    setPendingWrites(null);
  };

  const handleSendMessage = async (content, attachments = null, allowWrites = false) => {
    if (!currentConversationId) return;

    setIsLoading(true);
    try {
      // Optimistically add user message to UI
      const userMessage = { role: 'user', content, attachments: attachments || undefined };
      setCurrentConversation((prev) => ({
        ...prev,
        messages: [...prev.messages, userMessage],
      }));

      // Create a partial assistant message that will be updated progressively
      const assistantMessage = {
        role: 'assistant',
        stage1: null,
        stage2: null,
        stage3: null,
        metadata: null,
        loading: {
          stage1: false,
          stage2: false,
          stage3: false,
        },
      };

      // Add the partial assistant message
      setCurrentConversation((prev) => ({
        ...prev,
        messages: [...prev.messages, assistantMessage],
      }));

      // Send message with streaming
      await api.sendMessageStream(currentConversationId, content, (eventType, event) => {
        switch (eventType) {
          case 'stage1_start':
            setCurrentConversation((prev) => {
              const messages = [...prev.messages];
              const lastMsg = messages[messages.length - 1];
              lastMsg.loading.stage1 = true;
              return { ...prev, messages };
            });
            break;

          case 'stage1_complete':
            setCurrentConversation((prev) => {
              const messages = [...prev.messages];
              const lastMsg = messages[messages.length - 1];
              lastMsg.stage1 = event.data;
              lastMsg.loading.stage1 = false;
              return { ...prev, messages };
            });
            break;

          case 'stage2_start':
            setCurrentConversation((prev) => {
              const messages = [...prev.messages];
              const lastMsg = messages[messages.length - 1];
              lastMsg.loading.stage2 = true;
              return { ...prev, messages };
            });
            break;

          case 'stage2_complete':
            setCurrentConversation((prev) => {
              const messages = [...prev.messages];
              const lastMsg = messages[messages.length - 1];
              lastMsg.stage2 = event.data;
              lastMsg.metadata = event.metadata;
              lastMsg.loading.stage2 = false;
              return { ...prev, messages };
            });
            break;

          case 'stage3_start':
            setCurrentConversation((prev) => {
              const messages = [...prev.messages];
              const lastMsg = messages[messages.length - 1];
              lastMsg.loading.stage3 = true;
              return { ...prev, messages };
            });
            break;

          case 'stage3_complete':
            setCurrentConversation((prev) => {
              const messages = [...prev.messages];
              const lastMsg = messages[messages.length - 1];
              lastMsg.stage3 = event.data;
              lastMsg.loading.stage3 = false;
              return { ...prev, messages };
            });
            // Check for proposed writes from chairman
            if (event.data?.proposed_writes?.length > 0) {
              setPendingWrites(event.data.proposed_writes);
            }
            break;

          case 'title_complete':
            // Reload conversations to get updated title
            loadConversations();
            break;

          case 'complete':
            // Stream complete, reload conversations list
            loadConversations();
            setIsLoading(false);
            break;

          case 'error':
            console.error('Stream error:', event.message);
            setIsLoading(false);
            break;

          default:
            console.log('Unknown event type:', eventType);
        }
      }, attachments, allowWrites);
    } catch (error) {
      console.error('Failed to send message:', error);
      // Remove optimistic messages on error
      setCurrentConversation((prev) => ({
        ...prev,
        messages: prev.messages.slice(0, -2),
      }));
      setIsLoading(false);
    }
  };

  return (
    <div className="app">
      <Sidebar
        conversations={conversations}
        currentConversationId={currentConversationId}
        onSelectConversation={handleSelectConversation}
        onNewConversation={handleNewConversation}
        showArchived={showArchived}
        onToggleArchived={handleToggleArchived}
        onConversationsChanged={loadConversations}
      />
      <ChatInterface
        conversation={currentConversation}
        onSendMessage={handleSendMessage}
        isLoading={isLoading}
        councilModels={councilModels}
        chairmanModel={chairmanModel}
        onModelsChange={handleModelsChange}
        modelPricing={modelPricing}
        mountedPaths={mountedPaths}
        onMountsChange={handleMountsChange}
        pendingWrites={pendingWrites}
        onApproveWrites={handleApproveWrites}
        onRejectWrites={handleRejectWrites}
      />
    </div>
  );
}

export default App;