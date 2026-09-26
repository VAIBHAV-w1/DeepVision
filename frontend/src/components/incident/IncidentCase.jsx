import React, { useState } from 'react';
import { formatDate } from '../../utils/formatters';

export function IncidentCase({ incidentCase, notes = [], onCreateCase, onAddNote, onNavigate }) {
  const [newNote, setNewNote] = useState('');
  const [submittingNote, setSubmittingNote] = useState(false);
  const [creatingCase, setCreatingCase] = useState(false);

  const handlePostNote = async (e) => {
    e.preventDefault();
    const noteText = (newNote || e.currentTarget?.elements?.note?.value || '').trim();
    if (!noteText) return;
    try {
      setSubmittingNote(true);
      await onAddNote(noteText);
      setNewNote('');
      if (e.currentTarget?.elements?.note) {
        e.currentTarget.elements.note.value = '';
      }
    } finally {
      setSubmittingNote(false);
    }
  };

  const handleCreate = async () => {
    try {
      setCreatingCase(true);
      await onCreateCase();
    } finally {
      setCreatingCase(false);
    }
  };

  return (
    <div className="incident-case-card" style={{
      background: 'var(--bg-surface)',
      border: '1px solid var(--border-color)',
      borderRadius: 'var(--radius-lg)',
      padding: '1.25rem',
      marginBottom: '1.5rem',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.5rem' }}>
        <h3 style={{
          fontSize: '0.95rem',
          fontWeight: 700,
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
          margin: 0,
          color: 'var(--text-secondary)',
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
        }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
            <polyline points="14 2 14 8 20 8"></polyline>
            <line x1="16" y1="13" x2="8" y2="13"></line>
            <line x1="16" y1="17" x2="8" y2="17"></line>
            <polyline points="10 9 9 9 8 9"></polyline>
          </svg>
          Forensic Case & Notes
        </h3>

        {incidentCase ? (
          <span className="badge" style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '0.78rem',
            background: 'var(--bg-surface-raised)',
            border: '1px solid var(--border-color)',
            color: 'var(--text-primary)',
          }}>
            {incidentCase.case_number}
          </span>
        ) : (
          <button
            type="button"
            onClick={handleCreate}
            disabled={creatingCase}
            className="btn btn-secondary btn-sm"
            style={{ fontSize: '0.76rem', padding: '3px 10px' }}
          >
            {creatingCase ? 'Creating...' : '+ Open Case'}
          </button>
        )}
      </div>

      {incidentCase ? (
        <div style={{ marginBottom: '1.25rem', background: 'var(--bg-surface-raised)', padding: '0.85rem 1rem', borderRadius: 'var(--radius-md)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
            <span style={{ fontWeight: 600, fontSize: '0.88rem', color: 'var(--text-primary)' }}>
              {incidentCase.title}
            </span>
            <span className={`status-pill ${incidentCase.priority === 'CRITICAL' ? 'status-offline' : 'status-warn'}`} style={{ fontSize: '0.68rem' }}>
              {incidentCase.priority}
            </span>
          </div>
          {incidentCase.description && (
            <p style={{ margin: '0 0 6px 0', fontSize: '0.80rem', color: 'var(--text-secondary)' }}>
              {incidentCase.description}
            </p>
          )}
          <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem', marginTop: '6px' }}>
            <span>Status: <strong style={{ color: 'var(--text-primary)', textTransform: 'uppercase' }}>{incidentCase.status}</strong> | Assigned: {incidentCase.assigned_to || 'Unassigned'}</span>
            <span className="badge" style={{ fontSize: '0.68rem', background: 'var(--bg-surface)', border: '1px solid var(--border-color)' }}>
              Scoped Incident Dossier
            </span>
          </div>
        </div>
      ) : (
        <div style={{ padding: '1rem', background: 'rgba(255, 255, 255, 0.02)', borderRadius: 'var(--radius-md)', textAlign: 'center', marginBottom: '1rem' }}>
          <p style={{ margin: '0 0 0.5rem 0', fontSize: '0.82rem', color: 'var(--text-muted)' }}>
            No formal investigation case registered for this incident.
          </p>
        </div>
      )}

      {/* Notes Thread */}
      <div style={{ marginTop: '1rem' }}>
        <h4 style={{ fontSize: '0.82rem', textTransform: 'uppercase', color: 'var(--text-muted)', margin: '0 0 0.75rem 0' }}>
          Investigator Notes ({notes.length})
        </h4>

        {notes.length > 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem', marginBottom: '1rem', maxHeight: '180px', overflowY: 'auto' }}>
            {notes.map((n) => (
              <div key={n.id} style={{ background: 'var(--bg-surface-raised)', padding: '0.6rem 0.8rem', borderRadius: 'var(--radius-md)', borderLeft: '2px solid var(--accent-color, #3b82f6)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: 'var(--text-muted)', marginBottom: '3px' }}>
                  <span>{n.author_name || 'Investigator'}</span>
                  <span style={{ fontFamily: 'var(--font-mono)' }}>{formatDate(n.created_at)}</span>
                </div>
                <div style={{ fontSize: '0.82rem', color: 'var(--text-primary)' }}>
                  {n.note}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p style={{ margin: '0 0 1rem 0', fontSize: '0.80rem', color: 'var(--text-muted)' }}>No notes added yet.</p>
        )}

        {/* Add Note Form */}
        <form onSubmit={handlePostNote} style={{ display: 'flex', gap: '0.5rem' }}>
          <input
            type="text"
            name="note"
            id="incident-note-input"
            value={newNote}
            onChange={(e) => setNewNote(e.target.value)}
            placeholder="Add forensic investigation note..."
            className="form-control"
            style={{ fontSize: '0.82rem', height: '36px' }}
          />
          <button
            type="submit"
            id="btn-add-note"
            disabled={submittingNote}
            className="btn btn-secondary btn-sm"
            style={{ height: '36px', whiteSpace: 'nowrap' }}
          >
            {submittingNote ? 'Saving...' : 'Add Note'}
          </button>
        </form>
      </div>
    </div>
  );
}

export default IncidentCase;
