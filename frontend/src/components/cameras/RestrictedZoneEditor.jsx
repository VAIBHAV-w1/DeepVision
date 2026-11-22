import React, { useState, useRef, useEffect } from 'react';
import { useTranslation } from '../../i18n/i18nContext';

/**
 * Resolution-independent Restricted-Zone Visual Editor (Normalized 0..1 Coordinates).
 * Supports polygon vertex drawing, rectangle drag drawing, vertex handle dragging,
 * self-intersection & degenerate geometry validation, and real-time preview.
 */
function segmentsIntersect(a1, a2, b1, b2) {
  const ccw = (p1, p2, p3) => (p3.y - p1.y) * (p2.x - p1.x) - (p2.y - p1.y) * (p3.x - p1.x);
  const d1 = ccw(b1, b2, a1);
  const d2 = ccw(b1, b2, a2);
  const d3 = ccw(a1, a2, b1);
  const d4 = ccw(a1, a2, b2);
  return ((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) && ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0));
}

export function validatePolygonNormalized(points) {
  if (!Array.isArray(points) || points.length < 3) {
    return { valid: false, error: 'Polygon zone requires at least 3 vertices.' };
  }
  for (const pt of points) {
    if (typeof pt?.x !== 'number' || typeof pt?.y !== 'number' || Number.isNaN(pt.x) || Number.isNaN(pt.y)) {
      return { valid: false, error: 'Invalid polygon coordinates.' };
    }
    if (pt.x < 0 || pt.x > 1 || pt.y < 0 || pt.y > 1) {
      return { valid: false, error: 'Polygon vertices must remain inside the camera frame.' };
    }
  }
  if (points.length >= 4) {
    for (let i = 0; i < points.length; i++) {
      const a1 = points[i];
      const a2 = points[(i + 1) % points.length];
      for (let j = i + 2; j < points.length; j++) {
        if (i === 0 && j === points.length - 1) continue;
        const b1 = points[j];
        const b2 = points[(j + 1) % points.length];
        if (segmentsIntersect(a1, a2, b1, b2)) {
          return { valid: false, error: 'Polygon edges cannot cross each other (self-intersecting).' };
        }
      }
    }
  }
  let area2 = 0;
  for (let i = 0; i < points.length; i++) {
    const j = (i + 1) % points.length;
    area2 += points[i].x * points[j].y - points[j].x * points[i].y;
  }
  if (Math.abs(area2) * 0.5 < 0.0005) {
    return { valid: false, error: 'Drawn zone area is too small. Draw a larger region.' };
  }
  return { valid: true, error: null };
}

export function normalizeZonePoints(zone) {
  if (Array.isArray(zone?.points) && zone.points.length >= 3) {
    return zone.points.map((p) => ({
      x: Math.max(0, Math.min(1, Number(p.x) || 0)),
      y: Math.max(0, Math.min(1, Number(p.y) || 0)),
    }));
  }
  const x1 = Number(zone?.x1 ?? 320);
  const y1 = Number(zone?.y1 ?? 144);
  const x2 = Number(zone?.x2 ?? 960);
  const y2 = Number(zone?.y2 ?? 612);
  const isNorm = Math.max(x1, y1, x2, y2) <= 1.0 && Math.min(x1, y1, x2, y2) >= 0.0;
  const nx1 = isNorm ? x1 : Math.max(0, Math.min(1, x1 / 1280));
  const ny1 = isNorm ? y1 : Math.max(0, Math.min(1, y1 / 720));
  const nx2 = isNorm ? x2 : Math.max(0, Math.min(1, x2 / 1280));
  const ny2 = isNorm ? y2 : Math.max(0, Math.min(1, y2 / 720));
  return [
    { x: Math.min(nx1, nx2), y: Math.min(ny1, ny2) },
    { x: Math.max(nx1, nx2), y: Math.min(ny1, ny2) },
    { x: Math.max(nx1, nx2), y: Math.max(ny1, ny2) },
    { x: Math.min(nx1, nx2), y: Math.max(ny1, ny2) },
  ];
}

