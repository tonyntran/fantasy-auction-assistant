// options.js - Settings page for Fantasy Auction Assistant

const DEFAULTS = {
  serverUrl: "http://localhost:8000",
  overlayPosition: "top-right",
};

document.addEventListener("DOMContentLoaded", () => {
  const serverUrlInput = document.getElementById("serverUrl");
  const overlayPositionSelect = document.getElementById("overlayPosition");
  const saveButton = document.getElementById("save");
  const savedMsg = document.getElementById("savedMsg");

  // Load saved settings
  chrome.storage.sync.get(DEFAULTS, (result) => {
    serverUrlInput.value = result.serverUrl;
    overlayPositionSelect.value = result.overlayPosition;
  });

  // Save settings
  saveButton.addEventListener("click", () => {
    const settings = {
      serverUrl: serverUrlInput.value.trim() || DEFAULTS.serverUrl,
      overlayPosition: overlayPositionSelect.value,
    };

    chrome.storage.sync.set(settings, () => {
      savedMsg.style.display = "inline";
      setTimeout(() => {
        savedMsg.style.display = "none";
      }, 2000);
    });
  });
});
