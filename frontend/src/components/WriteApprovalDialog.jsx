import { useEffect, useState } from 'react';
import './WriteApprovalDialog.css';

const getWriteKey = (write, index) => write.id || `${write.path}:${index}`;

export default function WriteApprovalDialog({ proposedWrites, onApprove, onReject }) {
  const [selected, setSelected] = useState({});

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSelected(
      proposedWrites.reduce((acc, write, index) => ({
        ...acc,
        [getWriteKey(write, index)]: true,
      }), {})
    );
  }, [proposedWrites]);

  const toggleSelect = (key) => {
    setSelected((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const handleApprove = () => {
    const approved = proposedWrites.filter((write, index) => selected[getWriteKey(write, index)]);
    if (approved.length > 0) {
      onApprove(approved);
    }
  };

  const allSelected = Object.values(selected).every(Boolean);
  const noneSelected = Object.values(selected).every((v) => !v);

  return (
    <div className="write-approval-overlay">
      <div className="write-approval-dialog">
        <div className="write-approval-header">
          <h3>Chairman File Write Proposals</h3>
          <p>The chairman has proposed writing the following files. Review and approve or reject.</p>
        </div>

        <div className="write-approval-list">
          {proposedWrites.map((write, i) => {
            const key = getWriteKey(write, i);
            return (
              <div key={key} className={`write-proposal ${selected[key] ? 'selected' : ''}`}>
                <label className="write-proposal-check">
                  <input
                    type="checkbox"
                    checked={!!selected[key]}
                    onChange={() => toggleSelect(key)}
                  />
                </label>
                <div className="write-proposal-details">
                  <div className="write-proposal-path">{write.path}</div>
                  {write.description && (
                    <div className="write-proposal-desc">{write.description}</div>
                  )}
                  <pre className="write-proposal-content">{write.content}</pre>
                </div>
              </div>
            );
          })}
        </div>

        <div className="write-approval-actions">
          <button className="write-approve-btn" onClick={handleApprove} disabled={noneSelected}>
            {allSelected ? 'Approve All' : 'Approve Selected'}
          </button>
          <button className="write-reject-btn" onClick={onReject}>
            Reject All
          </button>
        </div>
      </div>
    </div>
  );
}
