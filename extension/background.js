// background.js - Manifest V3 service worker
// Handles ESPN cookie retrieval, server communication, and response relay

const SERVER_URL = "http://localhost:8000/draft_update";
const MANUAL_URL = "http://localhost:8000/manual";
const HEALTH_URL = "http://localhost:8000/health";
const HEALTH_INTERVAL_MS = 5000;

// Hardcode fallback tokens here if cookie reading fails.
// Leave as null to rely on browser cookies.
const HARDCODED_SWID = null;
const HARDCODED_ESPN_S2 = null;

// =========================================================
// Cookie Management
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
    console.error("[FAA Background] Error reading cookies:", err);
  }

  return cookies;
}

// =========================================================
// Server Communication
// =========================================================

async function sendToServer(payload) {
  const cookies = await getESPNCookies();

  const body = {
    ...payload,
    auth: {
      swid: cookies.swid || null,
      espn_s2: cookies.espn_s2 || null,
    },
  };

  const response = await fetch(SERVER_URL, {
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

  if (message.type === "START_STREAM") {
    startStreaming(message.playerName, message.bid, sender.tab?.id);
    sendResponse({ ok: true });
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
      });

      // Start AI streaming if there's an active nomination
      const nom = payload.currentNomination;
      if (nom && nom.playerName && tabId) {
        startStreaming(nom.playerName, payload.currentBid, tabId);
      }
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
    const response = await fetch(MANUAL_URL, {
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
// Health Monitoring — 5s heartbeat
// =========================================================

async function checkHealth() {
  try {
    const resp = await fetch(HEALTH_URL, { method: "GET" });
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
      url: ["https://fantasy.espn.com/*/draft*"],
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

setInterval(checkHealth, HEALTH_INTERVAL_MS);

// =========================================================
// SSE Streaming — progressive AI advice
// =========================================================

let activeStreamController = null;

async function startStreaming(playerName, bid, tabId) {
  // Abort any existing stream
  if (activeStreamController) {
    try { activeStreamController.abort(); } catch {}
    activeStreamController = null;
  }

  const controller = new AbortController();
  activeStreamController = controller;

  const url = `http://localhost:8000/stream/${encodeURIComponent(playerName)}?bid=${bid || 0}`;

  try {
    // Notify content script that streaming started
    if (tabId) {
      await chrome.tabs.sendMessage(tabId, {
        type: "SERVER_RESPONSE",
        payload: { aiStart: true },
      }).catch(() => {});
    }

    const resp = await fetch(url, { signal: controller.signal });
    if (!resp.ok || !resp.body) return;

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          try {
            const data = JSON.parse(line.slice(6));
            if (data.type === "ai_chunk" && data.text && tabId) {
              await chrome.tabs.sendMessage(tabId, {
                type: "SERVER_RESPONSE",
                payload: { aiChunk: data.text },
              }).catch(() => {});
            }
            if (data.type === "done" && tabId) {
              await chrome.tabs.sendMessage(tabId, {
                type: "SERVER_RESPONSE",
                payload: { aiDone: true },
              }).catch(() => {});
            }
          } catch {
            // Non-JSON SSE line, skip
          }
        }
      }
    }
  } catch (err) {
    if (err.name !== "AbortError") {
      console.warn("[FAA] Streaming error:", err);
    }
  } finally {
    if (activeStreamController === controller) {
      activeStreamController = null;
    }
  }
}

console.log("[Fantasy Auction Assistant] Background service worker loaded");
