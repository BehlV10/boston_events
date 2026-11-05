"""Light theme (☀️ in the theme picker).

The palette tokens live with the other themes in template.py. This file holds the overrides for
rules that hard-code colors meant for a dark page (white text, white-tinted chips, dark map
markers and popups, the photo banner's dark fade). Every rule is scoped to [data-theme="light"],
so the dark themes are untouched. Injected after the other theme rules, so equal-specificity
ties go to these.
"""

LIGHT_THEME_CSS = """
  /* ---------- Light theme ---------- */
  [data-theme="light"] body { background: var(--bg); color: var(--fg); }

  /* Banner: keep the Boston art, fade it into the page instead of into black */
  [data-theme="light"] .banner {
    background-color: #e9ecf3;
    background-image:
      linear-gradient(180deg, rgba(245, 246, 250, 0.10) 0%, rgba(245, 246, 250, 0.72) 55%, rgba(245, 246, 250, 1) 100%),
      url('banner.jpg');
  }
  [data-theme="light"] .banner-title { color: #10131c; text-shadow: 0 1px 12px rgba(255, 255, 255, 0.7); }
  [data-theme="light"] .banner-top-tag {
    color: #92400e;
    text-shadow: none;
    background: rgba(255, 255, 255, 0.82);
    padding: 3px 10px;
    border-radius: 999px;
  }
  [data-theme="light"] .banner-meta-pill {
    background: rgba(255, 255, 255, 0.82);
    border-color: var(--border);
    box-shadow: 0 2px 10px rgba(15, 23, 42, 0.10);
  }
  [data-theme="light"] .pill-weather { color: var(--fg); }
  [data-theme="light"] .theme-toggle-wrap {
    background: rgba(255, 255, 255, 0.85);
    border-color: var(--border);
  }
  [data-theme="light"] .theme-pill-btn:hover { color: var(--fg); }
  [data-theme="light"] .theme-pill-btn.active { background: var(--accent); color: #fff; box-shadow: 0 1px 4px rgba(37, 99, 235, 0.35); }
  [data-theme="light"] .theme-pill-holiday { color: var(--fg); }
  [data-theme="light"] .holiday-greeting { color: var(--fg); }

  /* Surfaces that were white-on-dark tints */
  [data-theme="light"] .event { background: transparent; border-color: rgba(15, 23, 42, 0.07); }
  [data-theme="light"] .event:hover { background: var(--card-hover); }
  [data-theme="light"] .subgenre-container,
  [data-theme="light"] .subarea-chips-bar,
  [data-theme="light"] .past-events-banner,
  [data-theme="light"] .map-venue-card,
  [data-theme="light"] .popup-event-item,
  [data-theme="light"] .chk:hover { background: rgba(15, 23, 42, 0.03); }
  [data-theme="light"] .loc-chip,
  [data-theme="light"] .sub-chip,
  [data-theme="light"] .chip,
  [data-theme="light"] .transit-chip,
  [data-theme="light"] .btn-upvote,
  [data-theme="light"] .cal-btn,
  [data-theme="light"] .genre-tag-list li a,
  [data-theme="light"] .view-toggle,
  [data-theme="light"] .map-toggle-btn,
  [data-theme="light"] .map-tool-btn,
  [data-theme="light"] .near-stream-clear-btn,
  [data-theme="light"] .past-banner-btn,
  [data-theme="light"] .modal-tabs,
  [data-theme="light"] .modal-close-btn,
  [data-theme="light"] .count,
  [data-theme="light"] .price { background: rgba(15, 23, 42, 0.05); }
  [data-theme="light"] .search-kbd { background: rgba(15, 23, 42, 0.06); border-color: var(--border); }

  /* Hover and active states that turned text white */
  [data-theme="light"] .loc-chip:hover,
  [data-theme="light"] .sub-chip:hover,
  [data-theme="light"] .chip:hover,
  [data-theme="light"] .transit-chip:hover,
  [data-theme="light"] .subgenre-btn:hover,
  [data-theme="light"] .past-banner-btn:hover,
  [data-theme="light"] .modal-close-btn:hover {
    background: rgba(15, 23, 42, 0.08);
    border-color: var(--border-hover);
    color: var(--fg);
  }
  [data-theme="light"] .cal-btn:hover,
  [data-theme="light"] .btn-reset-filters:hover,
  [data-theme="light"] .chip-starred:hover,
  [data-theme="light"] .chip-copy-plan:hover,
  [data-theme="light"] .compare-tickets a:hover,
  [data-theme="light"] .modal-tab:hover,
  [data-theme="light"] .btn-cancel:hover,
  [data-theme="light"] .leaflet-container a.leaflet-popup-close-button:hover { color: var(--fg) !important; }
  [data-theme="light"] .loc-chip.active { background: rgba(15, 23, 42, 0.08); border-color: rgba(15, 23, 42, 0.35); color: var(--fg); }
  [data-theme="light"] .loc-chip.active[data-city="boston"] { color: #1d4ed8; }
  [data-theme="light"] .loc-chip.active[data-city="cambridge"] { color: #be123c; }
  [data-theme="light"] .loc-chip.active[data-city="somerville"] { color: #c2410c; }
  [data-theme="light"] .loc-chip.active[data-city="other"] { color: #374151; }
  [data-theme="light"] .sub-chip.active,
  [data-theme="light"] .chip-active-genre,
  [data-theme="light"] .chip-featured.active { color: var(--fg) !important; }
  [data-theme="light"] .transit-chip.active[data-transit="green"] { color: #047857; }
  [data-theme="light"] .transit-chip.active[data-transit="orange"] { color: #c2410c; }
  [data-theme="light"] .transit-chip.active[data-transit="blue"] { color: #1d4ed8; }
  [data-theme="light"] .past-banner-badge.badge-all { background: rgba(15, 23, 42, 0.06); border-color: var(--border-hover); }

  /* Links and accent text: darker shades that read on white */
  [data-theme="light"] .what a { color: #1d4ed8; }
  [data-theme="light"] .what a:hover { color: #1e3a8a; }
  [data-theme="light"] .price.ticketed { color: #1d4ed8; background: rgba(37, 99, 235, 0.08); border-color: rgba(37, 99, 235, 0.3); }
  [data-theme="light"] .compare-tickets a { color: #1d4ed8; border-bottom-color: rgba(29, 78, 216, 0.35); }
  [data-theme="light"] .chip-copy-plan { color: #1d4ed8; }
  [data-theme="light"] .recur { color: #be185d; background: rgba(219, 39, 119, 0.08); }
  [data-theme="light"] .chk-saved span,
  [data-theme="light"] .chip-starred,
  [data-theme="light"] .star-btn:hover,
  [data-theme="light"] .star-btn.starred,
  [data-theme="light"] .btn-upvote.voted,
  [data-theme="light"] .btn-upvote.voted .upvote-arrow,
  [data-theme="light"] .event.glowing .btn-upvote,
  [data-theme="light"] .badge-highlight,
  [data-theme="light"] .chip-popular:hover { color: #b45309; }
  [data-theme="light"] .chip-popular,
  [data-theme="light"] .event.popular .btn-upvote,
  [data-theme="light"] .badge-popular,
  [data-theme="light"] .past-banner-badge.badge-done,
  [data-theme="light"] .chip-time-custom { color: #c2410c !important; }
  [data-theme="light"] .btn-copy-plan-sidebar,
  [data-theme="light"] .week-nav button.chip-copy-plan,
  [data-theme="light"] .btn-pill-free,
  [data-theme="light"] .form-status.success { color: #047857; }
  [data-theme="light"] .btn-copy-plan-sidebar:hover,
  [data-theme="light"] .week-nav button.chip-copy-plan:hover { color: #065f46; }
  [data-theme="light"] .curator-note { color: #78350f; background: rgba(245, 158, 11, 0.10); }
  [data-theme="light"] .curator-note .note-label { color: #92400e; }

  /* Category and genre pills get their color inline (pastels picked for a dark page). Darken the
     text so it reads on white; the tinted background and border stay. */
  [data-theme="light"] .cat-pill { color: color-mix(in srgb, var(--cat-c, #555) 60%, #000) !important; }
  [data-theme="light"] .cat-pill .chip-icon { filter: none; }

  /* Calendar range dots */
  [data-theme="light"] .mini-cal-grid .d.anchor::after,
  [data-theme="light"] .mini-cal-grid .d.range-start::after,
  [data-theme="light"] .mini-cal-grid .d.range-end::after { background: #ffffff; }

  /* Map: plain OpenStreetMap tiles instead of the inverted dark ones, light markers and popups */
  [data-theme="light"] .leaflet-map,
  [data-theme="light"] .leaflet-container.osm-dark-tiles,
  [data-theme="light"] .leaflet-container.osm-dark-tiles .leaflet-tile-container { background: #e8ebf1 !important; }
  [data-theme="light"] .leaflet-container.osm-dark-tiles .leaflet-tile-pane { filter: saturate(0.85); }
  [data-theme="light"] .leaflet-control-attribution { background: rgba(255, 255, 255, 0.85) !important; }
  [data-theme="light"] .leaflet-bar a { background-color: #ffffff !important; color: var(--fg) !important; }
  [data-theme="light"] .leaflet-bar a:hover { background-color: #eef1f6 !important; }
  [data-theme="light"] .venue-marker {
    background: #ffffff;
    color: var(--fg);
    box-shadow: 0 2px 8px rgba(15, 23, 42, 0.25);
  }
  [data-theme="light"] .venue-marker:hover .pin-count,
  [data-theme="light"] .venue-marker.highlighted .pin-count { background: #ffffff; color: var(--accent); }
  [data-theme="light"] .leaflet-popup-content-wrapper,
  [data-theme="light"] .leaflet-popup-tip {
    background: #ffffff !important;
    color: var(--fg) !important;
    border-color: var(--border) !important;
  }
  [data-theme="light"] .popup-head strong,
  [data-theme="light"] .map-venue-card-head h3 { color: var(--fg); }

  /* Add-event / suggest-venue modal */
  [data-theme="light"] .modal-overlay { background: rgba(15, 23, 42, 0.45); }
  [data-theme="light"] .modal-card { background: #ffffff; }
  [data-theme="light"] .modal-title { color: var(--fg); }
  [data-theme="light"] .form-label { color: #374151; }
  [data-theme="light"] .form-input,
  [data-theme="light"] .form-select,
  [data-theme="light"] .form-textarea { background: #ffffff; color: var(--fg); }
  [data-theme="light"] .form-select option { background: #ffffff; color: var(--fg); }
"""
