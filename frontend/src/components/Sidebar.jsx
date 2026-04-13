import { useState, useRef, useEffect } from 'react';
import { api } from '../api';
import './Sidebar.css';

export default function Sidebar({
  conversations,
  currentConversationId,
  onSelectConversation,
  onNewConversation,
  darkMode,
  onToggleDarkMode,
  showArchived,
  onToggleArchived,
  onConversationsChanged,
}) {
  const [openMenuId, setOpenMenuId] = useState(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const menuRef = useRef(null);

  // Close menu on outside click
  useEffect(() => {
    const handleClick = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setOpenMenuId(null);
        setConfirmDeleteId(null);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const handleArchive = async (convId) => {
    try {
      const conv = conversations.find(c => c.id === convId);
      await api.archiveConversation(convId, !conv.archived);
      setOpenMenuId(null);
      onConversationsChanged();
    } catch (err) {
      console.error('Failed to archive:', err);
    }
  };

  const handleDelete = async (convId) => {
    try {
      await api.deleteConversation(convId);
      setOpenMenuId(null);
      setConfirmDeleteId(null);
      onConversationsChanged();
    } catch (err) {
      console.error('Failed to delete:', err);
    }
  };

  const handleExport = async (convId, format) => {
    try {
      await api.exportConversation(convId, format);
      setOpenMenuId(null);
    } catch (err) {
      console.error('Failed to export:', err);
    }
  };

  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <h1>LLM Council</h1>
        <div className="sidebar-header-actions">
          <button
            className={`archive-toggle-btn ${showArchived ? 'active' : ''}`}
            onClick={onToggleArchived}
            title={showArchived ? 'Show active chats' : 'Show archived chats'}
          >
            {showArchived ? '☰ Active' : '☰ Archive'}
          </button>
          <button className="new-conversation-btn" onClick={onNewConversation}>
            + New
          </button>
        </div>
      </div>

      <div className="conversation-list">
        {conversations.length === 0 ? (
          <div className="no-conversations">
            {showArchived ? 'No archived conversations' : 'No conversations yet'}
          </div>
        ) : (
          conversations.map((conv) => (
            <div
              key={conv.id}
              className={`conversation-item ${conv.id === currentConversationId ? 'active' : ''} ${conv.archived ? 'archived' : ''}`}
              onClick={() => onSelectConversation(conv.id)}
            >
              <div className="conversation-item-content">
                <div className="conversation-title">
                  {conv.title || 'New Conversation'}
                </div>
                <div className="conversation-meta">
                  {conv.message_count} messages
                </div>
              </div>
              <div className="conversation-item-actions" ref={openMenuId === conv.id ? menuRef : null}>
                <button
                  className="menu-btn"
                  onClick={(e) => { e.stopPropagation(); setOpenMenuId(openMenuId === conv.id ? null : conv.id); setConfirmDeleteId(null); }}
                  title="Actions"
                >
                  ⋮
                </button>
                {openMenuId === conv.id && (
                  <div className="dropdown-menu" onClick={(e) => e.stopPropagation()}>
                    <div className="dropdown-label">Export</div>
                    <button className="dropdown-item" onClick={() => handleExport(conv.id, 'markdown')}>
                      Markdown (.md)
                    </button>
                    <button className="dropdown-item" onClick={() => handleExport(conv.id, 'json')}>
                      JSON (.json)
                    </button>
                    <button className="dropdown-item" onClick={() => handleExport(conv.id, 'pdf')}>
                      PDF (.pdf)
                    </button>
                    <div className="dropdown-divider" />
                    <button className="dropdown-item" onClick={() => handleArchive(conv.id)}>
                      {conv.archived ? 'Unarchive' : 'Archive'}
                    </button>
                    {confirmDeleteId === conv.id ? (
                      <div className="dropdown-confirm">
                        <span>Delete permanently?</span>
                        <div className="dropdown-confirm-btns">
                          <button className="confirm-yes" onClick={() => handleDelete(conv.id)}>Yes</button>
                          <button className="confirm-no" onClick={() => setConfirmDeleteId(null)}>No</button>
                        </div>
                      </div>
                    ) : (
                      <button className="dropdown-item danger" onClick={() => setConfirmDeleteId(conv.id)}>
                        Delete
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      <div className="sidebar-footer">
        <button className="theme-toggle" onClick={onToggleDarkMode}>
          {darkMode ? '☀ Light Mode' : '☾ Dark Mode'}
        </button>
      </div>
    </div>
  );
}
