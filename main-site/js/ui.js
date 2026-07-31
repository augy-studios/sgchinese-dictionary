'use strict';

// UI helpers. Classic script, so these are plain globals rather than ES
// module exports; the app does not use modules.

// Safe to call repeatedly; re-renders when data-icon changes.
function hydrateIcons(root = document) {
  root.querySelectorAll("[data-icon]").forEach((el) => {
    const name = el.dataset.icon;
    if (el.dataset.iconRendered === name) return;
    el.innerHTML = icon(name);
    el.dataset.iconRendered = name;
  });
}

function openModal(id) {
  document.getElementById(id).classList.remove("hidden");
  document.body.classList.add("modal-open");
}

function closeModal(id) {
  document.getElementById(id).classList.add("hidden");
  if (!document.querySelector(".modal-backdrop:not(.hidden)")) {
    document.body.classList.remove("modal-open");
  }
}

window.hydrateIcons = hydrateIcons;
window.openModal = openModal;
window.closeModal = closeModal;
