import React, { useState, useEffect } from "react";
import { api } from "../services/api";
import { useAuth } from "../hooks/useAuth";
import { useToast } from "../components/common/Toast";
import { useTranslation } from "../i18n/i18nContext";

/**
 * DeepVision Settings — Backend-Persisted Detection Rules & Operator Preferences
 */
export function Settings({ onNavigate, initialSection = "" }) {
  const { user, logout } = useAuth();
  const { t, language, setLanguage, languages } = useTranslation();
  const { addToast } = useToast();

  // 1. Preferences & Default Viewing Mode
  const [defaultMode, setDefaultMode] = useState(() => {
    return localStorage.getItem("deepvision_default_mode") || "tracking";
  });
  const [clockFormat, setClockFormat] = useState(() => {
    return localStorage.getItem("deepvision_clock_format") || "24h";
  });

  // 2. Appearance & Theme
  const [themePref, setThemePref] = useState(() => {
    return localStorage.getItem("deepvision_theme") || "dark";
  });

  // 3. Notification Preferences (Client Audio/Banner + Backend Email Preferences & Delivery Status)
  const [soundAlerts, setSoundAlerts] = useState(() => {
    return localStorage.getItem("deepvision_sound_alerts") !== "false";
  });
  const [bannerAlerts, setBannerAlerts] = useState(() => {
    return localStorage.getItem("deepvision_banner_alerts") !== "false";
  });
  const [emailPrefs, setEmailPrefs] = useState({
    enabled: true,
    notify_critical: true,
    notify_high: true,
    notify_medium: false,
    notify_restricted_entry: true,
    notify_loitering: true,
    notify_unusual_movement: true,
    notify_abandoned_object: true,
  });
  const [deliveryStatus, setDeliveryStatus] = useState(null);
  const [testingEmail, setTestingEmail] = useState(false);

  // 4. Camera & Detection Settings (persisted to SQLite DetectionProfile + live InferenceRegistry)
  const [confThreshold, setConfThreshold] = useState(() => {
    return Number(localStorage.getItem("deepvision_conf_threshold")) || 0.35;
  });
  const [aiProfile, setAiProfile] = useState("lightweight");
  const [activeBackendDetail, setActiveBackendDetail] = useState("YOLO26n ONNX + BoT-SORT Re-ID");
  const [anomalyRules, setAnomalyRules] = useState(() => {
    const saved = localStorage.getItem("deepvision_anomaly_rules");
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch {
        // Fallback below
      }
    }
    return {
      loitering: true,
      restrictedEntry: true,
      crowding: true,
      unusualMovement: true,
      rapidMovement: true,
      abandonedObject: true,
    };
  });
  const [saving, setSaving] = useState(false);

  // 5. Engine Diagnostics
  const [engineHealth, setEngineHealth] = useState({
    status: "checking",
    activeWorkers: 0,
    modelLoaded: true,
    databaseLabel: "PostgreSQL / SQLite (18 Tables Connected)",
  });
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [uptimeData, setUptimeData] = useState(null);
  const [probingUptime, setProbingUptime] = useState(false);
  const [clipConfig, setClipConfig] = useState({
    enabled: false,
    analysis_interval_seconds: 5.0,
    cosine_threshold: 0.24,
    model_name: "openai/clip-vit-base-patch32",
    promptsText: "",
  });
  const [clipStatus, setClipStatus] = useState(null);
  const isStaffUser = ['admin', 'supervisor', 'operator'].includes(String(user?.role || '').toLowerCase()) || Boolean(user?.is_superuser);
  const isAdminUser = String(user?.role || '').toLowerCase() === 'admin' || Boolean(user?.is_superuser);

  useEffect(() => {
    if (initialSection === "account") {
      const el = document.getElementById("settings-account-section");
      if (el && typeof el.scrollIntoView === "function") {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }
  }, [initialSection]);

  useEffect(() => {
    let mounted = true;

    const loadBackendSettings = async () => {
      try {
        const res = await api.settings.getDetection();
        if (!mounted || !res) return;
        if (typeof res.confidence_threshold === "number") {
          setConfThreshold(res.confidence_threshold);
          localStorage.setItem(
            "deepvision_conf_threshold",
            String(res.confidence_threshold),
          );
        }
        if (typeof res.ai_profile === "string" && res.ai_profile) {
          setAiProfile(res.ai_profile);
        }
        if (typeof res.detector_backend === "string" && res.detector_backend && res.detector_backend !== "unknown") {
          setActiveBackendDetail(`${res.detector_backend} (${res.effective_cpus || 1} vCPU) + BoT-SORT Re-ID`);
        }
        if (res.rules && typeof res.rules === "object") {
          const normalized = {
            loitering: res.rules.loitering !== false,
            restrictedEntry:
              (res.rules.restrictedEntry ?? res.rules.restricted_entry) !==
              false,
            crowding: res.rules.crowding !== false,
            unusualMovement: (res.rules.unusualMovement ?? res.rules.unusual_movement) !== false,
            rapidMovement: (res.rules.rapidMovement ?? res.rules.rapid_movement) !== false,
            abandonedObject: (res.rules.abandonedObject ?? res.rules.abandoned_object) !== false,
          };
          setAnomalyRules(normalized);
          localStorage.setItem(
            "deepvision_anomaly_rules",
            JSON.stringify(normalized),
          );
        }
      } catch (err) {
        console.warn("Could not load backend detection settings:", err);
      }
    };

    const loadNotificationSettings = async () => {
      try {
        const [prefRes, dlvRes] = await Promise.allSettled([
          api.notifications.getPreferences(),
          api.notifications.getDeliveryStatus(10),
        ]);
        if (!mounted) return;
        if (prefRes.status === "fulfilled" && prefRes.value?.preferences) {
          setEmailPrefs((prev) => ({ ...prev, ...prefRes.value.preferences }));
        }
        if (dlvRes.status === "fulfilled" && dlvRes.value) {
          setDeliveryStatus(dlvRes.value);
        }
      } catch {
        // non-blocking
      }
    };

    const loadEngineHealth = async () => {
      try {
        const [survRes, sysRes] = await Promise.allSettled([
          api.health.getSurveillance(),
          api.health.get(),
        ]);
        if (!mounted) return;
        const health = survRes.status === "fulfilled" ? survRes.value : null;
        const sysHealth = sysRes.status === "fulfilled" ? sysRes.value : null;
        const dbBackend = String(sysHealth?.database_backend || "").toLowerCase();
        const emailSuffix =
          sysHealth?.email_configuration_complete === true
            ? " · Email: Configured"
            : sysHealth?.email_configuration_complete === false
              ? " · Email: Unconfigured"
              : "";
        const dbLabel =
          (dbBackend === "postgresql"
            ? "PostgreSQL (18 Tables Connected)"
            : "SQLite WAL (18 Tables Connected)") + emailSuffix;
        if (!health) {
          setEngineHealth((prev) => ({
            ...prev,
            status: "offline",
            databaseLabel: dbLabel,
          }));
          return;
        }
        setEngineHealth({
          status:
            health.status === "ok" || health.healthy !== false
              ? "online"
              : "degraded",
          activeWorkers:
            health.active_camera_workers ?? health.camera_workers ?? health.logical_cameras_active ?? 0,
          modelLoaded: health.yolo_loaded !== false,
          databaseLabel: dbLabel,
        });
      } catch {
        if (mounted) {
          setEngineHealth((prev) => ({ ...prev, status: "offline" }));
        }
      }
    };

    const loadClipSettings = async () => {
      try {
        const res = await api.settings.getClip();
        if (!mounted || !res) return;
        if (res.status) setClipStatus(res.status);
        if (res.config) {
          const prompts = Array.isArray(res.config.scene_descriptions)
            ? res.config.scene_descriptions.map((d) => d.prompt).filter(Boolean).join("\n")
            : "";
          setClipConfig({
            enabled: Boolean(res.config.enabled),
            analysis_interval_seconds: Number(res.config.analysis_interval_seconds || 5.0),
            cosine_threshold: Number(res.config.cosine_threshold || 0.24),
            model_name: String(res.config.model_name || "openai/clip-vit-base-patch32"),
            promptsText: prompts,
          });
        }
      } catch {
        // non-blocking
      }
    };

    loadBackendSettings();
    loadNotificationSettings();
    loadEngineHealth();
    loadClipSettings();
    return () => {
      mounted = false;
    };
  }, []);

  const handleSendTestEmail = async () => {
    if (testingEmail) return;
    setTestingEmail(true);
    try {
      const res = await api.notifications.sendTestEmail();
      addToast(res?.message || t("settings.testEmailSent", "Test email dispatched"), res?.success ? "success" : "warning");
      const dlv = await api.notifications.getDeliveryStatus(10);
      if (dlv) setDeliveryStatus(dlv);
    } catch (err) {
      addToast(err?.message || t("settings.testEmailFailed", "Failed to send test email"), "error");
    } finally {
      setTestingEmail(false);
    }
  };

  const handleSaveAll = async () => {
    setSaving(true);
    localStorage.setItem("deepvision_default_mode", defaultMode);
    localStorage.setItem("deepvision_clock_format", clockFormat);
    localStorage.setItem("deepvision_theme", themePref);
    localStorage.setItem("deepvision_sound_alerts", String(soundAlerts));
    localStorage.setItem("deepvision_banner_alerts", String(bannerAlerts));
    localStorage.setItem("deepvision_conf_threshold", String(confThreshold));
    localStorage.setItem(
      "deepvision_anomaly_rules",
      JSON.stringify(anomalyRules),
    );

    // Apply theme immediately
    document.documentElement.setAttribute(
      "data-theme",
      themePref === "system"
        ? window.matchMedia("(prefers-color-scheme: dark)").matches
          ? "dark"
          : "light"
        : themePref,
    );

    try {
      const saveTasks = [
        api.settings.saveDetection({
          confidence_threshold: confThreshold,
          ai_profile: aiProfile,
          rules: anomalyRules,
        }),
        api.notifications.savePreferences(emailPrefs),
      ];
      if (isStaffUser && clipConfig.promptsText !== undefined) {
        const parsedPrompts = clipConfig.promptsText
          .split(/\r?\n/)
          .map((line) => line.trim())
          .filter(Boolean);
        saveTasks.push(
          api.settings.saveClip({
            enabled: clipConfig.enabled,
            analysis_interval_seconds: clipConfig.analysis_interval_seconds,
            cosine_threshold: clipConfig.cosine_threshold,
            model_name: clipConfig.model_name,
            ...(parsedPrompts.length > 0 ? { scene_descriptions: parsedPrompts } : {}),
          }).then((res) => {
            if (res?.status) setClipStatus(res.status);
          })
        );
      }
      await Promise.all(saveTasks);
      addToast(
        t(
          "settings.savedSuccess",
          "Settings saved and applied to active cameras.",
        ),
        "success",
      );
    } catch (err) {
      addToast(
        err?.message || "Preferences saved locally, but engine sync failed.",
        "warning",
      );
    } finally {
      setSaving(false);
    }
  };

  const handleThemeChange = (val) => {
    setThemePref(val);
    document.documentElement.setAttribute(
      "data-theme",
      val === "system"
        ? window.matchMedia("(prefers-color-scheme: dark)").matches
          ? "dark"
          : "light"
        : val,
    );
    localStorage.setItem("deepvision_theme", val);
  };

  const handleLangSelect = (code) => {
    setLanguage(code);
    addToast(
      `${t("settings.languageSection", "Language")}: ${languages.find((l) => l.code === code)?.nativeName}`,
      "info",
    );
  };

  const toggleRule = (ruleKey) => {
    setAnomalyRules((prev) => ({ ...prev, [ruleKey]: !prev[ruleKey] }));
  };

  return (
    <div
      className="deepvision-settings-page"
      style={{
        width: "100%",
        maxWidth: "1200px",
        margin: "0 auto",
        display: "flex",
        flexDirection: "column",
        gap: "18px",
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: "12px",
          padding: "14px 18px",
          background: "var(--bg-surface, #0C121D)",
          border: "1px solid var(--border-color, #1A2436)",
          borderRadius: "var(--radius-lg, 8px)",
        }}
      >
        <div>
          <h1
            style={{
              fontSize: "1.25rem",
              fontWeight: 800,
              margin: 0,
              color: "var(--text-main, #F8FAFC)",
            }}
          >
            {t("settings.title", "Settings & Preferences")}
          </h1>
          <p
            style={{
              margin: "2px 0 0 0",
              fontSize: "0.82rem",
              color: "var(--text-secondary, #64748B)",
            }}
          >
            {t(
              "settings.subtitle",
              "Personal preferences, language, display appearance, and live AI detection thresholds.",
            )}
          </p>
        </div>

        <button
          type="button"
          id="btn-save-settings"
          disabled={saving}
          onClick={handleSaveAll}
          className="btn btn-primary"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "6px",
            padding: "8px 18px",
            fontSize: "0.84rem",
            fontWeight: 700,
          }}
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <polyline points="20 6 9 17 4 12" />
          </svg>
          <span>
            {saving ? t("settings.saving", "Saving...") : t("settings.save", "Save Settings")}
          </span>
        </button>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))",
          gap: "16px",
        }}
      >
        {/* Section 1: Language Selection */}
        <div
          style={{
            padding: "18px",
            background: "var(--bg-surface, #0C121D)",
            border: "1px solid var(--border-color, #1A2436)",
            borderRadius: "var(--radius-lg, 8px)",
            display: "flex",
            flexDirection: "column",
            gap: "12px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={{ color: "var(--dv-cyan-500, #00E5FF)" }}>
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <circle cx="12" cy="12" r="10" />
                <line x1="2" y1="12" x2="22" y2="12" />
                <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
              </svg>
            </span>
            <h2
              style={{
                fontSize: "0.95rem",
                fontWeight: 700,
                margin: 0,
                color: "var(--text-main, #F8FAFC)",
              }}
            >
              {t("settings.languageSection", "Language")}
            </h2>
          </div>
          <p
            style={{
              margin: 0,
              fontSize: "0.8rem",
              color: "var(--text-muted, #64748B)",
            }}
          >
            {t("settings.languageDesc", "Choose the language for the entire surveillance application:")}
          </p>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(3, 1fr)",
              gap: "8px",
            }}
          >
            {languages.map((l) => {
              const isSelected = language === l.code;
              return (
                <button
                  key={l.code}
                  type="button"
                  id={`settings-lang-${l.code}`}
                  onClick={() => handleLangSelect(l.code)}
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    padding: "10px 8px",
                    borderRadius: "6px",
                    border: isSelected
                      ? "1px solid var(--dv-cyan-500, #00E5FF)"
                      : "1px solid var(--border-color, #24324A)",
                    background: isSelected
                      ? "rgba(0, 229, 255, 0.12)"
                      : "var(--bg-canvas, #101826)",
                    color: isSelected
                      ? "var(--dv-cyan-500, #00E5FF)"
                      : "var(--text-main, #F8FAFC)",
                    cursor: "pointer",
                    transition: "all 0.15s ease",
                  }}
                >
                  <span style={{ fontWeight: 700, fontSize: "0.88rem" }}>
                    {l.nativeName}
                  </span>
                  <span
                    style={{
                      fontSize: "0.72rem",
                      color: "var(--text-muted, #64748B)",
                      marginTop: "2px",
                    }}
                  >
                    {l.name}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Section 2: Appearance & Theme */}
        <div
          style={{
            padding: "18px",
            background: "var(--bg-surface, #0C121D)",
            border: "1px solid var(--border-color, #1A2436)",
            borderRadius: "var(--radius-lg, 8px)",
            display: "flex",
            flexDirection: "column",
            gap: "12px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={{ color: "var(--dv-cyan-500, #00E5FF)" }}>
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <circle cx="12" cy="12" r="5" />
                <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
              </svg>
            </span>
            <h2
              style={{
                fontSize: "0.95rem",
                fontWeight: 700,
                margin: 0,
                color: "var(--text-main, #F8FAFC)",
              }}
            >
              {t("settings.appearanceSection", "Appearance")}
            </h2>
          </div>
          <p
            style={{
              margin: 0,
              fontSize: "0.8rem",
              color: "var(--text-muted, #64748B)",
            }}
          >
            {t("settings.appearanceDesc", "Select your preferred display theme for the workstation:")}
          </p>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(3, 1fr)",
              gap: "8px",
            }}
          >
            {[
              { key: "dark", label: t("settings.themeDark", "Dark Theme") },
              { key: "light", label: t("settings.themeLight", "Light Theme") },
              { key: "system", label: t("settings.themeSystem", "System") },
            ].map((theme) => {
              const isSelected = themePref === theme.key;
              return (
                <button
                  key={theme.key}
                  type="button"
                  id={`settings-theme-${theme.key}`}
                  onClick={() => handleThemeChange(theme.key)}
                  style={{
                    padding: "10px 8px",
                    borderRadius: "6px",
                    border: isSelected
                      ? "1px solid var(--dv-cyan-500, #00E5FF)"
                      : "1px solid var(--border-color, #24324A)",
                    background: isSelected
                      ? "rgba(0, 229, 255, 0.12)"
                      : "var(--bg-canvas, #101826)",
                    color: isSelected
                      ? "var(--dv-cyan-500, #00E5FF)"
                      : "var(--text-main, #F8FAFC)",
                    fontWeight: 600,
                    fontSize: "0.82rem",
                    cursor: "pointer",
                    transition: "all 0.15s ease",
                  }}
                >
                  {theme.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Section 3: My Preferences */}
        <div
          style={{
            padding: "18px",
            background: "var(--bg-surface, #0C121D)",
            border: "1px solid var(--border-color, #1A2436)",
            borderRadius: "var(--radius-lg, 8px)",
            display: "flex",
            flexDirection: "column",
            gap: "14px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={{ color: "var(--dv-cyan-500, #00E5FF)" }}>
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9" />
              </svg>
            </span>
            <h2
              style={{
                fontSize: "0.95rem",
                fontWeight: 700,
                margin: 0,
                color: "var(--text-main, #F8FAFC)",
              }}
            >
              {t("settings.myPreferences", "My Preferences")}
            </h2>
          </div>

          <div
            style={{ display: "flex", flexDirection: "column", gap: "12px" }}
          >
            <div>
              <label
                style={{
                  display: "block",
                  fontSize: "0.82rem",
                  fontWeight: 600,
                  color: "var(--text-main, #F8FAFC)",
                  marginBottom: "6px",
                }}
              >
                {t("settings.defaultModeLabel", "Default Camera View Mode")}
              </label>
              <select
                id="select-default-mode"
                value={defaultMode}
                onChange={(e) => setDefaultMode(e.target.value)}
                style={{
                  width: "100%",
                  padding: "7px 10px",
                  borderRadius: "4px",
                  background: "var(--bg-canvas, #101826)",
                  border: "1px solid var(--border-color, #24324A)",
                  color: "var(--text-main, #F8FAFC)",
                  fontSize: "0.82rem",
                }}
              >
                <option value="tracking">
                  {t("settings.modeDetectionTracking", "Detection & Tracking")}
                </option>
                <option value="raw">
                  {t("settings.modeRawStream", "Raw Stream")}
                </option>
              </select>
            </div>

            <div>
              <label
                style={{
                  display: "block",
                  fontSize: "0.82rem",
                  fontWeight: 600,
                  color: "var(--text-main, #F8FAFC)",
                  marginBottom: "6px",
                }}
              >
                {t("settings.clockFormatLabel", "Live Digital Clock Format")}
              </label>
              <select
                id="select-clock-format"
                value={clockFormat}
                onChange={(e) => setClockFormat(e.target.value)}
                style={{
                  width: "100%",
                  padding: "7px 10px",
                  borderRadius: "4px",
                  background: "var(--bg-canvas, #101826)",
                  border: "1px solid var(--border-color, #24324A)",
                  color: "var(--text-main, #F8FAFC)",
                  fontSize: "0.82rem",
                }}
              >
                <option value="24h">{t("settings.format24h", "24-Hour (14:30:00)")}</option>
                <option value="12h">{t("settings.format12h", "12-Hour (02:30:00 PM)")}</option>
              </select>
            </div>
          </div>
        </div>

        {/* Section 4: Notifications */}
        <div
          style={{
            padding: "18px",
            background: "var(--bg-surface, #0C121D)",
            border: "1px solid var(--border-color, #1A2436)",
            borderRadius: "var(--radius-lg, 8px)",
            display: "flex",
            flexDirection: "column",
            gap: "12px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={{ color: "var(--dv-cyan-500, #00E5FF)" }}>
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
                <path d="M13.73 21a2 2 0 0 1-3.46 0" />
              </svg>
            </span>
            <h2
              style={{
                fontSize: "0.95rem",
                fontWeight: 700,
                margin: 0,
                color: "var(--text-main, #F8FAFC)",
              }}
            >
              {t("settings.notificationsSection", "Notifications")}
            </h2>
          </div>

          <div
            style={{ display: "flex", flexDirection: "column", gap: "10px" }}
          >
            <label
              style={{
                display: "flex",
                alignItems: "center",
                gap: "10px",
                cursor: "pointer",
                fontSize: "0.82rem",
                color: "var(--text-main, #F8FAFC)",
              }}
            >
              <input
                type="checkbox"
                checked={soundAlerts}
                onChange={(e) => setSoundAlerts(e.target.checked)}
                style={{
                  width: "16px",
                  height: "16px",
                  accentColor: "var(--dv-cyan-500, #00E5FF)",
                }}
              />
              <span>
                {t(
                  "settings.soundAlerts",
                  "Audio alert on high-severity events",
                )}
              </span>
            </label>

            <label
              style={{
                display: "flex",
                alignItems: "center",
                gap: "10px",
                cursor: "pointer",
                fontSize: "0.82rem",
                color: "var(--text-main, #F8FAFC)",
              }}
            >
              <input
                type="checkbox"
                checked={bannerAlerts}
                onChange={(e) => setBannerAlerts(e.target.checked)}
                style={{
                  width: "16px",
                  height: "16px",
                  accentColor: "var(--dv-cyan-500, #00E5FF)",
                }}
              />
              <span>
                {t(
                  "settings.bannerAlerts",
                  "Show floating notification banner",
                )}
              </span>
            </label>

            <div style={{ borderTop: "1px solid var(--border-color, #1A2436)", paddingTop: "10px", marginTop: "4px", display: "flex", flexDirection: "column", gap: "8px" }}>
              <label style={{ display: "flex", alignItems: "center", gap: "10px", cursor: "pointer", fontSize: "0.82rem", fontWeight: 700, color: "var(--text-main, #F8FAFC)" }}>
                <input
                  type="checkbox"
                  checked={Boolean(emailPrefs.enabled)}
                  onChange={(e) => setEmailPrefs((p) => ({ ...p, enabled: e.target.checked }))}
                  data-testid="email-alerts-enabled"
                  style={{ width: "16px", height: "16px", accentColor: "var(--dv-cyan-500, #00E5FF)" }}
                />
                <span>{t("settings.emailAlertsEnabled", "Enable email notifications for security alerts")}</span>
              </label>

              {emailPrefs.enabled && (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: "6px", paddingLeft: "6px", fontSize: "0.78rem", color: "var(--text-secondary, #94A3B8)" }}>
                  {[
                    { k: "notify_critical", lbl: t("settings.notifyCritical", "Critical severity") },
                    { k: "notify_high", lbl: t("settings.notifyHigh", "High severity") },
                    { k: "notify_medium", lbl: t("settings.notifyMedium", "Medium severity") },
                    { k: "notify_restricted_entry", lbl: t("settings.notifyRestricted", "Restricted-zone entry") },
                    { k: "notify_loitering", lbl: t("settings.notifyLoitering", "Loitering alerts") },
                    { k: "notify_unusual_movement", lbl: t("settings.notifyMovement", "Rapid/unusual motion") },
                    { k: "notify_abandoned_object", lbl: t("settings.notifyAbandoned", "Abandoned object") },
                  ].map((item) => (
                    <label key={item.k} style={{ display: "flex", alignItems: "center", gap: "6px", cursor: "pointer" }}>
                      <input
                        type="checkbox"
                        checked={Boolean(emailPrefs[item.k])}
                        onChange={(e) => setEmailPrefs((p) => ({ ...p, [item.k]: e.target.checked }))}
                        style={{ accentColor: "var(--dv-cyan-500, #00E5FF)" }}
                      />
                      <span>{item.lbl}</span>
                    </label>
                  ))}
                </div>
              )}

              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "8px", paddingTop: "6px" }}>
                <span style={{ fontSize: "0.75rem", color: "var(--text-muted, #94A3B8)" }}>
                  {deliveryStatus
                    ? `SMTP: ${deliveryStatus.smtp_configured ? "Configured" : "Not configured"} · Sent: ${deliveryStatus.summary?.sent ?? 0} · Failed: ${deliveryStatus.summary?.failed ?? 0}`
                    : "Email delivery status loading..."}
                </span>
                <button
                  type="button"
                  onClick={handleSendTestEmail}
                  disabled={testingEmail}
                  className="btn btn-secondary btn-sm"
                  data-testid="send-test-email-btn"
                >
                  {testingEmail ? t("settings.sendingTestEmail", "Sending...") : t("settings.sendTestEmail", "Send Test Email")}
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Section 5: Camera & Detection Settings */}
        <div
          style={{
            padding: "18px",
            background: "var(--bg-surface, #0C121D)",
            border: "1px solid var(--border-color, #1A2436)",
            borderRadius: "var(--radius-lg, 8px)",
            display: "flex",
            flexDirection: "column",
            gap: "14px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={{ color: "var(--dv-cyan-500, #00E5FF)" }}>
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
                <circle cx="12" cy="13" r="4" />
              </svg>
            </span>
            <h2
              style={{
                fontSize: "0.95rem",
                fontWeight: 700,
                margin: 0,
                color: "var(--text-main, #F8FAFC)",
              }}
            >
              {t("settings.cameraSection", "Camera & AI Detection Settings")}
            </h2>
          </div>

          <div>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                marginBottom: "6px",
              }}
            >
              <label
                htmlFor="range-conf-threshold"
                style={{
                  fontSize: "0.82rem",
                  fontWeight: 600,
                  color: "var(--text-main, #F8FAFC)",
                }}
              >
                {t(
                  "settings.detectionSensitivity",
                  "Detection Confidence Threshold",
                )}
              </label>
              <span
                id="conf-threshold-display"
                style={{
                  fontFamily: "var(--font-mono, monospace)",
                  color: "var(--dv-cyan-500, #00E5FF)",
                  fontWeight: 700,
                  fontSize: "0.82rem",
                }}
              >
                {Math.round(confThreshold * 100)}%
              </span>
            </div>
            <input
              id="range-conf-threshold"
              type="range"
              min="0.20"
              max="0.85"
              step="0.05"
              value={confThreshold}
              onChange={(e) => setConfThreshold(parseFloat(e.target.value))}
              style={{
                width: "100%",
                accentColor: "var(--dv-cyan-500, #00E5FF)",
              }}
            />
          </div>

          <div>
            <label
              htmlFor="select-ai-profile"
              style={{
                display: "block",
                fontSize: "0.82rem",
                fontWeight: 600,
                color: "var(--text-main, #F8FAFC)",
                marginBottom: "6px",
              }}
            >
              {t("settings.aiProfileLabel", "AI Inference Model Profile")}
            </label>
            <select
              id="select-ai-profile"
              value={aiProfile}
              onChange={(e) => setAiProfile(e.target.value)}
              style={{
                width: "100%",
                padding: "7px 10px",
                borderRadius: "4px",
                background: "var(--bg-canvas, #101826)",
                border: "1px solid var(--border-color, #24324A)",
                color: "var(--text-main, #F8FAFC)",
                fontSize: "0.82rem",
              }}
            >
              <option value="lightweight">YOLO26n — Real-Time 30 FPS / Fast CPU (Default)</option>
              <option value="balanced">YOLO26s — High Accuracy (Explicit)</option>
            </select>
            <div style={{ fontSize: "0.73rem", color: "var(--text-muted, #64748B)", marginTop: "4px" }}>
              {aiProfile === "lightweight"
                ? "Prioritizes real-time ~30 FPS live inference on Intel Iris Xe iGPU and ~3.3x faster CPU throughput."
                : "Higher detection recall on small or distant subjects (~18 FPS on iGPU; heavier on CPU-only cloud hosts)."}
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            <span
              style={{
                fontSize: "0.78rem",
                color: "var(--text-muted, #64748B)",
                fontWeight: 600,
              }}
            >
              {t("settings.anomalyRulesLabel", "Active Behavior & Perimeter Rules:")}
            </span>
            {[
              { key: 'restrictedEntry', label: t('settings.ruleRestricted', 'Perimeter / Restricted Zone Intrusion') },
              { key: 'loitering', label: t('settings.ruleLoitering', 'Loitering & Extended Linger Time') },
              { key: 'crowding', label: t('settings.ruleCrowding', 'Congestion & Crowd Density') },
              { key: 'unusualMovement', label: t('settings.ruleUnusual', 'Unusual / Erratic Movement') },
              { key: 'rapidMovement', label: t('settings.ruleRapid', 'Rapid Movement / High-Velocity Dash') },
              { key: 'abandonedObject', label: t('settings.ruleAbandoned', 'Unattended / Abandoned Object') },
            ].map((rule) => (
              <label
                key={rule.key}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  cursor: "pointer",
                  fontSize: "0.8rem",
                  color: "var(--text-secondary, #94A3B8)",
                }}
              >
                <input
                  id={`rule-checkbox-${rule.key}`}
                  type="checkbox"
                  checked={Boolean(anomalyRules[rule.key])}
                  onChange={() => toggleRule(rule.key)}
                  style={{ accentColor: "var(--dv-cyan-500, #00E5FF)" }}
                />
                <span>{rule.label}</span>
              </label>
            ))}
          </div>

          {/* Configurable CLIP Scene Understanding Controls */}
          <div style={{ borderTop: "1px solid var(--border-color, #1A2436)", paddingTop: "12px", display: "flex", flexDirection: "column", gap: "8px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
              <span style={{ fontSize: "0.82rem", fontWeight: 700, color: "var(--text-main, #F8FAFC)" }}>
                CLIP Scene Understanding ({clipConfig.model_name})
              </span>
              <span style={{ fontSize: "0.7rem", fontFamily: "var(--font-mono)", color: clipStatus?.available ? "#10B981" : "var(--text-muted, #94A3B8)" }}>
                {clipStatus ? `${String(clipStatus.status || "standby").replace(/_/g, " ")} · ${clipStatus.device || "cpu"}` : "checking"}
              </span>
            </div>
            <label style={{ display: "flex", alignItems: "center", gap: "8px", cursor: isStaffUser ? "pointer" : "not-allowed", fontSize: "0.8rem", color: "var(--text-secondary, #94A3B8)" }}>
              <input
                id="toggle-clip-enabled"
                type="checkbox"
                disabled={!isStaffUser}
                checked={Boolean(clipConfig.enabled)}
                onChange={(e) => setClipConfig((c) => ({ ...c, enabled: e.target.checked }))}
                style={{ accentColor: "var(--dv-cyan-500, #00E5FF)" }}
              />
              <span>Enable background CLIP scene understanding</span>
            </label>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
              <div>
                <label style={{ display: "block", fontSize: "0.72rem", color: "var(--text-muted, #94A3B8)", marginBottom: "2px" }}>
                  Interval (sec): {clipConfig.analysis_interval_seconds}s
                </label>
                <input
                  type="range"
                  min="2"
                  max="30"
                  step="1"
                  disabled={!isStaffUser}
                  value={clipConfig.analysis_interval_seconds}
                  onChange={(e) => setClipConfig((c) => ({ ...c, analysis_interval_seconds: parseFloat(e.target.value) }))}
                  style={{ width: "100%", accentColor: "var(--dv-cyan-500, #00E5FF)" }}
                />
              </div>
              <div>
                <label style={{ display: "block", fontSize: "0.72rem", color: "var(--text-muted, #94A3B8)", marginBottom: "2px" }}>
                  Cosine Threshold: {clipConfig.cosine_threshold}
                </label>
                <input
                  type="range"
                  min="0.15"
                  max="0.45"
                  step="0.01"
                  disabled={!isStaffUser}
                  value={clipConfig.cosine_threshold}
                  onChange={(e) => setClipConfig((c) => ({ ...c, cosine_threshold: parseFloat(e.target.value) }))}
                  style={{ width: "100%", accentColor: "var(--dv-cyan-500, #00E5FF)" }}
                />
              </div>
            </div>
            <div>
              <label style={{ display: "block", fontSize: "0.72rem", color: "var(--text-muted, #94A3B8)", marginBottom: "4px" }}>
                Scene Descriptions (one candidate prompt per line)
              </label>
              <textarea
                rows={4}
                disabled={!isStaffUser}
                value={clipConfig.promptsText}
                onChange={(e) => setClipConfig((c) => ({ ...c, promptsText: e.target.value }))}
                style={{
                  width: "100%",
                  padding: "6px 8px",
                  borderRadius: "4px",
                  background: "var(--bg-canvas, #101826)",
                  border: "1px solid var(--border-color, #24324A)",
                  color: "var(--text-main, #F8FAFC)",
                  fontSize: "0.75rem",
                  resize: "vertical",
                }}
              />
            </div>
          </div>
        </div>

        {/* Section 6: Account & Security */}
        <div
          id="settings-account-section"
          style={{
            padding: "18px",
            background: "var(--bg-surface, #0C121D)",
            border: "1px solid var(--border-color, #1A2436)",
            borderRadius: "var(--radius-lg, 8px)",
            display: "flex",
            flexDirection: "column",
            gap: "12px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={{ color: "var(--dv-cyan-500, #00E5FF)" }}>
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                <circle cx="12" cy="7" r="4" />
              </svg>
            </span>
            <h2
              style={{
                fontSize: "0.95rem",
                fontWeight: 700,
                margin: 0,
                color: "var(--text-main, #F8FAFC)",
              }}
            >
              {t("settings.securitySection", "Account & Security")}
            </h2>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '0.82rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-muted, #64748B)' }}>{t('settings.operatorLabel', 'Operator:')}</span>
              <span style={{ color: 'var(--text-main, #F8FAFC)', fontWeight: 600 }}>{user?.full_name || user?.username || t('app.operator', 'Security Operator')}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: "var(--text-muted, #64748B)" }}>
                {t('settings.emailLabel', 'Email:')}
              </span>
              <span style={{ color: "var(--text-main, #F8FAFC)" }}>
                {user?.email || t('settings.authSession', 'Authenticated Session')}
              </span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: "var(--text-muted, #64748B)" }}>
                {t('settings.authLabel', 'Authentication:')}
              </span>
              <span
                className="status-pill status-live"
                style={{ fontSize: "0.7rem", padding: "1px 8px" }}
              >
                {t('settings.otpVerified', 'OTP Verified')}
              </span>
            </div>
          </div>

          <button
            type="button"
            onClick={logout}
            className="btn btn-secondary btn-sm"
            style={{
              marginTop: "8px",
              color: "var(--color-critical, #FF3D71)",
              borderColor: "rgba(255, 61, 113, 0.3)",
            }}
          >
            {t("nav.logout", "Sign Out")}
          </button>
        </div>
      </div>

      {/* Section 6.5: Admin/Staff-Only Website Uptime Monitor */}
      {isStaffUser && (
        <div
          id="admin-uptime-monitor-card"
          style={{
            marginBottom: "18px",
            padding: "18px",
            background: "var(--bg-surface, #0C121D)",
            border: "1px solid var(--border-color, #1A2436)",
            borderRadius: "var(--radius-lg, 8px)",
            display: "flex",
            flexDirection: "column",
            gap: "12px",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
            <div>
              <h2 style={{ fontSize: "0.95rem", fontWeight: 700, margin: 0, color: "var(--text-main, #F8FAFC)" }}>
                Website Uptime &amp; Availability Monitor (External HTTPS Probes)
              </h2>
              <div style={{ fontSize: "0.74rem", color: "var(--text-muted, #64748B)", marginTop: "3px" }}>
                Scheduled every 15 min via GitHub Actions against allowlisted production URLs (SSRF-guarded, transition-only).
              </div>
            </div>
            <div style={{ display: "flex", gap: "8px" }}>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={async () => {
                  try {
                    const res = await api.uptime.getStatus();
                    if (res?.success) setUptimeData(res);
                  } catch {}
                }}
              >
                Refresh Status
              </button>
              {isAdminUser && (
                <button
                  type="button"
                  disabled={probingUptime}
                  data-testid="run-uptime-probe-btn"
                  className="btn btn-primary btn-sm"
                  onClick={async () => {
                    try {
                      setProbingUptime(true);
                      const res = await api.uptime.checkNow();
                      if (res?.success) {
                        setUptimeData(res);
                        addToast("Live HTTPS uptime check completed.", "success");
                      }
                    } catch (err) {
                      addToast(err?.message || "Uptime probe failed.", "error");
                    } finally {
                      setProbingUptime(false);
                    }
                  }}
                >
                  {probingUptime ? "Probing..." : "Run Live Check"}
                </button>
              )}
            </div>
          </div>

          {!uptimeData && (
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              style={{ alignSelf: "flex-start" }}
              onClick={async () => {
                try {
                  const res = await api.uptime.getStatus();
                  if (res?.success) setUptimeData(res);
                } catch {}
              }}
            >
              Load Uptime Telemetry
            </button>
          )}

          {uptimeData?.targets && (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "10px" }}>
              {uptimeData.targets.map((tgt) => {
                const st = String(tgt.current_status || "unknown").toLowerCase();
                const stClass = st === "up" ? "status-live" : st === "down" ? "status-offline" : "status-warn";
                return (
                  <div
                    key={tgt.target_id}
                    style={{
                      padding: "10px 12px",
                      background: "var(--bg-canvas, #101826)",
                      border: "1px solid var(--border-color, #1A2436)",
                      borderRadius: "6px",
                      fontSize: "0.78rem",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "6px", marginBottom: "6px" }}>
                      <strong style={{ color: "var(--text-main, #F8FAFC)" }}>{tgt.name}</strong>
                      <span className={`status-pill ${stClass}`} style={{ fontSize: "0.66rem", textTransform: "uppercase" }}>
                        {st.replace(/_/g, " ")}
                      </span>
                    </div>
                    <div style={{ color: "var(--text-muted, #94A3B8)", display: "flex", flexDirection: "column", gap: "2px" }}>
                      <span>Latency: <strong style={{ color: "var(--text-main)" }}>{tgt.last_latency_ms != null ? `${tgt.last_latency_ms} ms` : "—"}</strong> · Failures: <strong>{tgt.consecutive_failures ?? 0}</strong></span>
                      <span>Availability: <strong>{tgt.availability_pct != null ? `${tgt.availability_pct}% (${tgt.total_checks})` : "Awaiting probe"}</strong></span>
                      <span>Outage dur: <strong>{tgt.current_outage_duration_seconds > 0 ? `${tgt.current_outage_duration_seconds}s active` : (tgt.last_outage_duration_seconds != null ? `${tgt.last_outage_duration_seconds}s last` : "0s")}</strong></span>
                      {tgt.last_checked_at && <span>Checked: {new Date(tgt.last_checked_at).toLocaleString()}</span>}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {uptimeData?.tier_disclosure && (
            <div style={{ fontSize: "0.73rem", color: "var(--text-muted, #64748B)", lineHeight: 1.45 }}>
              {uptimeData.tier_disclosure}
            </div>
          )}
        </div>
      )}

      {/* Section 7: Advanced Diagnostics (Collapsible) */}
      <div
        style={{
          background: "var(--bg-surface, #0C121D)",
          border: "1px solid var(--border-color, #1A2436)",
          borderRadius: "var(--radius-lg, 8px)",
          overflow: "hidden",
        }}
      >
        <button
          type="button"
          id="btn-toggle-diagnostics"
          onClick={() => setShowAdvanced(!showAdvanced)}
          style={{
            width: "100%",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "12px 18px",
            background: "transparent",
            border: "none",
            color: "var(--text-secondary, #94A3B8)",
            cursor: "pointer",
            fontSize: "0.84rem",
            fontWeight: 600,
          }}
        >
          <span>{t("settings.advancedSection", "Advanced Diagnostics")}</span>
          <span>{showAdvanced ? "▲" : "▼"}</span>
        </button>

        {showAdvanced && (
          <div
            style={{
              padding: "0 18px 18px 18px",
              borderTop: "1px solid var(--border-color, #1A2436)",
            }}
          >
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
                gap: "12px",
                marginTop: "12px",
                fontSize: "0.8rem",
              }}
            >
              <div
                style={{
                  padding: "10px",
                  background: "var(--bg-canvas, #101826)",
                  borderRadius: "4px",
                }}
              >
                <div
                  style={{
                    color: "var(--text-muted, #64748B)",
                    marginBottom: "4px",
                  }}
                >
                  {t('settings.engineStatusLabel', 'Surveillance Capture Engine')}
                </div>
                <div
                  style={{
                    color:
                      engineHealth.status === "online"
                        ? "var(--color-live, #00E676)"
                        : "var(--color-warn, #F59E0B)",
                    fontWeight: 600,
                  }}
                >
                  Native Django OpenCV / DirectShow (
                  {engineHealth.status.toUpperCase()})
                </div>
              </div>
              <div
                style={{
                  padding: "10px",
                  background: "var(--bg-canvas, #101826)",
                  borderRadius: "4px",
                }}
              >
                <div
                  style={{
                    color: "var(--text-muted, #64748B)",
                    marginBottom: "4px",
                  }}
                >
                  {t('settings.yoloModelLabel', 'Inference & Tracking Pipeline')}
                </div>
                <div
                  style={{
                    color: "var(--text-main, #F8FAFC)",
                    fontWeight: 600,
                  }}
                >
                  {activeBackendDetail} (
                  {engineHealth.modelLoaded ? "Ready" : "Standby"})
                </div>
              </div>
              <div
                style={{
                  padding: "10px",
                  background: "var(--bg-canvas, #101826)",
                  borderRadius: "4px",
                }}
              >
                <div
                  style={{
                    color: "var(--text-muted, #64748B)",
                    marginBottom: "4px",
                  }}
                >
                  {t('settings.databaseStatus', 'Database Pipeline')}
                </div>
                <div
                  style={{
                    color: "var(--color-live, #00E676)",
                    fontWeight: 600,
                  }}
                >
                  {engineHealth.databaseLabel}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default Settings;
