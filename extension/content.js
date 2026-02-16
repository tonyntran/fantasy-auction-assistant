// content.js - MAIN world script
// Accesses ESPN's React fiber state to extract live auction draft data

(function () {
  "use strict";

  const POLL_INTERVAL_MS = 500;
  const MESSAGE_TYPE = "FANTASY_AUCTION_ASSISTANT";
  let overlayElement = null;
  let lastDataHash = null;
  let debugDumped = false;
  let minimizeState = 0; // 0=full, 1=compact, 2=hidden

  // Watch list (persisted in localStorage)
  const WATCHLIST_KEY = "faa_watchlist";
  function getWatchList() {
    try { return JSON.parse(localStorage.getItem(WATCHLIST_KEY) || "[]"); } catch { return []; }
  }
  function setWatchList(list) {
    localStorage.setItem(WATCHLIST_KEY, JSON.stringify(list));
  }

  // =========================================================
  // SECTION 1: React Fiber Traversal & Data Extraction
  // =========================================================

  function findReactFiberRoot() {
    const candidates = [
      document.getElementById("app"),
      document.getElementById("root"),
      document.querySelector("[data-reactroot]"),
      document.querySelector(".app-container"),
      document.body,
    ].filter(Boolean);

    for (const el of candidates) {
      const fiberKey = Object.keys(el).find(
        (key) =>
          key.startsWith("__reactFiber$") ||
          key.startsWith("__reactInternalInstance$")
      );
      if (fiberKey) return el[fiberKey];
    }

    // Fallback: scan direct children of body
    for (const el of document.body.children) {
      const fiberKey = Object.keys(el).find(
        (key) =>
          key.startsWith("__reactFiber$") ||
          key.startsWith("__reactInternalInstance$")
      );
      if (fiberKey) return el[fiberKey];
    }

    return null;
  }

  function getInitialState() {
    return window.__INITIAL_STATE__ || null;
  }

  function walkFiberTree(fiber, maxDepth = 50) {
    const results = {
      draftDetail: null,
      teams: null,
      players: null,
      leagueSettings: null,
    };

    function walk(node, depth) {
      if (!node || depth > maxDepth) return;

      // Check memoizedProps
      const props = node.memoizedProps;
      if (props && typeof props === "object") {
        extractDraftData(props, results);
      }

      // Check memoizedState (hooks linked list)
      let hookState = node.memoizedState;
      while (hookState) {
        if (
          hookState.memoizedState &&
          typeof hookState.memoizedState === "object"
        ) {
          extractDraftData(hookState.memoizedState, results);
        }
        hookState = hookState.next;
      }

      // Check stateNode (class components)
      if (node.stateNode && node.stateNode.state) {
        extractDraftData(node.stateNode.state, results);
      }

      walk(node.child, depth + 1);
      walk(node.sibling, depth + 1);
    }

    walk(fiber, 0);
    return results;
  }

  function extractDraftData(obj, results) {
    if (!obj || typeof obj !== "object") return;

    // draftDetail — ESPN's primary draft state container
    if (obj.draftDetail && obj.draftDetail.picks) {
      results.draftDetail = obj.draftDetail;
    }

    // teams array with budget info
    if (Array.isArray(obj.teams) && obj.teams.length > 0) {
      const first = obj.teams[0];
      if (
        first &&
        ("draftBudget" in first ||
          "remainingBudget" in first ||
          "roster" in first ||
          "teamId" in first)
      ) {
        results.teams = obj.teams;
      }
    }

    // players map
    if (
      obj.players &&
      typeof obj.players === "object" &&
      !Array.isArray(obj.players)
    ) {
      const sampleKey = Object.keys(obj.players)[0];
      if (
        sampleKey &&
        obj.players[sampleKey] &&
        obj.players[sampleKey].fullName
      ) {
        results.players = obj.players;
      }
    }

    // league settings
    if (obj.settings && obj.settings.draftSettings) {
      results.leagueSettings = obj.settings;
    }

    // Alternative: direct current pick references
    if (obj.currentPick || obj.currentNomination) {
      results.draftDetail = results.draftDetail || {};
      Object.assign(results.draftDetail, {
        currentPick: obj.currentPick,
        currentNomination: obj.currentNomination,
      });
    }
  }

  // =========================================================
  // SECTION 2: Payload Builder
  // =========================================================

  function detectSport() {
    const url = window.location.href;
    if (url.includes('/basketball/')) return 'basketball';
    if (url.includes('/baseball/')) return 'baseball';
    if (url.includes('/hockey/')) return 'hockey';
    return 'football';
  }

  function buildDraftPayload(rawData) {
    const payload = {
      timestamp: Date.now(),
      currentNomination: null,
      currentBid: null,
      highBidder: null,
      teams: [],
      draftLog: [],
      rosters: {},
      sport: detectSport(),
    };

    if (rawData.draftDetail) {
      const detail = rawData.draftDetail;

      // Current nomination
      if (detail.currentPick || detail.currentNomination) {
        const nom = detail.currentPick || detail.currentNomination;
        payload.currentNomination = {
          playerId: nom.playerId,
          playerName: resolvePlayerName(nom.playerId, rawData.players),
          nominatingTeamId: nom.teamId || nom.nominatingTeamId,
        };
      }

      // Current bid — try many possible property names
      payload.currentBid =
        detail.currentBid ??
        detail.bidAmount ??
        detail.amount ??
        detail.currentBidAmount ??
        null;

      // High bidder — ESPN may use various property names
      payload.highBidder =
        detail.highBidder ||
        detail.highBiddingTeamId ||
        detail.currentTeamId ||
        detail.biddingTeamId ||
        detail.winningTeamId ||
        detail.teamId ||
        (detail.currentPick && detail.currentPick.teamId) ||
        null;

      // Resolve bidder name from teams if we got a numeric ID
      if (
        payload.highBidder &&
        typeof payload.highBidder === "number" &&
        Array.isArray(rawData.teams)
      ) {
        const bidderTeam = rawData.teams.find(
          (t) => (t.id || t.teamId) === payload.highBidder
        );
        if (bidderTeam) {
          payload.highBidder =
            bidderTeam.name || bidderTeam.abbrev || payload.highBidder;
        }
      }

      // Draft log (completed picks)
      if (Array.isArray(detail.picks)) {
        payload.draftLog = detail.picks
          .filter((pick) => pick.playerId && pick.playerId > 0)
          .map((pick) => ({
            playerId: pick.playerId,
            playerName: resolvePlayerName(pick.playerId, rawData.players),
            teamId: pick.teamId,
            bidAmount: pick.bidAmount || pick.price || 0,
            roundId: pick.roundId,
            roundPickNumber: pick.roundPickNumber,
            keeper: pick.keeper || false,
          }));
      }
    }

    // Teams & rosters
    if (Array.isArray(rawData.teams)) {
      payload.teams = rawData.teams.map((team) => ({
        teamId: team.id || team.teamId,
        name: team.name || team.abbrev || `Team ${team.id || team.teamId}`,
        abbrev: team.abbrev,
        totalBudget: team.draftBudget || team.totalBudget || 200,
        remainingBudget:
          team.remainingBudget ??
          (team.draftBudget || 200) -
            calculateSpent(team, rawData.draftDetail),
        rosterSize: team.roster ? team.roster.entries.length : 0,
      }));

      rawData.teams.forEach((team) => {
        const teamId = team.id || team.teamId;
        if (team.roster && team.roster.entries) {
          payload.rosters[teamId] = team.roster.entries.map((entry) => ({
            playerId: entry.playerId,
            playerName: resolvePlayerName(entry.playerId, rawData.players),
            position: entry.lineupSlotId,
            acquisitionType: entry.acquisitionType,
          }));
        }
      });
    }

    return payload;
  }

  function resolvePlayerName(playerId, playersMap) {
    if (!playersMap || !playerId) return `Player #${playerId}`;
    const player = playersMap[playerId];
    return player
      ? player.fullName || player.name || `Player #${playerId}`
      : `Player #${playerId}`;
  }

  function calculateSpent(team, draftDetail) {
    if (!draftDetail || !draftDetail.picks) return 0;
    const teamId = team.id || team.teamId;
    return draftDetail.picks
      .filter((p) => p.teamId === teamId && p.playerId > 0)
      .reduce((sum, p) => sum + (p.bidAmount || p.price || 0), 0);
  }

  // =========================================================
  // SECTION 3: DOM Scraping Fallback
  // =========================================================

  /**
   * If React fiber traversal fails, attempt to scrape visible DOM elements.
   * Selectors are best-effort and may need updating if ESPN changes markup.
   */
  function scrapeDOMFallback() {
    const payload = {
      timestamp: Date.now(),
      currentNomination: null,
      currentBid: null,
      highBidder: null,
      teams: [],
      draftLog: [],
      rosters: {},
      source: "dom-fallback",
    };

    // Current nomination — player card in the bidding area
    const nomEl =
      document.querySelector(".pick-player-name") ||
      document.querySelector(".bid-player .player-name") ||
      document.querySelector('[class*="PlayerOnBlock"] .player-name');
    if (nomEl) {
      payload.currentNomination = {
        playerId: null,
        playerName: nomEl.textContent.trim(),
        nominatingTeamId: null,
      };
    }

    // Current bid amount
    const bidEl =
      document.querySelector(".bid-amount") ||
      document.querySelector('[class*="currentBid"]') ||
      document.querySelector('[class*="BidAmount"]');
    if (bidEl) {
      const bidText = bidEl.textContent.replace(/[^0-9]/g, "");
      payload.currentBid = parseInt(bidText, 10) || null;
    }

    // High bidder
    const bidderEl =
      document.querySelector(".high-bidder") ||
      document.querySelector('[class*="highBid"] .team-name');
    if (bidderEl) {
      payload.highBidder = bidderEl.textContent.trim();
    }

    // Team budgets — team strip across the top
    const teamEls = document.querySelectorAll(
      '.draft-team, [class*="TeamBudget"], [class*="team-slot"]'
    );
    teamEls.forEach((el, idx) => {
      const nameEl = el.querySelector(".team-name, .abbrev");
      const budgetEl = el.querySelector(
        ".budget, .remaining, [class*='budget']"
      );
      payload.teams.push({
        teamId: idx + 1,
        name: nameEl ? nameEl.textContent.trim() : `Team ${idx + 1}`,
        abbrev: null,
        totalBudget: 200,
        remainingBudget: budgetEl
          ? parseInt(budgetEl.textContent.replace(/[^0-9]/g, ""), 10) || null
          : null,
        rosterSize: null,
      });
    });

    // Draft log — completed pick rows
    const pickRows = document.querySelectorAll(
      '.pick-row, [class*="CompletedPick"], [class*="pick-history"] li'
    );
    pickRows.forEach((row) => {
      const nameEl = row.querySelector(".player-name");
      const priceEl = row.querySelector(".price, .bid-amount");
      if (nameEl) {
        payload.draftLog.push({
          playerId: null,
          playerName: nameEl.textContent.trim(),
          teamId: null,
          bidAmount: priceEl
            ? parseInt(priceEl.textContent.replace(/[^0-9]/g, ""), 10) || 0
            : 0,
        });
      }
    });

    return payload;
  }

  // =========================================================
  // SECTION 4: Overlay UI
  // =========================================================

  function createOverlay() {
    if (overlayElement) return;

    overlayElement = document.createElement("div");
    overlayElement.id = "faa-overlay";
    overlayElement.innerHTML = `
      <div id="faa-header">
        <span id="faa-title">Auction Assistant</span>
        <span id="faa-status" class="faa-disconnected">&#x25CF;</span>
        <button id="faa-minimize">_</button>
      </div>
      <div id="faa-compact" style="display:none">
        <div id="faa-compact-line"></div>
      </div>
      <div id="faa-body">
        <div id="faa-advice">Waiting for draft data...</div>
        <div id="faa-nomination"></div>
        <div id="faa-bid-info"></div>
        <div id="faa-ai-reasoning"></div>
        <div id="faa-roster"></div>
        <div id="faa-top-remaining"></div>
        <div id="faa-ticker"></div>
        <div id="faa-manual">
          <input id="faa-manual-input" type="text" placeholder='e.g. "Bijan 55", "watch Kelce", "undo"' />
          <button id="faa-manual-btn">Send</button>
        </div>
      </div>
    `;

    // Inline styles as fallback (MAIN world cannot use chrome.runtime.getURL)
    applyInlineStyles();
    document.body.appendChild(overlayElement);
    makeDraggable(overlayElement);
    setupMinimize();
    setupManualInput();
  }

  function applyInlineStyles() {
    const el = overlayElement;
    el.style.cssText = `
      position: fixed; top: 20px; right: 20px; width: 340px;
      max-height: 500px; background: #1a1a2e; color: #e0e0e0;
      border: 1px solid #16213e; border-radius: 8px;
      box-shadow: 0 4px 20px rgba(0,0,0,0.5); z-index: 999999;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      font-size: 13px; overflow: hidden; user-select: none;
      transition: border-color 0.3s ease;
    `;

    const header = el.querySelector("#faa-header");
    header.style.cssText = `
      display: flex; align-items: center; padding: 8px 12px;
      background: #16213e; cursor: grab; border-bottom: 1px solid #0f3460;
    `;

    const title = el.querySelector("#faa-title");
    title.style.cssText = "flex: 1; font-weight: 600; font-size: 14px; color: #e94560;";

    const status = el.querySelector("#faa-status");
    status.style.cssText = "font-size: 16px; margin-right: 8px; color: #ff1744;";

    const minBtn = el.querySelector("#faa-minimize");
    minBtn.style.cssText = `
      background: none; border: 1px solid #0f3460; color: #aaa;
      font-size: 14px; cursor: pointer; padding: 2px 8px; border-radius: 4px; line-height: 1;
    `;

    // Compact mode line
    const compact = el.querySelector("#faa-compact");
    compact.style.cssText = "padding: 6px 12px; font-size: 12px; color: #aaa;";

    const body = el.querySelector("#faa-body");
    body.style.cssText = "padding: 12px; overflow-y: auto; max-height: 440px;";

    const advice = el.querySelector("#faa-advice");
    advice.style.cssText = `
      padding: 8px 10px; background: #0f3460; border-radius: 6px;
      margin-bottom: 8px; line-height: 1.5; white-space: pre-wrap;
    `;

    const nom = el.querySelector("#faa-nomination");
    nom.style.cssText = `
      padding: 6px 0; font-weight: 500; color: #e94560;
      border-bottom: 1px solid #16213e; margin-bottom: 4px;
    `;

    const bid = el.querySelector("#faa-bid-info");
    bid.style.cssText = "padding: 4px 0; color: #aaa; font-size: 12px;";

    // AI reasoning section
    const aiReasoning = el.querySelector("#faa-ai-reasoning");
    aiReasoning.style.cssText = `
      padding: 6px 8px; margin-top: 6px; background: #12203a;
      border-radius: 4px; font-size: 11px; color: #8899aa;
      line-height: 1.4; white-space: pre-wrap; display: none;
      max-height: 80px; overflow-y: auto;
    `;

    // Mini roster display
    const roster = el.querySelector("#faa-roster");
    roster.style.cssText = `
      margin-top: 8px; padding: 6px 8px; background: #12203a;
      border-radius: 4px; font-size: 11px; color: #aaa; line-height: 1.6;
    `;

    // Top remaining display
    const topRemaining = el.querySelector("#faa-top-remaining");
    topRemaining.style.cssText = `
      margin-top: 6px; padding: 6px 8px; background: #12203a;
      border-radius: 4px; font-size: 11px; color: #aaa; line-height: 1.5;
    `;

    // Ticker section
    const tickerEl = el.querySelector("#faa-ticker");
    tickerEl.style.cssText = `
      margin-top: 6px; padding: 6px 8px; background: #12203a;
      border-radius: 4px; font-size: 10px; color: #aaa; line-height: 1.5;
      max-height: 80px; overflow-y: auto;
    `;

    const manual = el.querySelector("#faa-manual");
    manual.style.cssText = `
      display: flex; gap: 4px; margin-top: 8px; padding-top: 8px;
      border-top: 1px solid #16213e;
    `;

    const manualInput = el.querySelector("#faa-manual-input");
    manualInput.style.cssText = `
      flex: 1; background: #0f3460; border: 1px solid #16213e; color: #e0e0e0;
      padding: 6px 8px; border-radius: 4px; font-size: 12px; outline: none;
      font-family: inherit;
    `;

    const manualBtn = el.querySelector("#faa-manual-btn");
    manualBtn.style.cssText = `
      background: #e94560; border: none; color: #fff; padding: 6px 10px;
      border-radius: 4px; cursor: pointer; font-size: 12px; font-weight: 600;
    `;
  }

  function makeDraggable(el) {
    const header = el.querySelector("#faa-header");
    let isDragging = false;
    let offsetX, offsetY;

    header.addEventListener("mousedown", (e) => {
      isDragging = true;
      offsetX = e.clientX - el.getBoundingClientRect().left;
      offsetY = e.clientY - el.getBoundingClientRect().top;
      header.style.cursor = "grabbing";
    });

    document.addEventListener("mousemove", (e) => {
      if (!isDragging) return;
      el.style.left = e.clientX - offsetX + "px";
      el.style.top = e.clientY - offsetY + "px";
      el.style.right = "auto";
    });

    document.addEventListener("mouseup", () => {
      isDragging = false;
      if (header) header.style.cursor = "grab";
    });
  }

  function setupMinimize() {
    const btn = document.getElementById("faa-minimize");
    const body = document.getElementById("faa-body");
    const compact = document.getElementById("faa-compact");

    btn.addEventListener("click", () => {
      minimizeState = (minimizeState + 1) % 3;
      if (minimizeState === 0) {
        // Full
        body.style.display = "block";
        compact.style.display = "none";
        btn.textContent = "_";
      } else if (minimizeState === 1) {
        // Compact — one-liner with action + max bid
        body.style.display = "none";
        compact.style.display = "block";
        btn.textContent = "=";
      } else {
        // Hidden — header only
        body.style.display = "none";
        compact.style.display = "none";
        btn.textContent = "+";
      }
    });
  }

  function setupManualInput() {
    const input = document.getElementById("faa-manual-input");
    const btn = document.getElementById("faa-manual-btn");
    if (!input || !btn) return;

    function submitManual() {
      const cmd = input.value.trim();
      if (!cmd) return;
      input.value = "";

      // Local watch list commands
      const watchMatch = cmd.match(/^watch\s+(.+)$/i);
      const unwatchMatch = cmd.match(/^unwatch\s+(.+)$/i);
      if (watchMatch) {
        const name = watchMatch[1].trim();
        const list = getWatchList();
        if (!list.some(n => n.toLowerCase() === name.toLowerCase())) {
          list.push(name);
          setWatchList(list);
        }
        updateOverlayAdvice(`<span style="color:#00c853">Watching: ${list.join(", ")}</span>`);
        return;
      }
      if (unwatchMatch) {
        const name = unwatchMatch[1].trim().toLowerCase();
        const list = getWatchList().filter(n => n.toLowerCase() !== name);
        setWatchList(list);
        updateOverlayAdvice(`<span style="color:#aaa">Watch list: ${list.length ? list.join(", ") : "(empty)"}</span>`);
        return;
      }
      if (cmd.toLowerCase() === "watchlist") {
        const list = getWatchList();
        updateOverlayAdvice(`<span style="color:#aaa">Watch list: ${list.length ? list.join(", ") : "(empty)"}</span>`);
        return;
      }

      updateOverlayAdvice(
        '<span style="color:#aaa">Sending: "' + cmd + '"...</span>'
      );

      // Send manual command to bridge -> background -> server
      sendToBridge({ manualCommand: cmd });
    }

    btn.addEventListener("click", submitManual);
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") submitManual();
      // Stop ESPN from capturing keystrokes while typing
      e.stopPropagation();
    });
    // Also stop keyup/keypress from bubbling to ESPN
    input.addEventListener("keyup", (e) => e.stopPropagation());
    input.addEventListener("keypress", (e) => e.stopPropagation());
  }

  function updateOverlayStatus(connected) {
    const dot = document.getElementById("faa-status");
    if (!dot) return;
    dot.style.color = connected ? "#00c853" : "#ff1744";
    dot.title = connected ? "Connected to Python" : "Disconnected";
  }

  function updateOverlayAdvice(advice) {
    const el = document.getElementById("faa-advice");
    if (!el) return;
    el.innerHTML = advice;
  }

  function updateOverlayNomination(payload) {
    const nomEl = document.getElementById("faa-nomination");
    const bidEl = document.getElementById("faa-bid-info");
    if (!nomEl || !bidEl) return;

    if (payload.currentNomination) {
      nomEl.textContent = `On the block: ${payload.currentNomination.playerName}`;
      checkWatchListAlert(payload.currentNomination.playerName);
    } else {
      nomEl.textContent = "No active nomination";
    }

    if (payload.currentBid !== null && payload.currentBid !== undefined) {
      bidEl.textContent = `Current bid: $${payload.currentBid} (Team ${payload.highBidder || "?"})`;
    } else {
      bidEl.textContent = "";
    }
  }

  // =========================================================
  // SECTION 5: Message Passing
  // =========================================================

  window.addEventListener("message", (event) => {
    if (event.source !== window) return;
    if (!event.data || event.data.type !== MESSAGE_TYPE) return;
    if (event.data.direction !== "from-bridge") return;

    const p = event.data.payload;
    if (p.advice) updateOverlayAdvice(p.advice);
    if (p.connected !== undefined) updateOverlayStatus(p.connected);
    if (p.cssURL) injectCSS(p.cssURL);

    // New response fields from server
    const raw = p.raw;
    if (raw) {
      // Compact one-liner
      if (raw.suggestedBid !== undefined) {
        const compactEl = document.getElementById("faa-compact-line");
        if (compactEl) {
          const action = raw.advice?.includes("BUY") ? "BUY" : raw.advice?.includes("PASS") ? "PASS" : "—";
          const vonaText = raw.vona ? ` | VONA: ${raw.vona}` : '';
          compactEl.innerHTML = `<b style="color:#e94560">${action}</b> up to <b>$${raw.suggestedBid}</b>${vonaText}`;
        }
      }

      // Mini roster display
      if (raw.myRoster) {
        updateRosterDisplay(raw.myRoster);
      }

      // Top remaining
      if (raw.topRemaining) {
        updateTopRemainingDisplay(raw.topRemaining);
      }

      // Live ticker
      if (raw.tickerEvents) {
        updateTickerDisplay(raw.tickerEvents);
      }

      // Dead money alerts
      if (raw.deadMoneyAlerts && raw.deadMoneyAlerts.length) {
        showDeadMoneyNotification(raw.deadMoneyAlerts);
      }
    }

    // AI streaming chunk
    if (p.aiChunk) {
      appendAIReasoning(p.aiChunk);
    }
    if (p.aiDone) {
      // Streaming complete — no action needed
    }
    if (p.aiStart) {
      clearAIReasoning();
    }
  });

  function sendToBridge(payload) {
    window.postMessage(
      { type: MESSAGE_TYPE, direction: "from-main", payload },
      "*"
    );
  }

  function injectCSS(url) {
    if (document.getElementById("faa-stylesheet")) return;
    const link = document.createElement("link");
    link.id = "faa-stylesheet";
    link.rel = "stylesheet";
    link.href = url;
    document.head.appendChild(link);
  }

  // =========================================================
  // SECTION 5b: New Display Helpers
  // =========================================================

  function updateRosterDisplay(roster) {
    const el = document.getElementById("faa-roster");
    if (!el) return;
    const entries = Object.entries(roster).map(([slot, occupant]) => {
      if (occupant) {
        return `<span style="color:#e0e0e0">${slot}:</span> <span style="color:#00c853">${occupant}</span>`;
      }
      return `<span style="color:#e0e0e0">${slot}:</span> <span style="color:#555">—</span>`;
    });
    el.innerHTML = `<div style="font-weight:600;color:#e94560;margin-bottom:2px;font-size:10px">MY ROSTER</div>` + entries.join(" | ");
  }

  function updateTopRemainingDisplay(topRemaining) {
    const el = document.getElementById("faa-top-remaining");
    if (!el) return;
    let html = '<div style="font-weight:600;color:#e94560;margin-bottom:2px;font-size:10px">TOP REMAINING</div>';
    for (const [pos, players] of Object.entries(topRemaining)) {
      const names = players.slice(0, 3).map(p =>
        `${p.name} <span style="color:#00c853">$${p.fmv}</span>`
      ).join(", ");
      html += `<div><b>${pos}:</b> ${names || '<span style="color:#555">none</span>'}</div>`;
    }
    el.innerHTML = html;
  }

  function appendAIReasoning(chunk) {
    const el = document.getElementById("faa-ai-reasoning");
    if (!el) return;
    el.style.display = "block";
    el.textContent += chunk;
    el.scrollTop = el.scrollHeight;
  }

  function clearAIReasoning() {
    const el = document.getElementById("faa-ai-reasoning");
    if (!el) return;
    el.textContent = "";
    el.style.display = "none";
  }

  function updateTickerDisplay(events) {
    const el = document.getElementById("faa-ticker");
    if (!el || !events || !events.length) return;
    const TYPE_COLORS = {
      NEW_NOMINATION: "#3abff8",
      BID_PLACED: "#e0e0e0",
      PLAYER_SOLD: "#00c853",
      BUDGET_ALERT: "#ffab00",
      DEAD_MONEY: "#ff1744",
      MARKET_SHIFT: "#e94560",
    };
    const TYPE_ICONS = {
      NEW_NOMINATION: "\u{1F4E2}",
      BID_PLACED: "\u{1F4B5}",
      PLAYER_SOLD: "\u2705",
      BUDGET_ALERT: "\u26A0\uFE0F",
      DEAD_MONEY: "\u{1F4B8}",
      MARKET_SHIFT: "\u{1F4C8}",
    };
    const html = events.slice(0, 8).map(e => {
      const color = TYPE_COLORS[e.event_type] || "#aaa";
      const icon = TYPE_ICONS[e.event_type] || "";
      return `<div style="color:${color};padding:1px 0">${icon} ${e.message}</div>`;
    }).join("");
    el.innerHTML = `<div style="font-weight:600;color:#e94560;margin-bottom:2px;font-size:10px">LIVE TICKER</div>` + html;
    el.scrollTop = el.scrollHeight;
  }

  function showDeadMoneyNotification(alerts) {
    if (!alerts || !alerts.length) return;
    const overlay = document.getElementById("faa-overlay");
    if (overlay) {
      overlay.style.borderColor = "#ff1744";
      overlay.style.boxShadow = "0 0 25px rgba(255,23,68,0.6)";
      setTimeout(() => {
        overlay.style.borderColor = "#16213e";
        overlay.style.boxShadow = "0 4px 20px rgba(0,0,0,0.5)";
      }, 4000);
    }
    const adviceEl = document.getElementById("faa-advice");
    if (adviceEl) {
      const alertHtml = alerts.map(a =>
        `<div style="background:#3a0a0a;border:1px solid #ff1744;border-radius:4px;padding:6px 8px;margin-bottom:4px;font-size:11px">` +
        `<span style="color:#ff1744;font-weight:600">DEAD MONEY</span> ` +
        `${a.team} paid <b>$${a.draft_price}</b> for ${a.player_name} ` +
        `(FMV $${a.fmv_at_sale}, +${a.overpay_pct}% overpay)</div>`
      ).join("");
      adviceEl.insertAdjacentHTML("afterbegin", alertHtml);
      // Auto-dismiss after 8 seconds
      setTimeout(() => {
        const deadDivs = adviceEl.querySelectorAll('div[style*="3a0a0a"]');
        deadDivs.forEach(d => d.remove());
      }, 8000);
    }
  }

  function checkWatchListAlert(playerName) {
    if (!playerName) return;
    const watchList = getWatchList();
    const match = watchList.some(w =>
      playerName.toLowerCase().includes(w.toLowerCase()) ||
      w.toLowerCase().includes(playerName.toLowerCase())
    );
    if (match) {
      // Flash overlay border
      const el = document.getElementById("faa-overlay");
      if (el) {
        el.style.borderColor = "#e94560";
        el.style.boxShadow = "0 0 20px rgba(233,69,96,0.6)";
        setTimeout(() => {
          el.style.borderColor = "#16213e";
          el.style.boxShadow = "0 4px 20px rgba(0,0,0,0.5)";
        }, 3000);
      }
      // Inline beep — short sine wave
      try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.frequency.value = 880;
        gain.gain.value = 0.15;
        osc.start();
        osc.stop(ctx.currentTime + 0.15);
      } catch { /* audio may be blocked */ }
    }
  }

  // =========================================================
  // SECTION 6: Polling Loop
  // =========================================================

  function hashPayload(payload) {
    return JSON.stringify({
      nom: payload.currentNomination?.playerId,
      bid: payload.currentBid,
      bidder: payload.highBidder,
      logLen: payload.draftLog.length,
    });
  }

  function poll() {
    try {
      let rawData = null;

      // Strategy 1: __INITIAL_STATE__
      const initialState = getInitialState();
      if (initialState && initialState.draftDetail) {
        rawData = initialState;
      }

      // Strategy 2: React fiber tree
      if (!rawData) {
        const fiberRoot = findReactFiberRoot();
        if (fiberRoot) {
          rawData = walkFiberTree(fiberRoot);
        }
      }

      // Build payload from React state or fall back to DOM scraping
      let payload;
      if (rawData && (rawData.draftDetail || rawData.teams)) {
        payload = buildDraftPayload(rawData);

        // One-time debug dump — check Chrome DevTools console to see
        // the actual property names ESPN uses in draftDetail
        if (!debugDumped && rawData.draftDetail) {
          debugDumped = true;
          console.log(
            "[FAA DEBUG] draftDetail keys:",
            Object.keys(rawData.draftDetail)
          );
          console.log(
            "[FAA DEBUG] draftDetail snapshot:",
            JSON.parse(JSON.stringify(rawData.draftDetail, null, 2))
          );
          if (rawData.teams && rawData.teams[0]) {
            console.log(
              "[FAA DEBUG] first team keys:",
              Object.keys(rawData.teams[0])
            );
          }
          // Send debug info to server too
          payload._debug = {
            draftDetailKeys: Object.keys(rawData.draftDetail),
            firstTeamKeys: rawData.teams && rawData.teams[0]
              ? Object.keys(rawData.teams[0])
              : [],
          };
        }
      } else {
        payload = scrapeDOMFallback();
      }

      // Always update overlay locally
      updateOverlayNomination(payload);

      // Only POST to server if data changed
      const hash = hashPayload(payload);
      if (hash !== lastDataHash) {
        lastDataHash = hash;
        sendToBridge(payload);
      }
    } catch (err) {
      console.error("[Fantasy Auction Assistant] Poll error:", err);
      updateOverlayStatus(false);
    }
  }

  // =========================================================
  // SECTION 7: Init
  // =========================================================

  function init() {
    console.log("[Fantasy Auction Assistant] Content script loaded (MAIN world)");
    createOverlay();
    setInterval(poll, POLL_INTERVAL_MS);
    // Request CSS URL from bridge
    sendToBridge({ requestCSS: true });
  }

  if (document.readyState === "complete") {
    init();
  } else {
    window.addEventListener("load", init);
  }
})();
