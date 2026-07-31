'use strict';

// Theme system: 7 brand colour swatches + light/dark mode.
// Default is always light + classic (#ccffcc), regardless of OS preference.
// Once the user picks something, it is persisted.
// Classic script, so these are plain globals rather than ES module exports.

const APP_KEY = "sgchn-dict";

const COLOR_THEMES = [
  { id: "classic", label: "Classic", hex: "#ccffcc" },
  { id: "not-green-1", label: "Not green 1", hex: "#ffcccc" },
  { id: "not-green-2", label: "Not green 2", hex: "#ccccff" },
  { id: "not-green-3", label: "Not green 3", hex: "#ffffcc" },
  { id: "not-green-4", label: "Not green 4", hex: "#ffccff" },
  { id: "not-green-5", label: "Not green 5", hex: "#ccffff" },
  { id: "really-light-green", label: "Really really light green", hex: "#ffffff" },
];

const STORAGE_KEY_COLOR = `${APP_KEY}.colorTheme`;
const STORAGE_KEY_MODE = `${APP_KEY}.mode`;

// Old key held one of: classic, notgreen1..5, white. Mode did not exist.
const LEGACY_KEY = "sgchn_theme";
const LEGACY_IDS = {
  classic: "classic",
  notgreen1: "not-green-1",
  notgreen2: "not-green-2",
  notgreen3: "not-green-3",
  notgreen4: "not-green-4",
  notgreen5: "not-green-5",
  white: "really-light-green",
};

function migrateLegacyTheme() {
  const old = localStorage.getItem(LEGACY_KEY);
  if (!old) return;
  if (!localStorage.getItem(STORAGE_KEY_COLOR) && LEGACY_IDS[old]) {
    localStorage.setItem(STORAGE_KEY_COLOR, LEGACY_IDS[old]);
  }
  localStorage.removeItem(LEGACY_KEY);
}

function hexToRgb(hex) {
  const n = parseInt(hex.replace("#", ""), 16);
  return `${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}`;
}

function getStoredColorTheme() {
  return localStorage.getItem(STORAGE_KEY_COLOR) || "classic";
}

function getStoredMode() {
  return localStorage.getItem(STORAGE_KEY_MODE) || "light";
}

function applyColorTheme(id) {
  const theme = COLOR_THEMES.find((t) => t.id === id) || COLOR_THEMES[0];
  document.documentElement.setAttribute("data-color-theme", theme.id);
  document.documentElement.style.setProperty("--brand", theme.hex);
  document.documentElement.style.setProperty("--brand-rgb", hexToRgb(theme.hex));
  localStorage.setItem(STORAGE_KEY_COLOR, theme.id);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", theme.hex);
  return theme;
}

function applyMode(mode) {
  const resolved = mode === "dark" ? "dark" : "light";
  document.documentElement.setAttribute("data-mode", resolved);
  localStorage.setItem(STORAGE_KEY_MODE, resolved);
  return resolved;
}

function initTheme() {
  migrateLegacyTheme();
  applyColorTheme(getStoredColorTheme());
  applyMode(getStoredMode());
}

// ---- wiring ----
// The app has no app.js entry point that owns UI wiring, so per the spec this
// lives next to the state it drives.

function buildThemeModal() {
  const grid = document.getElementById("swatchGrid");
  grid.innerHTML = COLOR_THEMES.map(
    (t) => `
      <button class="swatch" data-theme-id="${t.id}" style="--swatch-color:${t.hex}" type="button" aria-label="${t.label}">
        <span class="swatch-dot"></span>
        <span class="swatch-label">${t.label}</span>
      </button>`
  ).join("");

  syncThemeModalState();

  grid.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-theme-id]");
    if (!btn) return;
    applyColorTheme(btn.dataset.themeId);
    syncThemeModalState();
  });

  document.getElementById("modeToggle").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-mode]");
    if (!btn) return;
    applyMode(btn.dataset.mode);
    syncThemeModalState();
  });
}

function syncThemeModalState() {
  const activeTheme = getStoredColorTheme();
  const activeMode = getStoredMode();
  document.querySelectorAll("#swatchGrid .swatch").forEach((el) => {
    const active = el.dataset.themeId === activeTheme;
    el.classList.toggle("active", active);
    el.setAttribute("aria-pressed", String(active));
  });
  document.querySelectorAll("#modeToggle .mode-btn").forEach((el) => {
    const active = el.dataset.mode === activeMode;
    el.classList.toggle("active", active);
    el.setAttribute("aria-pressed", String(active));
  });
  updateThemeButtonIcon();
}

function updateThemeButtonIcon() {
  const span = document.querySelector("#themeBtn [data-icon]");
  span.setAttribute("data-icon", getStoredMode() === "dark" ? "moon" : "sun");
  hydrateIcons(document.getElementById("themeBtn"));
}

function wireModals() {
  const themeBtn = document.getElementById("themeBtn");

  document.querySelectorAll("[data-close-modal]").forEach((btn) => {
    btn.addEventListener("click", () => closeModal(btn.dataset.closeModal));
  });
  document.querySelectorAll(".modal-backdrop").forEach((backdrop) => {
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) closeModal(backdrop.id);
    });
  });
  themeBtn.addEventListener("click", () => {
    openModal("themeModal");
    document.querySelector('#themeModal [data-close-modal]').focus();
  });

  // Existing behaviour: Escape closes, and focus returns to the trigger.
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    const open = document.querySelector(".modal-backdrop:not(.hidden)");
    if (!open) return;
    closeModal(open.id);
    themeBtn.focus();
  });
}

function bootTheme() {
  initTheme();
  if (!document.getElementById("themeBtn")) return;
  hydrateIcons();
  updateThemeButtonIcon();
  buildThemeModal();
  wireModals();
}

bootTheme();
