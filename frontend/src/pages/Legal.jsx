import React, { useState, useEffect } from 'react';

export function Legal({ initialTab = 'privacy', onNavigate }) {
  const [activeTab, setActiveTab] = useState(initialTab);

  useEffect(() => {
    if (initialTab) {
      setActiveTab(initialTab);
    }
  }, [initialTab]);

  return (
    <div style={{ maxWidth: '960px', margin: '0 auto', paddingBottom: '3.5rem' }}>
      {/* Header */}
      <div style={{ marginBottom: '1.75rem' }}>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', background: 'rgba(16, 185, 129, 0.12)', border: '1px solid rgba(16, 185, 129, 0.3)', color: '#10b981', padding: '4px 12px', borderRadius: '4px', fontSize: '0.72rem', fontWeight: 800, letterSpacing: '0.06em', marginBottom: '8px' }}>
          <span>SECURITY &amp; COMPLIANCE DISCLOSURE</span>
        </div>
        <h1 style={{ fontSize: '1.65rem', fontWeight: 700, margin: '2px 0 6px 0', letterSpacing: '-0.02em', color: 'var(--text-main)' }}>
          Legal, Privacy &amp; Operational Governance
        </h1>
        <p style={{ fontSize: '0.86rem', color: 'var(--text-secondary)', margin: 0 }}>
          Authoritative technical specifications for surveillance media retention, telemetry handling, and service conditions.
        </p>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '8px', borderBottom: '1px solid var(--border-color)', marginBottom: '1.5rem' }}>
        <button
          type="button"
          onClick={() => setActiveTab('privacy')}
          style={{
            padding: '10px 16px',
            background: 'none',
            border: 'none',
            borderBottom: activeTab === 'privacy' ? '2px solid var(--color-primary, #10b981)' : '2px solid transparent',
            color: activeTab === 'privacy' ? 'var(--text-main)' : 'var(--text-secondary)',
            fontWeight: activeTab === 'privacy' ? 700 : 500,
            cursor: 'pointer',
            fontSize: '0.88rem'
          }}
        >
          Privacy Policy
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('terms')}
          style={{
            padding: '10px 16px',
            background: 'none',
            border: 'none',
            borderBottom: activeTab === 'terms' ? '2px solid var(--color-primary, #10b981)' : '2px solid transparent',
            color: activeTab === 'terms' ? 'var(--text-main)' : 'var(--text-secondary)',
            fontWeight: activeTab === 'terms' ? 700 : 500,
            cursor: 'pointer',
            fontSize: '0.88rem'
          }}
        >
          Terms of Service
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('cookies')}
          style={{
            padding: '10px 16px',
            background: 'none',
            border: 'none',
            borderBottom: activeTab === 'cookies' ? '2px solid var(--color-primary, #10b981)' : '2px solid transparent',
            color: activeTab === 'cookies' ? 'var(--text-main)' : 'var(--text-secondary)',
            fontWeight: activeTab === 'cookies' ? 700 : 500,
            cursor: 'pointer',
            fontSize: '0.88rem'
          }}
        >
          Cookies &amp; Local Storage
        </button>
      </div>

      {/* Tab 1: Privacy Policy */}
      {activeTab === 'privacy' && (
        <div className="card" style={{ padding: '2rem', background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-sm)', lineHeight: 1.6 }}>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-main)', marginTop: 0, marginBottom: '1rem' }}>
            1. Surveillance Data Collection &amp; Scope
          </h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.88rem', marginBottom: '1.25rem' }}>
            DeepVision operates as a Security Operations Center (SOC) management suite. The application processes surveillance video streams ingested from configured hardware endpoints (DirectShow webcams, RTSP streams, and network cameras).
          </p>

          <h3 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-main)', marginBottom: '0.5rem' }}>
            A. Real-Time Neural Processing
          </h3>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.88rem', marginBottom: '1.25rem' }}>
            When running in Tracking &amp; Detection mode, video frames are processed locally or within authorized serverless boundaries using YOLO11n object detection and ByteTrack tracking. Extracted bounding boxes and trajectories are rendered in-stream. No biometric facial recognition data or biometric templates are stored unless explicitly configured by the site administrator.
          </p>

          <h3 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-main)', marginBottom: '0.5rem' }}>
            B. Video Recordings &amp; Forensic Evidence
          </h3>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.88rem', marginBottom: '1.25rem' }}>
            Continuous recordings and incident snapshots captured by operators or trigger rules are persisted into designated encrypted storage volumes. Media files are accessible only to authenticated operators assigned to the respective surveillance channels.
          </p>

          <h3 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-main)', marginBottom: '0.5rem' }}>
            C. Operator Access &amp; Audit Logs
          </h3>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.88rem', margin: 0 }}>
            Every operator action (authentication attempts, stream access, evidence viewing, and case creation) is recorded in immutable security audit logs with source IP address, user identifier, and timestamp to satisfy operational integrity standards.
          </p>
        </div>
      )}

      {/* Tab 2: Terms of Service */}
      {activeTab === 'terms' && (
        <div className="card" style={{ padding: '2rem', background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-sm)', lineHeight: 1.6 }}>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-main)', marginTop: 0, marginBottom: '1rem' }}>
            1. Authorized Operational Use
          </h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.88rem', marginBottom: '1.25rem' }}>
            DeepVision is intended exclusively for authorized surveillance monitoring, facility protection, and security management. Operators must possess legal authorization to monitor designated zones and cameras.
          </p>

          <h3 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-main)', marginBottom: '0.5rem' }}>
            2. Account Responsibility &amp; MFA
          </h3>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.88rem', marginBottom: '1.25rem' }}>
            All operator accounts require verified email credentials and mandatory single-use One-Time Passwords (OTP) for authentication. Account credentials must not be shared. Sessions are automatically terminated upon timeout or sign-out.
          </p>

          <h3 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-main)', marginBottom: '0.5rem' }}>
            3. Rate Limiting &amp; System Protection
          </h3>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.88rem', marginBottom: '1.25rem' }}>
            All API endpoints enforce backend rate limits. Automated scraping, unauthorized probing, credential stuffing, and denial-of-service attempts result in immediate HTTP 429 throttling and IP-level suspension.
          </p>

          <h3 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-main)', marginBottom: '0.5rem' }}>
            4. Service Availability &amp; Edge Hardware
          </h3>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.88rem', margin: 0 }}>
            Physical camera streams depend upon host hardware network stability and local camera bridge availability. DeepVision provides continuous signal health monitoring and reconnection routines, but cannot guarantee uninterrupted video capture across hardware power loss or third-party ISP disconnections.
          </p>
        </div>
      )}

      {/* Tab 3: Cookies & Local Storage */}
      {activeTab === 'cookies' && (
        <div className="card" style={{ padding: '2rem', background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-sm)', lineHeight: 1.6 }}>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-main)', marginTop: 0, marginBottom: '1rem' }}>
            Technical Storage &amp; Cookie Specifications
          </h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.88rem', marginBottom: '1.5rem' }}>
            DeepVision uses strictly necessary cookies and local storage tokens required for secure authentication, CSRF defense, and user interface preferences. No third-party advertising cookies or trackers are utilized.
          </p>

          <div style={{ overflowX: 'auto', marginBottom: '1.5rem' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.84rem' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border-color)', textAlign: 'left', color: 'var(--text-secondary)' }}>
                  <th style={{ padding: '8px 12px' }}>Key / Cookie</th>
                  <th style={{ padding: '8px 12px' }}>Type</th>
                  <th style={{ padding: '8px 12px' }}>Purpose</th>
                  <th style={{ padding: '8px 12px' }}>Lifespan</th>
                </tr>
              </thead>
              <tbody>
                <tr style={{ borderBottom: '1px solid var(--border-color)' }}>
                  <td style={{ padding: '8px 12px', fontFamily: 'var(--font-mono)', color: 'var(--text-main)' }}>deepvision_django_session</td>
                  <td style={{ padding: '8px 12px', color: 'var(--text-secondary)' }}>HTTP Cookie (Signed)</td>
                  <td style={{ padding: '8px 12px', color: 'var(--text-secondary)' }}>Maintains operator authenticated session state</td>
                  <td style={{ padding: '8px 12px', color: 'var(--text-secondary)' }}>Session / 14 Days</td>
                </tr>
                <tr style={{ borderBottom: '1px solid var(--border-color)' }}>
                  <td style={{ padding: '8px 12px', fontFamily: 'var(--font-mono)', color: 'var(--text-main)' }}>csrftoken</td>
                  <td style={{ padding: '8px 12px', color: 'var(--text-secondary)' }}>HTTP Cookie</td>
                  <td style={{ padding: '8px 12px', color: 'var(--text-secondary)' }}>Cross-Site Request Forgery (CSRF) protection token</td>
                  <td style={{ padding: '8px 12px', color: 'var(--text-secondary)' }}>1 Year</td>
                </tr>
                <tr style={{ borderBottom: '1px solid var(--border-color)' }}>
                  <td style={{ padding: '8px 12px', fontFamily: 'var(--font-mono)', color: 'var(--text-main)' }}>deepvision_theme</td>
                  <td style={{ padding: '8px 12px', color: 'var(--text-secondary)' }}>localStorage</td>
                  <td style={{ padding: '8px 12px', color: 'var(--text-secondary)' }}>Stores operator theme choice ('dark', 'light', 'system')</td>
                  <td style={{ padding: '8px 12px', color: 'var(--text-secondary)' }}>Persistent</td>
                </tr>
                <tr style={{ borderBottom: '1px solid var(--border-color)' }}>
                  <td style={{ padding: '8px 12px', fontFamily: 'var(--font-mono)', color: 'var(--text-main)' }}>deepvision_lang</td>
                  <td style={{ padding: '8px 12px', color: 'var(--text-secondary)' }}>localStorage</td>
                  <td style={{ padding: '8px 12px', color: 'var(--text-secondary)' }}>Stores selected operator interface language (22 languages)</td>
                  <td style={{ padding: '8px 12px', color: 'var(--text-secondary)' }}>Persistent</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

export default Legal;
