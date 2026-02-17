// content-bridge.js - ISOLATED world script
// Bridges MAIN world <-> background service worker communication

(function () {
  "use strict";

  const MESSAGE_TYPE = "FANTASY_AUCTION_ASSISTANT";

  // =========================================================
  // MAIN world -> bridge -> background service worker
  // =========================================================

  window.addEventListener("message", (event) => {
    if (event.source !== window) return;
    if (!event.data || event.data.type !== MESSAGE_TYPE) return;
    if (event.data.direction !== "from-main") return;

    // Handle CSS URL request from MAIN world
    if (event.data.payload?.requestCSS) {
      const cssURL = chrome.runtime.getURL("style.css");
      window.postMessage(
        {
          type: MESSAGE_TYPE,
          direction: "from-bridge",
          payload: { cssURL },
        },
        "*"
      );
      return;
    }

    // Handle Sleeper player cache: save to chrome.storage.local
    if (event.data.payload?.cacheSleeperPlayers) {
      chrome.storage.local.set({
        sleeperPlayers: event.data.payload.cacheSleeperPlayers,
        sleeperPlayersCachedAt: Date.now(),
      }).catch((err) => console.warn("[FAA Bridge] Failed to cache Sleeper players:", err));
      return;
    }

    // Handle Sleeper player cache: load from chrome.storage.local
    if (event.data.payload?.requestSleeperPlayersCache) {
      chrome.storage.local.get(["sleeperPlayers", "sleeperPlayersCachedAt"]).then((result) => {
        const ONE_WEEK_MS = 7 * 24 * 60 * 60 * 1000;
        const isStale = !result.sleeperPlayersCachedAt || (Date.now() - result.sleeperPlayersCachedAt > ONE_WEEK_MS);
        window.postMessage(
          {
            type: MESSAGE_TYPE,
            direction: "from-bridge",
            payload: { cachedSleeperPlayers: isStale ? null : (result.sleeperPlayers || null) },
          },
          "*"
        );
      }).catch(() => {
        window.postMessage(
          {
            type: MESSAGE_TYPE,
            direction: "from-bridge",
            payload: { cachedSleeperPlayers: null },
          },
          "*"
        );
      });
      return;
    }

    // Forward manual command to background service worker
    if (event.data.payload?.manualCommand) {
      chrome.runtime
        .sendMessage({
          type: "MANUAL_OVERRIDE",
          command: event.data.payload.manualCommand,
        })
        .catch((err) => {
          console.warn("[FAA Bridge] Failed to send manual command:", err);
          window.postMessage(
            {
              type: MESSAGE_TYPE,
              direction: "from-bridge",
              payload: {
                connected: false,
                advice: "Extension background disconnected",
              },
            },
            "*"
          );
        });
      return;
    }

    // Forward draft data to background service worker
    chrome.runtime
      .sendMessage({
        type: "DRAFT_UPDATE",
        payload: event.data.payload,
      })
      .catch((err) => {
        console.warn("[FAA Bridge] Failed to send to background:", err);
        window.postMessage(
          {
            type: MESSAGE_TYPE,
            direction: "from-bridge",
            payload: {
              connected: false,
              advice: "Extension background disconnected",
            },
          },
          "*"
        );
      });
  });

  // =========================================================
  // Background service worker -> bridge -> MAIN world
  // =========================================================

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === "SERVER_RESPONSE") {
      window.postMessage(
        {
          type: MESSAGE_TYPE,
          direction: "from-bridge",
          payload: message.payload,
        },
        "*"
      );
      sendResponse({ received: true });
    }
    return true;
  });

  console.log("[Fantasy Auction Assistant] Bridge script loaded (ISOLATED world)");
})();
