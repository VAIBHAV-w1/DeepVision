import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../services/api';
import { cameraService } from '../services/camera';
import { useToast } from '../components/common/Toast';
import { useTranslation } from '../i18n/i18nContext';
import Surveillance from './Surveillance';

/**
 * DeepVision Cameras — Unified Surveillance & Camera Management Hub
 * 
 * Houses Two Primary Sub-Workspaces:
 * 1. Live Surveillance & Analytics (Multi-grid live video, AI overlays, telemetry)
 * 2. Camera Inventory & Configuration (Device registration, testing, edit, remove)
 */
export function Cameras({ onNavigate, initialCameraId, pageParams }) {
  const { t } = useTranslation();
  const { addToast } = useToast();

  // Tab State: 'live' (Live Surveillance & Analytics) | 'inventory' (Camera Inventory & Configuration)
  const [activeTab, setActiveTab] = useState(() => {
    if (pageParams?.tab === 'manage' || pageParams?.tab === 'inventory') return 'inventory';
    return 'live';
  });

  const [cameras, setCameras] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all'); // 'all' | 'online' | 'offline'
  const [search, setSearch] = useState('');
  const [viewMode, setViewMode] = useState('table'); // 'table' | 'grid'

  // Selected camera for live monitoring
  const [selectedCameraId, setSelectedCameraId] = useState(() => {
    const parsed = Number(initialCameraId || pageParams?.camera);
    return !Number.isNaN(parsed) && parsed > 0 ? parsed : 4;
  });

  // Sync when initialCameraId or pageParams changes
  useEffect(() => {
    const cid = Number(initialCameraId || pageParams?.camera);
    if (!Number.isNaN(cid) && cid > 0) {
      setSelectedCameraId(cid);
      if (pageParams?.tab !== 'manage' && pageParams?.tab !== 'inventory') {
        setActiveTab('live');
      }
    }
  }, [initialCameraId, pageParams]);

  // Modals & action state
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [editingCamera, setEditingCamera] = useState(null);
  const [deletingCamera, setDeletingCamera] = useState(null);
  const [testingSignalId, setTestingSignalId] = useState(null);
  const [testingModalConn, setTestingModalConn] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // Form state
  const [modalForm, setModalForm] = useState({
    name: '',
    source_type: 'webcam',
    source: '0',
    location: '',
    description: '',
  });

  // Fetch camera inventory
  const fetchCameras = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.cameras.list();
      const list = res.cameras || res || [];
      setCameras(Array.isArray(list) ? list : []);
    } catch (err) {
      console.warn('Failed to load cameras:', err);
      addToast(t('cameras.loadFailed', 'Failed to load camera inventory'), 'error');
    } finally {
      setLoading(false);
    }
  }, [addToast, t]);

  useEffect(() => {
    fetchCameras();
  }, [fetchCameras]);

  // Derived counts
  const onlineCameras = cameras.filter((c) => c.status === 'online');
  const offlineCameras = cameras.filter((c) => c.status !== 'online');
  const configuredSourceTypes = [...new Set(cameras.map((camera) => camera.source_type).filter(Boolean))];

  // Filtered cameras list
  const filteredCameras = cameras.filter((c) => {
    if (filter === 'online' && c.status !== 'online') return false;
    if (filter === 'offline' && c.status === 'online') return false;
    if (search.trim()) {
      const q = search.toLowerCase();
      const nameMatch = (c.name || '').toLowerCase().includes(q);
      const locMatch = (c.location || '').toLowerCase().includes(q);
      const typeMatch = (c.source_type || '').toLowerCase().includes(q);
      const srcMatch = String(c.source || '').toLowerCase().includes(q);
      return nameMatch || locMatch || typeMatch || srcMatch;
    }
    return true;
  });

  // Signal Test Handler for registered camera card
  const handleTestSignal = async (cam) => {
    try {
      setTestingSignalId(cam.id);
      addToast(`Testing signal for ${cam.name}...`, 'info');
      const res = await cameraService.testCamera(cam.id);
      if (res && (res.status === 'ok' || res.success)) {
        addToast(`Signal verified for ${cam.name} (Online)`, 'success');
      } else {
        addToast(res?.message || `Camera ${cam.name} is currently offline`, 'warning');
      }
      fetchCameras();
    } catch (err) {
      addToast(err?.message || `Camera ${cam.name} is offline or unreachable`, 'warning');
      fetchCameras();
    } finally {
      setTestingSignalId(null);
    }
  };

  // Pre-save Connection Test inside Modal
  const handleTestModalConnection = async () => {
    if (!modalForm.source.trim()) {
      addToast('Enter a source device index or stream URL first', 'warning');
      return;
    }
    try {
      setTestingModalConn(true);
      const res = await api.cameras.testConnection(modalForm.source_type, modalForm.source.trim());
      if (res && (res.success || res.status === 'ok')) {
        addToast(res.message || 'Camera connection verified!', 'success');
      } else {
        addToast(res?.message || res?.error || 'Could not open camera source', 'warning');
      }
    } catch (err) {
      addToast(err?.message || 'Connection test failed', 'error');
    } finally {
      setTestingModalConn(false);
    }
  };

  // Open in Live View Handler from card
  const handleOpenLive = (cameraId) => {
    setSelectedCameraId(cameraId);
    setActiveTab('live');
    if (onNavigate) {
      onNavigate('cameras', { tab: 'live', camera: cameraId });
    }
  };

  // Submit Add or Edit Camera (real backend persistence)
  const handleSubmitForm = async (e) => {
    e.preventDefault();
    if (!modalForm.name.trim()) {
      addToast('Camera name is required', 'warning');
      return;
    }
    try {
      setSubmitting(true);
      const payload = {
        name: modalForm.name.trim(),
        source_type: modalForm.source_type,
        source: modalForm.source.trim(),
        location: modalForm.location.trim(),
        description: modalForm.description.trim(),
      };
      if (editingCamera) {
        const res = await api.cameras.update(editingCamera.id, payload);
        if (res && res.success !== false) {
          addToast(`Camera "${payload.name}" updated`, 'success');
        }
      } else {
        const res = await api.cameras.create(payload);
        if (res && res.success !== false) {
          addToast(`Camera "${payload.name}" registered`, 'success');
        }
      }
      setIsAddModalOpen(false);
      setEditingCamera(null);
      await fetchCameras();
    } catch (err) {
      addToast(err?.message || 'Failed to save camera', 'error');
    } finally {
      setSubmitting(false);
    }
  };

  // Confirm Delete Camera (real backend persistence)
  const handleConfirmDelete = async () => {
    if (!deletingCamera) return;
    try {
      setSubmitting(true);
      const res = await api.cameras.remove(deletingCamera.id);
      addToast(res?.message || `Camera "${deletingCamera.name}" removed`, 'success');
      setDeletingCamera(null);
      await fetchCameras();
    } catch (err) {
      addToast(err?.message || 'Failed to remove camera', 'error');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="cameras-workspace-container cameras-page-container" style={{ maxWidth: '1700px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '16px' }}>
      
      {/* 1. Header Banner & Sub-Navigation Tabs */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem', borderBottom: '1px solid #1A2436', paddingBottom: '14px' }}>
        <div>
          <h1 style={{ fontSize: '1.4rem', fontWeight: 800, margin: '0 0 4px 0', color: 'var(--text-main, #F8FAFC)', letterSpacing: '-0.02em' }}>
            {t('cameras.title', 'Cameras & Surveillance')}
          </h1>
          <p style={{ fontSize: '0.84rem', color: 'var(--text-secondary, #94A3B8)', margin: 0 }}>
            {t('cameras.subtitle', 'Live video monitoring, real-time AI analytics, and camera hardware configuration')}
          </p>
        </div>

        {/* Top-Level Sub-Navigation Switcher */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', backgroundColor: '#070B13', padding: '4px', borderRadius: '8px', border: '1px solid #1A2436' }}>
          <button
            type="button"
            id="tab-cameras-live"
            onClick={() => {
              setActiveTab('live');
              if (onNavigate) onNavigate('cameras', { tab: 'live' });
            }}
            style={{
              padding: '7px 16px',
              borderRadius: '6px',
              fontSize: '0.82rem',
              fontWeight: activeTab === 'live' ? 700 : 500,
              backgroundColor: activeTab === 'live' ? '#2563EB' : 'transparent',
              color: activeTab === 'live' ? '#FFFFFF' : '#94A3B8',
              border: 'none',
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              transition: 'all 0.15s ease',
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polygon points="23 7 16 12 23 17 23 7" />
              <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
            </svg>
            <span>Live Surveillance & Analytics</span>
          </button>

          <button
            type="button"
            id="tab-cameras-inventory"
            onClick={() => {
              setActiveTab('inventory');
              if (onNavigate) onNavigate('cameras', { tab: 'manage' });
            }}
            style={{
              padding: '7px 16px',
              borderRadius: '6px',
              fontSize: '0.82rem',
              fontWeight: activeTab === 'inventory' ? 700 : 500,
              backgroundColor: activeTab === 'inventory' ? '#2563EB' : 'transparent',
              color: activeTab === 'inventory' ? '#FFFFFF' : '#94A3B8',
              border: 'none',
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              transition: 'all 0.15s ease',
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 20h9" />
              <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
            </svg>
            <span>Camera Inventory ({cameras.length})</span>
          </button>
        </div>
      </div>

      {/* 2. TAB 1: Live Surveillance & Analytics */}
      {activeTab === 'live' && (
        <section className="camera-detail-workspace" aria-label="Live Surveillance and Analytics">
          <Surveillance
            initialCameraId={selectedCameraId || 4}
            embedded
            onNavigate={onNavigate}
          />
        </section>
      )}

      {/* 3. TAB 2: Camera Inventory & Configuration */}
      {activeTab === 'inventory' && (
        <section className="camera-inventory-management-section" aria-label="Camera Inventory and Management">
          
          {/* Action Row: Title & Add Camera Button */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem', marginBottom: '1.25rem' }}>
            <div>
              <h2 style={{ fontSize: '1.25rem', fontWeight: 800, margin: '0 0 3px 0', color: '#F8FAFC', letterSpacing: '-0.02em' }}>
                Cameras
              </h2>
              <p style={{ fontSize: '0.84rem', color: '#94A3B8', margin: 0 }}>
                Manage and monitor your camera sources
              </p>
            </div>

            <button
              type="button"
              id="btn-add-camera-top"
              onClick={() => {
                setModalForm({ name: '', source_type: 'webcam', source: '0', location: '', description: '' });
                setEditingCamera(null);
                setIsAddModalOpen(true);
              }}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '8px',
                padding: '8px 18px',
                borderRadius: '8px',
                fontSize: '0.84rem',
                fontWeight: 700,
                backgroundColor: '#2563EB',
                color: '#FFFFFF',
                border: 'none',
                cursor: 'pointer',
                boxShadow: '0 2px 10px rgba(37, 99, 235, 0.4)',
                transition: 'background 0.15s ease',
              }}
              onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#1D4ED8'}
              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = '#2563EB'}
            >
              <span style={{ fontSize: '1.1rem', lineHeight: 1 }}>+</span>
              <span>{t('dashboard.addCamera', 'Add Camera')}</span>
            </button>
          </div>

          {/* Metric Cards Row */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
              gap: '12px',
              marginBottom: '1.25rem',
            }}
          >
            <div style={{ padding: '14px 18px', borderRadius: '8px', backgroundColor: 'var(--bg-surface, #0F172A)', border: '1px solid var(--border-color, #1E293B)' }}>
              <div style={{ fontSize: '0.74rem', color: 'var(--text-muted, #64748B)', textTransform: 'uppercase', fontWeight: 600 }}>
                Registered Cameras
              </div>
              <div id="metric-total-cameras" style={{ fontSize: '1.6rem', fontWeight: 800, color: 'var(--text-main, #F8FAFC)', marginTop: '4px' }}>
                {cameras.length}
              </div>
            </div>

            <div style={{ padding: '14px 18px', borderRadius: '8px', backgroundColor: 'var(--bg-surface, #0F172A)', border: '1px solid var(--border-color, #1E293B)' }}>
              <div style={{ fontSize: '0.74rem', color: 'var(--color-live, #00E676)', textTransform: 'uppercase', fontWeight: 600 }}>
                Online Live Channels
              </div>
              <div id="metric-online-cameras" style={{ fontSize: '1.6rem', fontWeight: 800, color: 'var(--color-live, #00E676)', marginTop: '4px' }}>
                {onlineCameras.length}
              </div>
            </div>

            <div style={{ padding: '14px 18px', borderRadius: '8px', backgroundColor: 'var(--bg-surface, #0F172A)', border: '1px solid var(--border-color, #1E293B)' }}>
              <div style={{ fontSize: '0.74rem', color: 'var(--text-muted, #64748B)', textTransform: 'uppercase', fontWeight: 600 }}>
                Offline / Standby
              </div>
              <div id="metric-offline-cameras" style={{ fontSize: '1.6rem', fontWeight: 800, color: 'var(--text-secondary, #94A3B8)', marginTop: '4px' }}>
                {offlineCameras.length}
              </div>
            </div>

            <div style={{ padding: '14px 18px', borderRadius: '8px', backgroundColor: 'var(--bg-surface, #0F172A)', border: '1px solid var(--border-color, #1E293B)' }}>
              <div style={{ fontSize: '0.74rem', color: 'var(--dv-cyan-500, #00D2FF)', textTransform: 'uppercase', fontWeight: 600 }}>
                Configured Source Types
              </div>
              <div style={{ fontSize: '0.88rem', fontWeight: 700, color: 'var(--text-main, #F8FAFC)', marginTop: '6px' }}>
                {configuredSourceTypes.length}
              </div>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary, #94A3B8)', marginTop: '3px' }}>
                {configuredSourceTypes.join(', ') || 'No sources configured'}
              </div>
            </div>
          </div>

          {/* Controls & Filter Bar matching Figure 7.1.3 */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: '12px',
              padding: '12px 16px',
              borderRadius: '8px',
              backgroundColor: '#0D1527',
              border: '1px solid #1A253C',
              marginBottom: '1.25rem',
            }}
          >
            {/* Left: Search Input matching Figure 7.1.3 */}
            <div style={{ position: 'relative', width: '320px', maxWidth: '100%' }}>
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="#64748B"
                strokeWidth="2"
                style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)' }}
              >
                <circle cx="11" cy="11" r="8" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
              <input
                type="text"
                id="input-search-cameras"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search cameras..."
                style={{
                  padding: '8px 14px 8px 36px',
                  borderRadius: '8px',
                  fontSize: '0.84rem',
                  border: '1px solid #1E293B',
                  backgroundColor: '#070B13',
                  color: '#F8FAFC',
                  width: '100%',
                  outline: 'none',
                }}
              />
            </div>

            {/* Right: All Status dropdown & View Mode Toggle */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
              {/* All Status Dropdown */}
              <select
                id="select-camera-status"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                style={{
                  padding: '8px 14px',
                  borderRadius: '8px',
                  fontSize: '0.82rem',
                  fontWeight: 600,
                  backgroundColor: '#070B13',
                  color: '#E2E8F0',
                  border: '1px solid #1E293B',
                  cursor: 'pointer',
                  outline: 'none',
                }}
              >
                <option value="all">All Status ({cameras.length})</option>
                <option value="online">Online ({onlineCameras.length})</option>
                <option value="offline">Offline ({offlineCameras.length})</option>
              </select>

              {/* View Layout Toggle: Table vs Grid */}
              <div style={{ display: 'inline-flex', backgroundColor: '#070B13', padding: '3px', borderRadius: '6px', border: '1px solid #1E293B' }}>
                <button
                  type="button"
                  id="btn-view-table"
                  onClick={() => setViewMode('table')}
                  title="Table View (Figure 7.1.3)"
                  style={{
                    padding: '6px 10px',
                    borderRadius: '4px',
                    backgroundColor: viewMode === 'table' ? '#2563EB' : 'transparent',
                    color: viewMode === 'table' ? '#FFFFFF' : '#94A3B8',
                    border: 'none',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                    fontSize: '0.78rem',
                    fontWeight: 600,
                  }}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <line x1="3" y1="6" x2="21" y2="6" />
                    <line x1="3" y1="12" x2="21" y2="12" />
                    <line x1="3" y1="18" x2="21" y2="18" />
                  </svg>
                  <span>Table</span>
                </button>
                <button
                  type="button"
                  id="btn-view-grid"
                  onClick={() => setViewMode('grid')}
                  title="Grid View"
                  style={{
                    padding: '6px 10px',
                    borderRadius: '4px',
                    backgroundColor: viewMode === 'grid' ? '#2563EB' : 'transparent',
                    color: viewMode === 'grid' ? '#FFFFFF' : '#94A3B8',
                    border: 'none',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                    fontSize: '0.78rem',
                    fontWeight: 600,
                  }}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <rect x="3" y="3" width="7" height="7" />
                    <rect x="14" y="3" width="7" height="7" />
                    <rect x="14" y="14" width="7" height="7" />
                    <rect x="3" y="14" width="7" height="7" />
                  </svg>
                  <span>Grid</span>
                </button>
              </div>
            </div>
          </div>

          {/* Loading state */}
          {loading && (
            <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
              <div style={{ width: '32px', height: '32px', border: '3px solid var(--border-color)', borderTopColor: 'var(--dv-cyan-500, #00D2FF)', borderRadius: '50%', animation: 'spin 0.8s linear infinite', margin: '0 auto 12px auto' }} />
              <span>Loading registered cameras...</span>
            </div>
          )}

          {/* Empty state */}
          {!loading && filteredCameras.length === 0 && (
            <div style={{ textAlign: 'center', padding: '3rem', backgroundColor: 'var(--bg-surface)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', margin: '0 0 12px 0' }}>
                No cameras matched your filter criteria.
              </p>
              <button
                type="button"
                onClick={() => {
                  setFilter('all');
                  setSearch('');
                }}
                className="btn btn-secondary btn-sm"
              >
                Reset Filters
              </button>
            </div>
          )}

          {/* Table View matching Figure 7.1.3 */}
          {!loading && filteredCameras.length > 0 && viewMode === 'table' && (
            <div style={{ backgroundColor: '#0D1527', border: '1px solid #1A253C', borderRadius: '10px', overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', minWidth: '600px' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #1A253C', color: '#94A3B8', fontSize: '0.78rem', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    <th style={{ padding: '12px 18px', fontWeight: 600 }}>Camera</th>
                    <th style={{ padding: '12px 18px', fontWeight: 600 }}>Source</th>
                    <th style={{ padding: '12px 18px', fontWeight: 600 }}>Status</th>
                    <th style={{ padding: '12px 18px', fontWeight: 600, textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredCameras.map((cam) => {
                    const isOnline = cam.status === 'online';
                    const sourceTypeLabel = cam.source_type === 'webcam' ? 'USB Camera' : cam.source_type === 'rtsp' ? 'RTSP' : 'IP Camera';
                    return (
                      <tr
                        key={cam.id}
                        data-camera-id={cam.id}
                        style={{
                          borderBottom: '1px solid rgba(255, 255, 255, 0.04)',
                          transition: 'background 0.15s ease',
                        }}
                        onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.02)'}
                        onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                      >
                        {/* Camera Column (Thumbnail + Name) */}
                        <td style={{ padding: '12px 18px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                            <div
                              style={{
                                width: '56px',
                                height: '36px',
                                borderRadius: '6px',
                                backgroundColor: '#070B13',
                                border: '1px solid #1E293B',
                                overflow: 'hidden',
                                flexShrink: 0,
                                position: 'relative',
                              }}
                            >
                              <img
                                src={`/api/cameras/${cam.id}/snapshot/?t=${Date.now()}`}
                                alt={cam.name}
                                style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                                onError={(e) => {
                                  e.currentTarget.style.display = 'none';
                                }}
                              />
                            </div>
                            <div>
                              <div style={{ fontSize: '0.88rem', fontWeight: 700, color: '#F8FAFC' }}>
                                {cam.name} {cam.location ? `(${cam.location})` : ''}
                              </div>
                              <div style={{ fontSize: '0.72rem', color: '#64748B', fontFamily: 'monospace' }}>
                                CH-{String(cam.id).padStart(2, '0')} • {cam.source || '0'}
                              </div>
                            </div>
                          </div>
                        </td>

                        {/* Source Column */}
                        <td style={{ padding: '12px 18px', fontSize: '0.82rem', color: '#CBD5E1' }}>
                          {sourceTypeLabel}
                        </td>

                        {/* Status Column */}
                        <td style={{ padding: '12px 18px' }}>
                          <span
                            style={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              padding: '3px 10px',
                              borderRadius: '12px',
                              fontSize: '0.74rem',
                              fontWeight: 700,
                              backgroundColor: isOnline ? 'rgba(16, 185, 129, 0.15)' : 'rgba(239, 68, 68, 0.15)',
                              color: isOnline ? '#10B981' : '#EF4444',
                              border: `1px solid ${isOnline ? 'rgba(16, 185, 129, 0.35)' : 'rgba(239, 68, 68, 0.35)'}`,
                            }}
                          >
                            {isOnline ? 'Online' : 'Offline'}
                          </span>
                        </td>

                        {/* Actions Column matching Figure 7.1.3 */}
                        <td style={{ padding: '12px 18px', textAlign: 'right' }}>
                          <div style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
                            {/* Play Button (Blue) -> Opens Live Surveillance */}
                            <button
                              type="button"
                              id={`btn-live-cam-${cam.id}`}
                              onClick={() => handleOpenLive(cam.id)}
                              title="Open Live Surveillance & Analytics"
                              style={{
                                width: '32px',
                                height: '32px',
                                borderRadius: '6px',
                                backgroundColor: '#2563EB',
                                border: 'none',
                                color: '#FFFFFF',
                                cursor: 'pointer',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                transition: 'background 0.15s ease',
                              }}
                              onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#1D4ED8'}
                              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = '#2563EB'}
                            >
                              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                                <polygon points="5 3 19 12 5 21 5 3" />
                              </svg>
                            </button>

                            {/* Edit Button */}
                            <button
                              type="button"
                              id={`btn-edit-cam-${cam.id}`}
                              onClick={() => {
                                setEditingCamera(cam);
                                setModalForm({
                                  name: cam.name || '',
                                  source_type: cam.source_type || 'webcam',
                                  source: cam.source || '',
                                  location: cam.location || '',
                                  description: cam.description || '',
                                });
                                setIsAddModalOpen(true);
                              }}
                              title="Edit Camera Configuration"
                              style={{
                                width: '32px',
                                height: '32px',
                                borderRadius: '6px',
                                backgroundColor: 'rgba(255, 255, 255, 0.05)',
                                border: '1px solid rgba(255, 255, 255, 0.1)',
                                color: '#CBD5E1',
                                cursor: 'pointer',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                transition: 'all 0.15s ease',
                              }}
                              onMouseEnter={(e) => {
                                e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.1)';
                                e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.2)';
                              }}
                              onMouseLeave={(e) => {
                                e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.05)';
                                e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.1)';
                              }}
                            >
                              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <path d="M12 20h9" />
                                <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
                              </svg>
                            </button>

                            {/* Delete Button */}
                            <button
                              type="button"
                              id={`btn-delete-cam-${cam.id}`}
                              onClick={() => setDeletingCamera(cam)}
                              title="Remove Camera"
                              style={{
                                width: '32px',
                                height: '32px',
                                borderRadius: '6px',
                                backgroundColor: 'rgba(239, 68, 68, 0.1)',
                                border: '1px solid rgba(239, 68, 68, 0.25)',
                                color: '#EF4444',
                                cursor: 'pointer',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                transition: 'all 0.15s ease',
                              }}
                              onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'rgba(239, 68, 68, 0.2)'}
                              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'rgba(239, 68, 68, 0.1)'}
                            >
                              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <polyline points="3 6 5 6 21 6" />
                                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                              </svg>
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Camera Inventory Cards Grid when viewMode === 'grid' */}
          {!loading && filteredCameras.length > 0 && viewMode === 'grid' && (
            <div
              className="manage-cameras-grid cameras-grid-container"
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
                gap: '16px',
              }}
            >
              {filteredCameras.map((cam) => {
                const isOnline = cam.status === 'online';

                return (
                  <div
                    key={cam.id}
                    data-camera-id={cam.id}
                    className="camera-inventory-card camera-card card"
                    style={{
                      backgroundColor: 'var(--bg-surface, #0F172A)',
                      borderRadius: '8px',
                      border: '1px solid var(--border-color, #1E293B)',
                      overflow: 'hidden',
                      display: 'flex',
                      flexDirection: 'column',
                    }}
                  >
                    {/* Card Header */}
                    <div
                      style={{
                        padding: '12px 16px',
                        borderBottom: '1px solid var(--border-color, #1E293B)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: '8px',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0 }}>
                        <span
                          style={{
                            width: '9px',
                            height: '9px',
                            borderRadius: '50%',
                            backgroundColor: isOnline ? 'var(--color-live, #00E676)' : 'var(--color-offline, #64748B)',
                            flexShrink: 0,
                          }}
                        />
                        <span
                          style={{
                            fontSize: '0.92rem',
                            fontWeight: 700,
                            color: 'var(--text-main, #F8FAFC)',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {cam.name}
                        </span>
                      </div>

                      <span
                        style={{
                          fontSize: '0.68rem',
                          fontWeight: 700,
                          padding: '2px 8px',
                          borderRadius: '4px',
                          backgroundColor: isOnline ? 'rgba(0, 230, 118, 0.15)' : 'rgba(100, 116, 139, 0.15)',
                          color: isOnline ? 'var(--color-live, #00E676)' : 'var(--text-muted, #64748B)',
                          letterSpacing: '0.04em',
                          flexShrink: 0,
                        }}
                      >
                        CH-{String(cam.id).padStart(2, '0')} • {isOnline ? 'ONLINE' : 'OFFLINE'}
                      </span>
                    </div>

                    {/* Card Body: Camera Specifications */}
                    <div style={{ padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: '8px', flex: 1 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem' }}>
                        <span style={{ color: 'var(--text-muted, #64748B)' }}>Source Type:</span>
                        <span style={{ color: 'var(--text-main, #F8FAFC)', fontWeight: 600 }}>{cam.source_type || 'webcam'}</span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem', gap: '10px' }}>
                        <span style={{ color: 'var(--text-muted, #64748B)', flexShrink: 0 }}>Source Address:</span>
                        <span
                          title={String(cam.source ?? '0')}
                          style={{
                            color: 'var(--text-secondary, #94A3B8)',
                            fontFamily: 'var(--font-mono, monospace)',
                            maxWidth: '190px',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {cam.source ?? '0'}
                        </span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem' }}>
                        <span style={{ color: 'var(--text-muted, #64748B)' }}>Location:</span>
                        <span style={{ color: 'var(--text-main, #F8FAFC)' }}>{cam.location || 'Perimeter Optical Zone'}</span>
                      </div>
                    </div>

                    {/* Card Footer: Action Buttons */}
                    <div
                      style={{
                        padding: '10px 16px',
                        borderTop: '1px solid var(--border-color, #1E293B)',
                        backgroundColor: 'var(--bg-canvas, #080C14)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: '8px',
                      }}
                    >
                      <button
                        type="button"
                        id={`btn-open-live-${cam.id}`}
                        onClick={() => handleOpenLive(cam.id)}
                        style={{
                          padding: '6px 12px',
                          borderRadius: '5px',
                          fontSize: '0.76rem',
                          fontWeight: 700,
                          backgroundColor: 'var(--dv-cyan-500, #00D2FF)',
                          color: '#080C14',
                          border: 'none',
                          cursor: 'pointer',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '5px',
                        }}
                      >
                        <span>▶ </span>
                        <span>Open Live View</span>
                      </button>

                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <button
                          type="button"
                          id={`btn-test-signal-${cam.id}`}
                          disabled={testingSignalId === cam.id}
                          onClick={() => handleTestSignal(cam)}
                          title="Verify live camera hardware signal"
                          style={{
                            padding: '6px 10px',
                            borderRadius: '5px',
                            fontSize: '0.74rem',
                            fontWeight: 600,
                            backgroundColor: 'transparent',
                            color: 'var(--text-secondary, #94A3B8)',
                            border: '1px solid var(--border-color, #1E293B)',
                            cursor: 'pointer',
                          }}
                        >
                          {testingSignalId === cam.id ? 'Testing...' : 'Test Signal'}
                        </button>

                        <button
                          type="button"
                          id={`btn-edit-camera-${cam.id}`}
                          onClick={() => {
                            setEditingCamera(cam);
                            setModalForm({
                              name: cam.name || '',
                              source_type: cam.source_type || 'webcam',
                              source: String(cam.source ?? '0'),
                              location: cam.location || '',
                              description: cam.description || '',
                            });
                            setIsAddModalOpen(true);
                          }}
                          title="Edit camera parameters"
                          style={{
                            padding: '6px 10px',
                            borderRadius: '5px',
                            fontSize: '0.74rem',
                            fontWeight: 600,
                            backgroundColor: 'transparent',
                            color: 'var(--text-secondary, #94A3B8)',
                            border: '1px solid var(--border-color, #1E293B)',
                            cursor: 'pointer',
                          }}
                        >
                          Edit
                        </button>

                        <button
                          type="button"
                          id={`btn-delete-camera-${cam.id}`}
                          onClick={() => setDeletingCamera(cam)}
                          title="Remove camera from registry"
                          style={{
                            padding: '6px 10px',
                            borderRadius: '5px',
                            fontSize: '0.74rem',
                            fontWeight: 600,
                            backgroundColor: 'transparent',
                            color: 'var(--color-critical, #EF4444)',
                            border: '1px solid var(--border-color, #1E293B)',
                            cursor: 'pointer',
                          }}
                        >
                          Remove
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

        </section>
      )}

      {/* Add / Edit Camera Modal */}
      {isAddModalOpen && (
        <div
          className="modal-backdrop"
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.75)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1100,
            padding: '16px',
          }}
        >
          <div
            className="modal-content"
            style={{
              backgroundColor: 'var(--bg-surface, #0F172A)',
              border: '1px solid var(--border-color, #1E293B)',
              borderRadius: '8px',
              width: '100%',
              maxWidth: '520px',
              padding: '24px',
              display: 'flex',
              flexDirection: 'column',
              gap: '16px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 800, color: 'var(--text-main, #F8FAFC)' }}>
                {editingCamera ? `Edit Camera: ${editingCamera.name}` : 'Register New Camera'}
              </h3>
              <button
                type="button"
                onClick={() => {
                  setIsAddModalOpen(false);
                  setEditingCamera(null);
                }}
                style={{ background: 'none', border: 'none', color: 'var(--text-muted, #64748B)', fontSize: '1.2rem', cursor: 'pointer' }}
              >
                &times;
              </button>
            </div>

            <form onSubmit={handleSubmitForm} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.78rem', fontWeight: 700, color: 'var(--text-secondary, #94A3B8)', marginBottom: '4px' }}>
                  Camera Name *
                </label>
                <input
                  type="text"
                  required
                  id="modal-input-name"
                  value={modalForm.name}
                  onChange={(e) => setModalForm({ ...modalForm, name: e.target.value })}
                  placeholder="e.g. Cam-05 (Server Room)"
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    borderRadius: '6px',
                    fontSize: '0.84rem',
                    border: '1px solid var(--border-color, #1E293B)',
                    backgroundColor: 'var(--bg-canvas, #080C14)',
                    color: 'var(--text-main, #F8FAFC)',
                    boxSizing: 'border-box',
                  }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.78rem', fontWeight: 700, color: 'var(--text-secondary, #94A3B8)', marginBottom: '4px' }}>
                  Source Type
                </label>
                <select
                  id="modal-select-source-type"
                  value={modalForm.source_type}
                  onChange={(e) => setModalForm({ ...modalForm, source_type: e.target.value })}
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    borderRadius: '6px',
                    fontSize: '0.84rem',
                    border: '1px solid var(--border-color, #1E293B)',
                    backgroundColor: 'var(--bg-canvas, #080C14)',
                    color: 'var(--text-main, #F8FAFC)',
                    boxSizing: 'border-box',
                  }}
                >
                  <option value="webcam">Physical USB / DirectShow Camera</option>
                  <option value="rtsp">RTSP Network Video Stream</option>
                  <option value="ip_camera">IP Camera (HTTP / MJPEG)</option>
                  <option value="video_file">Pre-recorded Video Source</option>
                </select>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.78rem', fontWeight: 700, color: 'var(--text-secondary, #94A3B8)', marginBottom: '4px' }}>
                  Source Index or Stream URL *
                </label>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <input
                    type="text"
                    required
                    id="modal-input-source"
                    value={modalForm.source}
                    onChange={(e) => setModalForm({ ...modalForm, source: e.target.value })}
                    placeholder={modalForm.source_type === 'webcam' ? 'Device index (e.g. 0 or 1)' : 'rtsp://user:pass@ip:554/live'}
                    style={{
                      flex: 1,
                      padding: '8px 12px',
                      borderRadius: '6px',
                      fontSize: '0.84rem',
                      border: '1px solid var(--border-color, #1E293B)',
                      backgroundColor: 'var(--bg-canvas, #080C14)',
                      color: 'var(--text-main, #F8FAFC)',
                      fontFamily: 'var(--font-mono, monospace)',
                      boxSizing: 'border-box',
                    }}
                  />
                  <button
                    type="button"
                    id="btn-test-modal-connection"
                    disabled={testingModalConn}
                    onClick={handleTestModalConnection}
                    style={{
                      padding: '8px 14px',
                      borderRadius: '6px',
                      fontSize: '0.78rem',
                      fontWeight: 700,
                      backgroundColor: 'var(--bg-surface-raised, #1E293B)',
                      color: 'var(--text-main, #F8FAFC)',
                      border: '1px solid var(--border-color, #1E293B)',
                      cursor: 'pointer',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {testingModalConn ? 'Testing...' : 'Test Feed'}
                  </button>
                </div>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.78rem', fontWeight: 700, color: 'var(--text-secondary, #94A3B8)', marginBottom: '4px' }}>
                  Location / Zone
                </label>
                <input
                  type="text"
                  id="modal-input-location"
                  value={modalForm.location}
                  onChange={(e) => setModalForm({ ...modalForm, location: e.target.value })}
                  placeholder="e.g. North Gate Access Road"
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    borderRadius: '6px',
                    fontSize: '0.84rem',
                    border: '1px solid var(--border-color, #1E293B)',
                    backgroundColor: 'var(--bg-canvas, #080C14)',
                    color: 'var(--text-main, #F8FAFC)',
                    boxSizing: 'border-box',
                  }}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '8px' }}>
                <button
                  type="button"
                  onClick={() => {
                    setIsAddModalOpen(false);
                    setEditingCamera(null);
                  }}
                  style={{
                    padding: '8px 16px',
                    borderRadius: '6px',
                    backgroundColor: 'transparent',
                    border: '1px solid var(--border-color, #1E293B)',
                    color: 'var(--text-secondary, #94A3B8)',
                    cursor: 'pointer',
                    fontSize: '0.82rem',
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  id="btn-submit-camera-form"
                  disabled={submitting}
                  style={{
                    padding: '8px 20px',
                    borderRadius: '6px',
                    backgroundColor: 'var(--dv-cyan-500, #00D2FF)',
                    color: '#080C14',
                    border: 'none',
                    fontWeight: 700,
                    cursor: 'pointer',
                    fontSize: '0.82rem',
                  }}
                >
                  {submitting ? 'Saving...' : editingCamera ? 'Save Changes' : 'Register Camera'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deletingCamera && (
        <div
          className="modal-backdrop"
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.75)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1100,
            padding: '16px',
          }}
        >
          <div
            className="modal-content"
            style={{
              backgroundColor: 'var(--bg-surface, #0F172A)',
              border: '1px solid var(--border-color, #1E293B)',
              borderRadius: '8px',
              width: '100%',
              maxWidth: '420px',
              padding: '20px',
              display: 'flex',
              flexDirection: 'column',
              gap: '14px',
            }}
          >
            <h3 style={{ margin: 0, fontSize: '1.02rem', fontWeight: 700, color: 'var(--text-main, #F8FAFC)' }}>
              Remove Camera "{deletingCamera.name}"?
            </h3>
            <p style={{ margin: 0, fontSize: '0.83rem', color: 'var(--text-secondary, #94A3B8)', lineHeight: 1.5 }}>
              Any historical recordings, alerts, and forensic evidence tied to this camera will remain safely preserved in the database.
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '4px' }}>
              <button
                type="button"
                onClick={() => setDeletingCamera(null)}
                style={{
                  padding: '8px 14px',
                  borderRadius: '6px',
                  backgroundColor: 'transparent',
                  border: '1px solid var(--border-color, #1E293B)',
                  color: 'var(--text-secondary)',
                  cursor: 'pointer',
                  fontSize: '0.8rem',
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                id="btn-confirm-delete-camera"
                disabled={submitting}
                onClick={handleConfirmDelete}
                style={{
                  padding: '8px 16px',
                  borderRadius: '6px',
                  backgroundColor: 'var(--color-critical, #EF4444)',
                  color: '#FFFFFF',
                  border: 'none',
                  fontWeight: 700,
                  cursor: 'pointer',
                  fontSize: '0.8rem',
                }}
              >
                {submitting ? 'Removing...' : 'Confirm Remove'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default Cameras;
