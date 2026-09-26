import React, { useState, useEffect } from 'react';
import { api } from '../services/api';
import { formatDate } from '../utils/formatters';

export function Cases({ onNavigate, selectedId, initialAlertId }) {
  const [cases, setCases] = useState([]);
  const [status, setStatus] = useState('');
  const [priority, setPriority] = useState('');
  const [alertId, setAlertId] = useState(initialAlertId || '');
  const [search, setSearch] = useState('');
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [selectedCase, setSelectedCase] = useState(null);

  const fetchCases = async () => {
    try {
      setLoading(true);
      const params = {};
      if (status) params.status = status;
      if (priority) params.priority = priority;
      if (alertId) params.alert_id = alertId;
      if (search) params.search = search;

      const data = await api.cases.list(params);
      if (data) {
        const list = data.cases || [];
        setCases(list);
        setTotalCount(data.total_count ?? list.length);

        if (selectedId) {
          const found = list.find(c => Number(c.id) === Number(selectedId));
          if (found) setSelectedCase(found);
        }
      }
    } catch (err) {
      console.warn('Failed to load cases:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCases();
  }, [status, priority, alertId]);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    fetchCases();
  };

  return (
    <div className="cases-page-container">
      {/* Editorial Header */}
      <div className="hero-editorial-wrap">
        <div className="editorial-badge-pill">
          <span>Case Registry</span>
        </div>
        <h1 className="editorial-hero-title" style={{ fontSize: 'clamp(2.2rem, 4vw, 3.25rem)', marginBottom: '0.5rem' }}>
          Forensic incident cases
        </h1>
        <p className="editorial-hero-subtitle" style={{ marginBottom: '2rem' }}>
          Track, investigate, and resolve security incident workflows, evidence chains, and SLA response timelines.
        </p>
      </div>

      {/* Controls & Filters Bar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem', marginBottom: '2rem' }}>
        <form onSubmit={handleSearchSubmit} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap', margin: 0 }}>
          {/* Status Filter */}
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="form-select"
            style={{ width: 'auto', height: '38px', fontSize: '0.84rem', padding: '0.2rem 1.8rem 0.2rem 0.8rem' }}
          >
            <option value="">All Statuses</option>
            <option value="OPEN">Open</option>
            <option value="INVESTIGATING">Investigating</option>
            <option value="RESOLVED">Resolved</option>
            <option value="CLOSED">Closed</option>
          </select>

          {/* Priority Filter */}
          <select
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
            className="form-select"
            style={{ width: 'auto', height: '38px', fontSize: '0.84rem', padding: '0.2rem 1.8rem 0.2rem 0.8rem' }}
          >
            <option value="">All Priorities</option>
            <option value="CRITICAL">Critical</option>
            <option value="HIGH">High</option>
            <option value="MEDIUM">Medium</option>
            <option value="LOW">Low</option>
          </select>

          {/* Search Input */}
          <div style={{ position: 'relative', width: '240px' }}>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search case number or title..."
              className="form-control"
              style={{ height: '38px', fontSize: '0.84rem', paddingLeft: '2.2rem' }}
            />
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ position: 'absolute', left: '0.75rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }}>
              <circle cx="11" cy="11" r="8"></circle>
              <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
            </svg>
          </div>

          <button type="submit" className="btn btn-secondary btn-sm" style={{ height: '38px' }}>Filter</button>
          {(status || priority || alertId || search) && (
            <button
              type="button"
              onClick={() => { setStatus(''); setPriority(''); setAlertId(''); setSearch(''); }}
              className="btn btn-ghost btn-sm"
              style={{ height: '38px' }}
            >
              Reset
            </button>
          )}
        </form>

        <div style={{ fontSize: '0.84rem', color: 'var(--text-secondary)' }}>
          Total Registered Cases: <strong style={{ color: 'var(--text-main)' }}>{totalCount}</strong>
        </div>
      </div>

      {/* Cases Table */}
      {cases.length > 0 ? (
        <div className="table-responsive" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
          <table className="cctv-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-color)', background: 'var(--bg-surface-raised)' }}>
                <th style={{ padding: '0.75rem 1rem', textAlignment: 'left' }}>Case Number</th>
                <th style={{ padding: '0.75rem 1rem', textAlignment: 'left' }}>Title &amp; Summary</th>
                <th style={{ padding: '0.75rem 1rem', textAlignment: 'left' }}>Priority</th>
                <th style={{ padding: '0.75rem 1rem', textAlignment: 'left' }}>Status</th>
                <th style={{ padding: '0.75rem 1rem', textAlignment: 'left' }}>Investigator</th>
                <th style={{ padding: '0.75rem 1rem', textAlignment: 'left' }}>Created Time</th>
                <th style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {cases.map((c) => (
                <tr key={c.id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                  <td style={{ padding: '0.75rem 1rem', fontFamily: 'var(--font-mono)', fontWeight: 700 }}>
                    <span style={{ color: 'var(--color-primary, #38bdf8)' }}>{c.case_number}</span>
                  </td>
                  <td style={{ padding: '0.75rem 1rem', fontWeight: 600 }}>
                    <div>{c.title}</div>
                    {c.description && (
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 'normal', marginTop: '2px' }}>
                        {c.description.length > 60 ? `${c.description.slice(0, 60)}...` : c.description}
                      </div>
                    )}
                  </td>
                  <td style={{ padding: '0.75rem 1rem' }}>
                    <span className={`status-pill ${c.priority === 'CRITICAL' ? 'status-offline' : c.priority === 'HIGH' ? 'status-warn' : 'status-live'}`} style={{ fontSize: '0.70rem' }}>
                      {c.priority}
                    </span>
                  </td>
                  <td style={{ padding: '0.75rem 1rem' }}>
                    <span className={`status-pill ${c.status === 'OPEN' ? 'status-offline' : c.status === 'INVESTIGATING' ? 'status-warn' : 'status-live'}`} style={{ fontSize: '0.70rem' }}>
                      {c.status}
                    </span>
                  </td>
                  <td style={{ padding: '0.75rem 1rem', color: 'var(--text-secondary)' }}>
                    {c.assigned_to || 'Unassigned'}
                  </td>
                  <td style={{ padding: '0.75rem 1rem', fontFamily: 'var(--font-mono)', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    {formatDate(c.created_at)}
                  </td>
                  <td style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>
                    <button
                      type="button"
                      onClick={() => setSelectedCase(c)}
                      className="btn btn-secondary btn-sm"
                      style={{ fontSize: '0.75rem', padding: '0.25rem 0.6rem' }}
                    >
                      Inspect
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="empty-state-card" style={{ textAlign: 'center', padding: '4rem 1.5rem', background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-lg)' }}>
          <p style={{ margin: 0, color: 'var(--text-muted)' }}>
            {loading ? 'Retrieving active forensic cases...' : 'No incident cases registered in system.'}
          </p>
        </div>
      )}

      {/* Case Details Drawer / Modal */}
      {selectedCase && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 9999,
            background: 'rgba(0,0,0,0.7)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '1.5rem',
          }}
          onClick={(e) => { if (e.target === e.currentTarget) setSelectedCase(null); }}
        >
          <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-lg)', width: '100%', maxWidth: '640px', padding: '1.75rem', boxShadow: 'var(--shadow-xl)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.75rem' }}>
              <div>
                <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--color-primary)' }}>{selectedCase.case_number}</span>
                <h3 style={{ margin: '4px 0 0', fontSize: '1.15rem' }}>{selectedCase.title}</h3>
              </div>
              <button
                type="button"
                onClick={() => setSelectedCase(null)}
                className="btn btn-ghost btn-sm"
              >
                ✕
              </button>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '12px', fontSize: '0.85rem', marginBottom: '1.25rem' }}>
              <div><strong>Status:</strong> {selectedCase.status}</div>
              <div><strong>Priority:</strong> {selectedCase.priority}</div>
              <div><strong>Investigator:</strong> {selectedCase.assigned_to || 'Unassigned'}</div>
              <div><strong>Opened:</strong> {formatDate(selectedCase.created_at)}</div>
            </div>

            {selectedCase.description && (
              <div style={{ marginBottom: '1.25rem' }}>
                <strong style={{ fontSize: '0.85rem', display: 'block', marginBottom: '4px' }}>Description:</strong>
                <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-secondary)', background: 'var(--bg-surface-secondary, rgba(0,0,0,0.02))', padding: '10px', borderRadius: 'var(--radius-sm)' }}>
                  {selectedCase.description}
                </p>
              </div>
            )}

            {/* Incident notes safely checked */}
            {selectedCase.incident_notes || selectedCase.alert?.incident_notes ? (
              <div style={{ marginBottom: '1.25rem' }}>
                <strong style={{ fontSize: '0.85rem', display: 'block', marginBottom: '4px' }}>Incident Notes:</strong>
                <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-secondary)', background: 'var(--bg-surface-secondary, rgba(0,0,0,0.02))', padding: '10px', borderRadius: 'var(--radius-sm)' }}>
                  {selectedCase.incident_notes || selectedCase.alert?.incident_notes}
                </p>
              </div>
            ) : null}

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '1.5rem' }}>
              {selectedCase.alert_id ? (
                <button
                  type="button"
                  onClick={() => { const aid = selectedCase.alert_id; setSelectedCase(null); onNavigate('alerts', { selectedId: aid }); }}
                  className="btn btn-primary btn-sm"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}
                >
                  Open Incident Workspace →
                </button>
              ) : <div />}
              <button
                type="button"
                onClick={() => setSelectedCase(null)}
                className="btn btn-secondary btn-sm"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default Cases;