export function RestrictedZoneEditor({
  active,
  zones = [],
  activeIntrusions = [],
  editingZone,
  drawTool = 'polygon',
  draftPoints = [],
  setDraftPoints,
  onEditZoneVertices,
  showZones = true,
}) {
  const { t } = useTranslation();
  const svgRef = useRef(null);
  const [dragState, setDragState] = useState(null); // { mode: 'rect' | 'vertex', vertexIdx?: number, start?: {x,y} }

  const toNormalized = (clientX, clientY) => {
    const el = svgRef.current;
    if (!el) return { x: 0, y: 0 };
    const rect = el.getBoundingClientRect();
    const x = Math.max(0, Math.min(1, (clientX - rect.left) / Math.max(1, rect.width)));
    const y = Math.max(0, Math.min(1, (clientY - rect.top) / Math.max(1, rect.height)));
    return { x: Number(x.toFixed(4)), y: Number(y.toFixed(4)) };
  };

  useEffect(() => {
    if (!dragState) return undefined;
    const handleMove = (ev) => {
      const pt = toNormalized(ev.clientX, ev.clientY);
      if (dragState.mode === 'rect' && dragState.start) {
        const x1 = Math.min(dragState.start.x, pt.x);
        const y1 = Math.min(dragState.start.y, pt.y);
        const x2 = Math.max(dragState.start.x, pt.x);
        const y2 = Math.max(dragState.start.y, pt.y);
        setDraftPoints([
          { x: x1, y: y1 },
          { x: x2, y: y1 },
          { x: x2, y: y2 },
          { x: x1, y: y2 },
        ]);
      } else if (dragState.mode === 'vertex' && typeof dragState.vertexIdx === 'number') {
        if (editingZone) {
          const updated = normalizeZonePoints(editingZone).map((p, idx) =>
            idx === dragState.vertexIdx ? pt : p
          );
          onEditZoneVertices?.(editingZone.id, updated);
        } else {
          setDraftPoints((prev) => prev.map((p, idx) => (idx === dragState.vertexIdx ? pt : p)));
        }
      }
    };
    const handleUp = () => setDragState(null);
    window.addEventListener('pointermove', handleMove);
    window.addEventListener('pointerup', handleUp);
    return () => {
      window.removeEventListener('pointermove', handleMove);
      window.removeEventListener('pointerup', handleUp);
    };
  }, [dragState, editingZone, onEditZoneVertices, setDraftPoints]);

  if (!showZones && !active) return null;

  const handleCanvasPointerDown = (e) => {
    if (!active || e.button !== 0) return;
    if (e.target?.dataset?.vertexHandle === 'true') return;
    const pt = toNormalized(e.clientX, e.clientY);

    if (editingZone) return; // Dragging handles edits the selected existing zone

    if (drawTool === 'rectangle') {
      setDraftPoints([pt, pt, pt, pt]);
      setDragState({ mode: 'rect', start: pt });
    } else {
      setDraftPoints((prev) => [...prev, pt]);
    }
  };

  const editingPts = editingZone ? normalizeZonePoints(editingZone) : [];

  return (
    <svg
      ref={svgRef}
      viewBox="0 0 1000 1000"
      preserveAspectRatio="none"
      onPointerDown={handleCanvasPointerDown}
      data-testid="restricted-zone-svg"
      style={{
        position: 'absolute',
        inset: 0,
        width: '100%',
        height: '100%',
        pointerEvents: active ? 'auto' : 'none',
        cursor: active ? (editingZone ? 'default' : 'crosshair') : 'default',
        zIndex: 6,
      }}
    >
      {/* Existing persisted zones */}
      {zones.map((z) => {
        const pts = normalizeZonePoints(z);
        const isEditingThis = editingZone && editingZone.id === z.id;
        if (isEditingThis) return null;
        const isIntruded = activeIntrusions.includes(z.id);
        const stroke = !z.enabled
          ? 'rgba(148, 163, 184, 0.5)'
          : isIntruded
          ? '#ef4444'
          : z.color || '#f59e0b';
        const fill = !z.enabled
          ? 'rgba(148, 163, 184, 0.08)'
          : isIntruded
          ? 'rgba(239, 68, 68, 0.24)'
          : 'rgba(245, 158, 11, 0.14)';
        const polyAttr = pts.map((p) => `${(p.x * 1000).toFixed(1)},${(p.y * 1000).toFixed(1)}`).join(' ');
        const minX = Math.min(...pts.map((p) => p.x * 1000));
        const minY = Math.min(...pts.map((p) => p.y * 1000));
        return (
          <g key={z.id}>
            <polygon
              points={polyAttr}
              fill={fill}
              stroke={stroke}
              strokeWidth={isIntruded ? 4 : 2.5}
              strokeDasharray={z.enabled ? undefined : '8 6'}
            />
            <text
              x={Math.max(8, minX + 10)}
              y={Math.max(24, minY + 24)}
              fill={stroke}
              fontSize="20"
              fontWeight="700"
              style={{ paintOrder: 'stroke', stroke: 'rgba(15,23,42,0.85)', strokeWidth: '4px' }}
            >
              {isIntruded ? `! ${z.name}` : z.name}
            </text>
          </g>
        );
      })}

      {/* Currently editing existing zone vertices */}
      {editingZone && editingPts.length >= 3 && (
        <g>
          <polygon
            points={editingPts.map((p) => `${(p.x * 1000).toFixed(1)},${(p.y * 1000).toFixed(1)}`).join(' ')}
            fill="rgba(0, 229, 255, 0.18)"
            stroke="#00E5FF"
            strokeWidth={3}
          />
          {editingPts.map((p, idx) => (
            <circle
              key={idx}
              cx={p.x * 1000}
              cy={p.y * 1000}
              r={10}
              fill="#00E5FF"
              stroke="#0F172A"
              strokeWidth={2.5}
              data-vertex-handle="true"
              style={{ cursor: 'grab' }}
              onPointerDown={(ev) => {
                ev.stopPropagation();
                setDragState({ mode: 'vertex', vertexIdx: idx });
              }}
            />
          ))}
        </g>
      )}

      {/* New Draft Zone (Polygon / Rectangle) */}
      {active && !editingZone && draftPoints.length > 0 && (
        <g>
          {draftPoints.length >= 3 ? (
            <polygon
              points={draftPoints.map((p) => `${(p.x * 1000).toFixed(1)},${(p.y * 1000).toFixed(1)}`).join(' ')}
              fill="rgba(0, 229, 255, 0.2)"
              stroke="#00E5FF"
              strokeWidth={3}
              strokeDasharray="6 4"
            />
          ) : (
            <polyline
              points={draftPoints.map((p) => `${(p.x * 1000).toFixed(1)},${(p.y * 1000).toFixed(1)}`).join(' ')}
              fill="none"
              stroke="#00E5FF"
              strokeWidth={3}
            />
          )}
          {draftPoints.map((p, idx) => (
            <circle
              key={idx}
              cx={p.x * 1000}
              cy={p.y * 1000}
              r={9}
              fill="#FFFFFF"
              stroke="#00E5FF"
              strokeWidth={3}
              data-vertex-handle="true"
              style={{ cursor: 'grab' }}
              onPointerDown={(ev) => {
                ev.stopPropagation();
                setDragState({ mode: 'vertex', vertexIdx: idx });
              }}
            />
          ))}
        </g>
      )}

      {active && !editingZone && draftPoints.length === 0 && (
        <text
          x="500"
          y="44"
          textAnchor="middle"
          fill="#00E5FF"
          fontSize="20"
          fontWeight="700"
          style={{ paintOrder: 'stroke', stroke: 'rgba(15,23,42,0.9)', strokeWidth: '5px' }}
        >
          {drawTool === 'rectangle'
            ? t('zoneEditor.dragRectangleHint', 'Click and drag on video to draw a restricted rectangle zone')
            : t('zoneEditor.clickPolygonHint', 'Click on video points to draw polygon boundary vertices (min 3 points)')}
        </text>
      )}
    </svg>
  );
}

export default RestrictedZoneEditor;
