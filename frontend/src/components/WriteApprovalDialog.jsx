import { useState } from 'react';
import './WriteApprovalDialog.css';

export default function WriteApprovalDialog({ proposedWrites, onApprove, onReject }) {
  const [selected, setSelected] = useState(() =>
    proposedWrites.reduce((acc, _, i) => ({ ...acc, [i]: true }), {})
  );

  const toggleSelect = (index) => {
    setSelected((prev) => ({ ...prev, [index]: !prev[index] }));
  };

  const handleApprove = () => {
    const approved = proposedWrites.filter((_, i) => selected[i]);
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
          {proposedWrites.map((write, i) => (
            <div key={i} className={`write-proposal ${selected[i] ? 'selected' : ''}`}>
              <label className="write-proposal-check">
                <input
                  type="checkbox"
                  checked={selected[i]}
                  onChange={() => toggleSelect(i)}
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
          ))}
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
