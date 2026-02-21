// background.js - Manifest V3 service worker
// Handles ESPN cookie retrieval, server communication, and response relay

const DEFAULT_SERVER = "http://localhost:8000";

async function getServerUrl() {
  try {
    const result = await chrome.storage.sync.get({ serverUrl: DEFAULT_SERVER });
    return result.serverUrl.replace(/\/+$/, '');  // strip trailing slash
  } catch {
    return DEFAULT_SERVER;
  }
}

// Hardcode fallback tokens here if cookie reading fails.
// Leave as null to rely on browser cookies.
const HARDCODED_SWID = null;
const HARDCODED_ESPN_S2 = null;

// =========================================================
// Platform Auth Management
// =========================================================

async function getESPNCookies() {
  const cookies = {
    swid: HARDCODED_SWID,
    espn_s2: HARDCODED_ESPN_S2,
  };

  try {
    const swid = await chrome.cookies.get({
      url: "https://espn.com",
      name: "SWID",
    });
    if (swid) cookies.swid = swid.value;

    const espnS2 = await chrome.cookies.get({
      url: "https://espn.com",
      name: "espn_s2",
    });
    if (espnS2) cookies.espn_s2 = espnS2.value;
  } catch (err) {
    console.error("[FAA Background] Error reading ESPN cookies:", err);
  }

  return cookies;
}

function parseSleeperInfoFromUrl(url) {
  // Extract draft_id from Sleeper URL: /draft/<sport>/<id> or /draft/<id>
  const match = url && url.match(/\/draft\/(?:\w+\/)?(\d+)/);
  return {
    sleeper_draft_id: match ? match[1] : null,
    sleeper_league_id: null, // League ID not in draft URL; will be resolved from draft API if needed
  };
}

async function getPlatformAuth(payload) {
  // Detect platform from the payload itself
  const platform = payload && payload.platform;

  if (platform === "sleeper") {
    // For Sleeper: parse IDs from the active tab URL
    try {
      const tabs = await chrome.tabs.query({
        active: true,
        currentWindow: true,
      });
      const activeTab = tabs[0];
      const sleeperInfo = parseSleeperInfoFromUrl(activeTab?.url);
      return {
        sleeper_draft_id: sleeperInfo.sleeper_draft_id,
        sleeper_league_id: sleeperInfo.sleeper_league_id,
      };
    } catch (err) {
      console.error("[FAA Background] Error getting Sleeper auth:", err);
      return {};
    }
  }

  // Default: ESPN cookies
  return await getESPNCookies();
}

// =========================================================
// Server Communication
// =========================================================

async function sendToServer(payload) {
  const auth = await getPlatformAuth(payload);
  const serverUrl = await getServerUrl();

  const body = {
    ...payload,
    auth,
  };

  const response = await fetch(`${serverUrl}/draft_update`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    throw new Error(`Server responded ${response.status}: ${response.statusText}`);
  }

  return await response.json();
}

// =========================================================
// Message Handling
// =========================================================

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "DRAFT_UPDATE") {
    handleDraftUpdate(message.payload, sender.tab?.id)
      .then(() => sendResponse({ success: true }))
      .catch((err) => {
        console.error("[FAA Background] Error:", err);
        sendResponse({ success: false, error: err.message });
      });
    return true;
  }

  if (message.type === "MANUAL_OVERRIDE") {
    handleManualOverride(message.command, sender.tab?.id)
      .then(() => sendResponse({ success: true }))
      .catch((err) => {
        console.error("[FAA Background] Manual override error:", err);
        sendResponse({ success: false, error: err.message });
      });
    return true;
  }
});

async function handleDraftUpdate(payload, tabId) {
  try {
    const serverResponse = await sendToServer(payload);

    // Relay AI advice back to the content script
    if (tabId && serverResponse) {
      await chrome.tabs.sendMessage(tabId, {
        type: "SERVER_RESPONSE",
        payload: {
          connected: true,
          advice:
            serverResponse.advice ||
            serverResponse.recommendation ||
            "No advice available",
          suggestedBid: serverResponse.suggestedBid,
          playerValue: serverResponse.playerValue,
          raw: serverResponse,
        },
      }).catch(() => {});
    }
  } catch (err) {
    // Server unreachable — notify the content script
    if (tabId) {
      await chrome.tabs
        .sendMessage(tabId, {
          type: "SERVER_RESPONSE",
          payload: {
            connected: false,
            advice: `Server error: ${err.message}`,
          },
        })
        .catch(() => {});
    }
    throw err;
  }
}

async function handleManualOverride(command, tabId) {
  try {
    const serverUrl = await getServerUrl();
    const response = await fetch(`${serverUrl}/manual`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command }),
    });

    if (!response.ok) {
      throw new Error(
        `Server responded ${response.status}: ${response.statusText}`
      );
    }

    const serverResponse = await response.json();

    if (tabId && serverResponse) {
      await chrome.tabs.sendMessage(tabId, {
        type: "SERVER_RESPONSE",
        payload: {
          connected: true,
          advice:
            serverResponse.advice || "Manual command processed.",
          suggestedBid: serverResponse.suggestedBid,
          playerValue: serverResponse.playerValue,
          raw: serverResponse,
        },
      });
    }
  } catch (err) {
    if (tabId) {
      await chrome.tabs
        .sendMessage(tabId, {
          type: "SERVER_RESPONSE",
          payload: {
            connected: false,
            advice: `Manual override error: ${err.message}`,
          },
        })
        .catch(() => {});
    }
    throw err;
  }
}

// =========================================================
// Health Monitoring — uses chrome.alarms (MV3-safe)
// =========================================================

async function checkHealth() {
  try {
    const serverUrl = await getServerUrl();
    const resp = await fetch(`${serverUrl}/health`, { method: "GET" });
    if (resp.ok) {
      broadcastToContentScripts({ connected: true });
    } else {
      broadcastToContentScripts({ connected: false });
    }
  } catch {
    broadcastToContentScripts({ connected: false });
  }
}

async function broadcastToContentScripts(payload) {
  try {
    const tabs = await chrome.tabs.query({
      url: [
        "https://fantasy.espn.com/*/draft*",
        "https://sleeper.com/draft/*",
        "https://sleeper.app/draft/*",
      ],
    });
    for (const tab of tabs) {
      chrome.tabs
        .sendMessage(tab.id, { type: "SERVER_RESPONSE", payload })
        .catch(() => {});
    }
  } catch {
    // No matching tabs
  }
}

// Use chrome.alarms instead of setInterval — survives service worker restarts
chrome.alarms.create("healthCheck", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "healthCheck") {
    checkHealth();
  }
});

console.log("[Fantasy Auction Assistant] Background service worker loaded");
