import React, { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '../services/api';
import { formatDate } from '../utils/formatters';
import { useToast } from '../components/common/Toast';
import { IncidentHeader } from '../components/incident/IncidentHeader';
import { IncidentMedia } from '../components/incident/IncidentMedia';
import { IncidentAnalysis } from '../components/incident/IncidentAnalysis';
import { IncidentTimeline } from '../components/incident/IncidentTimeline';
import { IncidentEvidence } from '../components/incident/IncidentEvidence';
import { IncidentRecording } from '../components/incident/IncidentRecording';
import { IncidentCase } from '../components/incident/IncidentCase';
import { IncidentNotifications } from '../components/incident/IncidentNotifications';

export function Alerts({ onNavigate, selectedId, initialCameraId, initialHasVideo, initialHasCase }) {
  // Inbox state
  const [alerts, setAlerts] = useState([]);
  const [cameras, setCameras] = useState([]);
  const [status, setStatus] = useState('');
  const [severity, setSeverity] = useState('');
  const [cameraId, setCameraId] = useState(initialCameraId ? String(initialCameraId) : '');
  const [hasVideoFilter, setHasVideoFilter] = useState(initialHasVideo ? String(initialHasVideo) : '');
  const [hasCaseFilter, setHasCaseFilter] = useState(initialHasCase ? String(initialHasCase) : '');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [numPages, setNumPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [stats, setStats] = useState({
    total_count: 0,
    new_count: 0,
    active_high_count: 0,
    resolved_count: 0,
    with_video_count: 0,
    with_case_count: 0,
  });
  const [loading, setLoading] = useState(true);

  // Selected Incident Workspace state
  const [activeAlertId, setActiveAlertId] = useState(selectedId ? Number(selectedId) : null);
  const [activeIncidentData, setActiveIncidentData] = useState(null);
  const [incidentLoading, setIncidentLoading] = useState(false);
  const activeRequestRef = useRef(0);

  const { addToast } = useToast();

  // Sync selectedId prop from outside navigation
  useEffect(() => {
    if (selectedId !== undefined && selectedId !== null) {
      const parsed = Number(selectedId);
      if (!isNaN(parsed) && parsed !== Number(activeAlertId)) {
        setActiveAlertId(parsed);
      }
    }
  }, [selectedId]);

  // Fetch Alert Inbox list
  const fetchAlerts = useCallback(async () => {
    try {
      setLoading(true);
      const params = { page, per_page: 15 };
      if (status) params.status = status;
      if (severity) params.severity = severity;
      if (cameraId) params.camera_id = cameraId;
      if (hasVideoFilter) params.has_video = hasVideoFilter;
      if (hasCaseFilter) params.has_case = hasCaseFilter;
      if (search.trim()) params.search = search.trim();

      const data = await api.alerts.list(params);
      if (data) {
        setAlerts(data.alerts || []);
        setCameras(data.cameras || []);
        setTotalCount(data.total_count || 0);
        setNumPages(data.num_pages || 1);
        if (data.metrics) {
          setStats(data.metrics);
        }
      }
    } catch (err) {
      console.warn('Failed to load alerts inbox:', err);
    } finally {
      setLoading(false);
    }
  }, [page, status, severity, cameraId, hasVideoFilter, hasCaseFilter, search]);

  useEffect(() => {
    fetchAlerts();
  }, [fetchAlerts]);

  // Fetch single incident workspace detail when activeAlertId is set
  const loadIncidentDetail = useCallback(async (alertId) => {
    if (!alertId) {
      activeRequestRef.current++;
      setActiveIncidentData(null);
      setIncidentLoading(false);
      return;
    }

    const reqId = ++activeRequestRef.current;
    // CRITICAL: Immediately clear previous incident data to prevent cross-incident contamination
    setActiveIncidentData(null);
    setIncidentLoading(true);

    try {
      const data = await api.alerts.get(alertId);
      // Ensure only the response for the most recent active alert is accepted
      if (reqId === activeRequestRef.current && data && data.alert && Number(data.alert.id) === Number(alertId)) {
        setActiveIncidentData(data);
      }
    } catch (err) {
      if (reqId === activeRequestRef.current) {
        console.warn(`Failed to load incident detail for alert ${alertId}:`, err);
        addToast('Failed to load incident detail', 'error');
      }
    } finally {
      if (reqId === activeRequestRef.current) {
        setIncidentLoading(false);
      }
    }
  }, [addToast]);

  useEffect(() => {
    if (activeAlertId) {
      loadIncidentDetail(activeAlertId);
    } else {
      activeRequestRef.current++;
      setActiveIncidentData(null);
      setIncidentLoading(false);
    }
  }, [activeAlertId, loadIncidentDetail]);

  // Acknowledge handler
  const handleAcknowledge = async (id) => {
    try {
      const res = await api.alerts.acknowledge(id);
      if (res && (res.success || res.status === 'ok')) {
        addToast('Alert acknowledged', 'success');
        fetchAlerts();
        if (activeAlertId === id) {
          loadIncidentDetail(id);
        }
      } else {
        addToast(res?.message || res?.error || 'Failed to acknowledge alert', 'error');
      }
    } catch {
      addToast('Error acknowledging alert', 'error');
    }
  };

  // Resolve handler
  const handleResolve = async (id) => {
    try {
      const res = await api.alerts.resolve(id);
      if (res && (res.success || res.status === 'ok')) {
        addToast('Incident resolved successfully', 'success');
        fetchAlerts();
        if (activeAlertId === id) {
          loadIncidentDetail(id);
        }
      } else {
        addToast(res?.message || res?.error || 'Failed to resolve incident', 'error');
      }
    } catch {
      addToast('Error resolving incident', 'error');
    }
  };

  // Add Investigator Note handler
  const handleAddNote = async (noteText) => {
    if (!activeAlertId) return;
    try {
      const res = await api.alerts.addNote(activeAlertId, noteText);
      if (res && res.success) {
        addToast('Investigator note attached', 'success');
        loadIncidentDetail(activeAlertId);
      } else {
        addToast(res?.error || 'Failed to add note', 'error');
      }
    } catch {
      addToast('Error saving note', 'error');
    }
  };

  // Create Case handler
  const handleCreateCase = async () => {
    if (!activeAlertId) return;
    try {
      const res = await api.alerts.createCase(activeAlertId);
      if (res && res.success) {
        addToast(`Case ${res.case.case_number} registered`, 'success');
        loadIncidentDetail(activeAlertId);
        fetchAlerts();
      } else {
        addToast(res?.error || 'Failed to create case', 'error');
      }
    } catch {
      addToast('Error creating case', 'error');
    }
  };

  // Quick filter tab selection
  const handleQuickTab = (type) => {
    setPage(1);
    if (type === 'all') {
      setStatus('');
      setSeverity('');
      setHasVideoFilter('');
      setHasCaseFilter('');
    } else if (type === 'new') {
      setStatus('new');
      setSeverity('');
      setHasVideoFilter('');
      setHasCaseFilter('');
    } else if (type === 'high') {
      setStatus('');
      setSeverity('high');
      setHasVideoFilter('');
      setHasCaseFilter('');
    } else if (type === 'video') {
      setStatus('');
      setSeverity('');
      setHasVideoFilter('true');
      setHasCaseFilter('');
    } else if (type === 'case') {
      setStatus('');
      setSeverity('');
      setHasVideoFilter('');
      setHasCaseFilter('true');
    } else if (type === 'resolved') {
      setStatus('resolved');
      setSeverity('');
      setHasVideoFilter('');
      setHasCaseFilter('');
    }
  };

  // =========================================================================
  // VIEW 1: ACTIVE INCIDENT FORENSIC WORKSPACE (Alert Detail View)
  // =========================================================================
  if (activeAlertId) {
    // If data is loading or does not match the active alert ID, display loading placeholder
    if (incidentLoading || !activeIncidentData || Number(activeIncidentData.alert?.id) !== Number(activeAlertId)) {
      return (
        <div style={{ padding: '4rem 2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
          <div className="spinner" style={{ margin: '0 auto 1rem auto' }}></div>
          <p style={{ margin: 0, fontWeight: 500 }}>Loading incident forensics workspace for Incident #{activeAlertId}...</p>
        </div>
      );
    }

    const { alert, primary_media, ai_analysis, timeline, evidence_items, incident_case, incident_notes, notifications } = activeIncidentData;

    return (
      <div className="incident-workspace-container" style={{ padding: '0 0.5rem 2rem 0.5rem', maxWidth: '1280px', margin: '0 auto' }}>
        {/* 1. INCIDENT HEADER */}
        <IncidentHeader
          alert={alert}
          onBack={() => setActiveAlertId(null)}
          onAcknowledge={handleAcknowledge}
          onResolve={handleResolve}
          onNavigate={onNavigate}
        />

        <div className="incident-workspace-flow" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* 2. AI ANALYSIS */}
          <IncidentAnalysis analysis={ai_analysis} />

          {/* 3. INCIDENT MEDIA */}
          <IncidentMedia
            primaryMedia={primary_media}
            evidenceItems={evidence_items}
            alertId={alert?.id}
            onNavigate={onNavigate}
          />

          {/* 4. EVIDENCE */}
          <IncidentEvidence
            evidenceItems={evidence_items}
            alertId={alert?.id}
            onNavigate={onNavigate}
          />

          {/* 5. RECORDING */}
          <IncidentRecording
            recording={primary_media?.recording}
            alertId={alert?.id}
          />

          {/* 6. CASE */}
          <IncidentCase
            incidentCase={incident_case}
            notes={incident_notes}
            alertId={alert?.id}
            onNavigate={onNavigate}
            onCreateCase={handleCreateCase}
            onAddNote={handleAddNote}
          />

          {/* 7. TIMELINE */}
          <IncidentTimeline timeline={timeline} />

          {/* 8. INCIDENT NOTIFICATIONS */}
          <IncidentNotifications notifications={notifications} />
        </div>
      </div>
    );
  }

  // =========================================================================
  // VIEW 2: UNIFIED INCIDENT INBOX (Alerts Page Primary List)
  // =========================================================================
  return (
    <div className="alerts-page-container">
      {/* Editorial Hero Header */}
      <div className="hero-editorial-wrap">
        <div className="editorial-badge-pill">
          <span>Incident Operations Workspace</span>
        </div>
        <h1 className="editorial-hero-title" style={{ fontSize: 'clamp(2.2rem, 4vw, 3.25rem)', marginBottom: '0.5rem' }}>
          Unified Incident Forensics
        </h1>
        <p className="editorial-hero-subtitle" style={{ marginBottom: '2rem' }}>
          Real-time security anomaly inbox, evidence media verification, and incident case operations.
        </p>
      </div>

      {/* Forensic KPI Metric Cards */}
      <div className="summary-grid" style={{ marginBottom: '2rem' }}>
        <div className="summary-card" onClick={() => handleQuickTab('all')} style={{ cursor: 'pointer' }}>
          <div className="summary-data">
            <span className="summary-value">{stats.total_count}</span>
            <span className="summary-label">Total Incidents</span>
          </div>
          <div className="summary-icon-wrap">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M 18 8 A 6 6 0 0 0 6 8 c 0 7 -3 9 -3 9 h 18 s -3 -2 -3 -9"></path>
              <path d="M 13.73 21 a 2 2 0 0 1 -3.46 0"></path>
            </svg>
          </div>
        </div>

        <div className="summary-card kpi-offline" onClick={() => handleQuickTab('new')} style={{ cursor: 'pointer' }}>
          <div className="summary-data">
            <span className="summary-value" style={{ color: 'var(--color-offline, #ef4444)' }}>{stats.new_count}</span>
            <span className="summary-label">Unacknowledged</span>
          </div>
          <div className="summary-icon-wrap">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="8" x2="12" y2="12"></line>
              <line x1="12" y1="16" x2="12.01" y2="16"></line>
            </svg>
          </div>
        </div>

        <div className="summary-card kpi-recordings" onClick={() => handleQuickTab('high')} style={{ cursor: 'pointer' }}>
          <div className="summary-data">
            <span className="summary-value" style={{ color: 'var(--color-warn, #f59e0b)' }}>{stats.active_high_count}</span>
            <span className="summary-label">High / Critical</span>
          </div>
          <div className="summary-icon-wrap">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polygon points="12 2 2 22 22 22 12 2"></polygon>
              <line x1="12" y1="9" x2="12" y2="13"></line>
              <line x1="12" y1="17" x2="12.01" y2="17"></line>
            </svg>
          </div>
        </div>

        <div className="summary-card" onClick={() => handleQuickTab('video')} style={{ cursor: 'pointer' }}>
          <div className="summary-data">
            <span className="summary-value" style={{ color: 'var(--accent-color, #3b82f6)' }}>{stats.with_video_count || 0}</span>
            <span className="summary-label">With Video Clips</span>
          </div>
          <div className="summary-icon-wrap">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polygon points="23 7 16 12 23 17 23 7"></polygon>
              <rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect>
            </svg>
          </div>
        </div>

        <div className="summary-card" onClick={() => handleQuickTab('case')} style={{ cursor: 'pointer' }}>
          <div className="summary-data">
            <span className="summary-value" style={{ color: '#8b5cf6' }}>{stats.with_case_count || 0}</span>
            <span className="summary-label">Linked Cases</span>
          </div>
          <div className="summary-icon-wrap">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
              <polyline points="14 2 14 8 20 8"></polyline>
            </svg>
          </div>
        </div>

        <div className="summary-card kpi-online" onClick={() => handleQuickTab('resolved')} style={{ cursor: 'pointer' }}>
          <div className="summary-data">
            <span className="summary-value" style={{ color: 'var(--color-live, #10b981)' }}>{stats.resolved_count}</span>
            <span className="summary-label">Resolved</span>
          </div>
          <div className="summary-icon-wrap">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M 22 11.08 V 12 a 10 10 0 1 1 -5.93 -9.14"></path>
              <polyline points="22 4 12 14.01 9 11.01"></polyline>
            </svg>
          </div>
        </div>
      </div>

      {/* Quick Filter Navigation Tabs */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '1.25rem', flexWrap: 'wrap' }}>
        <button
          type="button"
          onClick={() => handleQuickTab('all')}
          className={`btn btn-sm ${!status && !severity && !hasVideoFilter && !hasCaseFilter ? 'btn-primary' : 'btn-ghost'}`}
          style={{ fontSize: '0.80rem' }}
        >
          All Incidents
        </button>
        <button
          type="button"
          onClick={() => handleQuickTab('new')}
          className={`btn btn-sm ${status === 'new' ? 'btn-primary' : 'btn-ghost'}`}
          style={{ fontSize: '0.80rem' }}
        >
          Unacknowledged ({stats.new_count})
        </button>
        <button
          type="button"
          onClick={() => handleQuickTab('high')}
          className={`btn btn-sm ${severity === 'high' ? 'btn-primary' : 'btn-ghost'}`}
          style={{ fontSize: '0.80rem' }}
        >
          Critical & High ({stats.active_high_count})
        </button>
        <button
          type="button"
          id="tab-filter-video"
          onClick={() => handleQuickTab('video')}
          className={`btn btn-sm ${hasVideoFilter === 'true' ? 'btn-primary' : 'btn-ghost'}`}
          style={{ fontSize: '0.80rem' }}
        >
          With Video ({stats.with_video_count || 0})
        </button>
        <button
          type="button"
          onClick={() => handleQuickTab('case')}
          className={`btn btn-sm ${hasCaseFilter === 'true' ? 'btn-primary' : 'btn-ghost'}`}
          style={{ fontSize: '0.80rem' }}
        >
          With Case ({stats.with_case_count || 0})
        </button>
        <button
          type="button"
          onClick={() => handleQuickTab('resolved')}
          className={`btn btn-sm ${status === 'resolved' ? 'btn-primary' : 'btn-ghost'}`}
          style={{ fontSize: '0.80rem' }}
        >
          Resolved ({stats.resolved_count})
        </button>
      </div>

      {/* Advanced Filters & Search Bar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem', marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap', margin: 0 }}>
          {/* Camera Filter */}
          <select
            value={cameraId}
            onChange={(e) => { setCameraId(e.target.value); setPage(1); }}
            className="form-select"
            style={{ width: 'auto', height: '38px', fontSize: '0.84rem' }}
          >
            <option value="">All Cameras</option>
            {cameras.map((cam) => (
              <option key={cam.id} value={cam.id}>{cam.name}</option>
            ))}
          </select>

          {/* Severity Filter */}
          <select
            value={severity}
            onChange={(e) => { setSeverity(e.target.value); setPage(1); }}
            className="form-select"
            style={{ width: 'auto', height: '38px', fontSize: '0.84rem' }}
          >
            <option value="">All Severities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>

          {/* Status Filter */}
          <select
            value={status}
            onChange={(e) => { setStatus(e.target.value); setPage(1); }}
            className="form-select"
            style={{ width: 'auto', height: '38px', fontSize: '0.84rem' }}
          >
            <option value="">All Statuses</option>
            <option value="new">New</option>
            <option value="acknowledged">Acknowledged</option>
            <option value="resolved">Resolved</option>
          </select>

          {/* Search Box */}
          <div style={{ position: 'relative', width: '240px' }}>
            <input
              type="text"
              id="alerts-search-input"
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1); }}
              placeholder="Search incident, ID, case..."
              className="form-control"
              style={{ height: '38px', fontSize: '0.84rem', paddingLeft: '2.2rem' }}
            />
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ position: 'absolute', left: '0.75rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }}>
              <circle cx="11" cy="11" r="8"></circle>
              <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
            </svg>
          </div>

          {(status || severity || cameraId || hasVideoFilter || hasCaseFilter || search) && (
            <button
              type="button"
              onClick={() => {
                setStatus('');
                setSeverity('');
                setCameraId('');
                setHasVideoFilter('');
                setHasCaseFilter('');
                setSearch('');
                setPage(1);
              }}
              className="btn btn-ghost btn-sm"
              style={{ height: '38px' }}
            >
              Reset Filters
            </button>
          )}
        </div>

        <div style={{ fontSize: '0.84rem', color: 'var(--text-muted)' }}>
          Showing <strong>{alerts.length}</strong> of <strong>{totalCount}</strong> incidents
        </div>
      </div>

      {/* Incident Forensics Table */}
      {alerts.length > 0 ? (
        <div className="table-responsive" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
          <table className="cctv-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-color)', background: 'var(--bg-surface-raised)' }}>
                <th style={{ padding: '0.75rem 1rem', textAlign: 'left' }}>Incident / Anomaly</th>
                <th style={{ padding: '0.75rem 1rem', textAlign: 'left' }}>Camera Source</th>
                <th style={{ padding: '0.75rem 1rem', textAlign: 'left' }}>Severity</th>
                <th style={{ padding: '0.75rem 1rem', textAlign: 'left' }}>Artifacts & Forensics</th>
                <th style={{ padding: '0.75rem 1rem', textAlign: 'left' }}>Status</th>
                <th style={{ padding: '0.75rem 1rem', textAlign: 'left' }}>Detected</th>
                <th style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((alertItem) => {
                const severityClass = alertItem.severity === 'critical' ? 'status-offline' : alertItem.severity === 'high' ? 'status-warn' : 'status-live';

                return (
                  <tr
                    key={alertItem.id}
                    data-alert-id={alertItem.id}
                    onClick={() => setActiveAlertId(alertItem.id)}
                    style={{ borderBottom: '1px solid var(--border-color)', cursor: 'pointer', transition: 'background 0.15s ease' }}
                    className="incident-row-hover"
                  >
                    <td style={{ padding: '0.75rem 1rem' }}>
                      <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: '2px' }}>
                        {alertItem.title}
                      </div>
                      <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)' }}>
                        #{alertItem.id} • {alertItem.event_type || 'Surveillance'}
                      </div>
                    </td>

                    <td style={{ padding: '0.75rem 1rem' }}>
                      <div style={{ fontWeight: 500 }}>{alertItem.camera_name || 'Channel 01'}</div>
                      <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>{alertItem.location || 'Zone'}</div>
                    </td>

                    <td style={{ padding: '0.75rem 1rem' }}>
                      <span className={`status-pill ${severityClass}`} style={{ fontSize: '0.70rem', fontWeight: 700 }}>
                        {alertItem.severity ? alertItem.severity.toUpperCase() : 'MEDIUM'}
                      </span>
                    </td>

                    {/* Artifact & Forensics Badges: Video, Audio, Snapshot, Case */}
                    <td style={{ padding: '0.75rem 1rem' }} onClick={(e) => e.stopPropagation()}>
                      <div style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
                        {/* Video Badge */}
                        <span
                          className="badge"
                          style={{
                            fontSize: '0.68rem',
                            background: alertItem.has_video ? 'rgba(59, 130, 246, 0.15)' : 'rgba(255, 255, 255, 0.03)',
                            color: alertItem.has_video ? 'var(--accent-color, #3b82f6)' : 'var(--text-muted)',
                            border: `1px solid ${alertItem.has_video ? 'var(--accent-color, #3b82f6)' : 'var(--border-color)'}`,
                          }}
                        >
                          VIDEO {alertItem.has_video ? '✓' : '✕'}
                        </span>

                        {/* Audio Badge */}
                        <span
                          className="badge"
                          title="DirectShow video-only source without multiplexed audio track"
                          style={{
                            fontSize: '0.68rem',
                            background: alertItem.has_audio ? 'rgba(16, 185, 129, 0.15)' : 'rgba(255, 255, 255, 0.03)',
                            color: alertItem.has_audio ? 'var(--color-live, #10b981)' : 'var(--text-muted)',
                            border: `1px solid ${alertItem.has_audio ? 'var(--color-live, #10b981)' : 'var(--border-color)'}`,
                          }}
                        >
                          AUDIO {alertItem.has_audio ? '✓' : '✕'}
                        </span>

                        {/* Snapshot Badge */}
                        <span
                          className="badge"
                          style={{
                            fontSize: '0.68rem',
                            background: alertItem.has_snapshot ? 'rgba(16, 185, 129, 0.15)' : 'rgba(255, 255, 255, 0.03)',
                            color: alertItem.has_snapshot ? 'var(--color-live, #10b981)' : 'var(--text-muted)',
                            border: `1px solid ${alertItem.has_snapshot ? 'var(--color-live, #10b981)' : 'var(--border-color)'}`,
                          }}
                        >
                          SNAP {alertItem.has_snapshot ? '✓' : '✕'}
                        </span>

                        {/* Case Badge */}
                        {alertItem.has_case && (
                          <span
                            className="badge"
                            style={{
                              fontSize: '0.68rem',
                              background: 'rgba(139, 92, 246, 0.15)',
                              color: '#8b5cf6',
                              border: '1px solid #8b5cf6',
                              fontFamily: 'var(--font-mono)',
                            }}
                          >
                            {alertItem.case_number || 'CASE ✓'}
                          </span>
                        )}
                      </div>
                    </td>

                    <td style={{ padding: '0.75rem 1rem' }}>
                      <span className="badge" style={{ textTransform: 'uppercase', fontSize: '0.70rem' }}>
                        {alertItem.status}
                      </span>
                    </td>

                    <td style={{ padding: '0.75rem 1rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: '0.80rem' }}>
                      {formatDate(alertItem.detected_at)}
                    </td>

                    <td style={{ padding: '0.75rem 1rem', textAlign: 'right' }} onClick={(e) => e.stopPropagation()}>
                      <div style={{ display: 'inline-flex', gap: '6px' }}>
                        {alertItem.status === 'new' && (
                          <button
                            type="button"
                            onClick={() => handleAcknowledge(alertItem.id)}
                            className="btn btn-secondary btn-sm"
                            style={{ fontSize: '0.75rem', padding: '4px 8px' }}
                          >
                            Ack
                          </button>
                        )}
                        <button
                          type="button"
                          id={`btn-open-incident-${alertItem.id}`}
                          onClick={() => setActiveAlertId(alertItem.id)}
                          className="btn btn-primary btn-sm btn-open-incident"
                          style={{ fontSize: '0.75rem', padding: '4px 10px', fontWeight: 600 }}
                        >
                          Open Incident
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="empty-state-card" style={{ textAlign: 'center', padding: '4rem 1.5rem', background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-lg)' }}>
          <p style={{ margin: 0, color: 'var(--text-muted)' }}>
            {loading ? 'Retrieving incident operations feed...' : 'No security incidents found matching your query.'}
          </p>
        </div>
      )}

      {/* Pagination Controls */}
      {numPages > 1 && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem', marginTop: '1.5rem' }}>
          <button
            type="button"
            onClick={() => setPage(1)}
            disabled={page <= 1}
            className="btn btn-ghost btn-sm"
            style={{ fontSize: '0.80rem' }}
          >
            « First
          </button>
          <button
            type="button"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="btn btn-ghost btn-sm"
            style={{ fontSize: '0.80rem' }}
          >
            ‹ Prev
          </button>
          <span style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', padding: '0 0.5rem' }}>
            Page <strong>{page}</strong> of <strong>{numPages}</strong>
          </span>
          <button
            type="button"
            onClick={() => setPage((p) => Math.min(numPages, p + 1))}
            disabled={page >= numPages}
            className="btn btn-ghost btn-sm"
            style={{ fontSize: '0.80rem' }}
          >
            Next ›
          </button>
          <button
            type="button"
            onClick={() => setPage(numPages)}
            disabled={page >= numPages}
            className="btn btn-ghost btn-sm"
            style={{ fontSize: '0.80rem' }}
          >
            Last »
          </button>
        </div>
      )}
    </div>
  );
}

export default Alerts;
