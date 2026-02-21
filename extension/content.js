// content.js - MAIN world script
// Accesses ESPN React fiber state or Sleeper API to extract live auction draft data

(function () {
  "use strict";

  const POLL_INTERVAL_MS = 500;
  const SLEEPER_API_BASE = "https://api.sleeper.app/v1";
  const MESSAGE_TYPE = "FANTASY_AUCTION_ASSISTANT";
  let overlayElement = null;
  let lastDataHash = null;
  let debugDumped = false;
  let minimizeState = 0; // 0=full, 1=compact, 2=hidden

  // =========================================================
  // Platform Detection
  // =========================================================

  function detectPlatform() {
    const host = window.location.hostname;
    if (host.includes("sleeper.com") || host.includes("sleeper.app")) return "sleeper";
    return "espn";
  }

  const PLATFORM = detectPlatform();

  // Install WebSocket interceptor immediately for Sleeper (before their JS connects)
  if (PLATFORM === "sleeper") {
    installSleeperWebSocketInterceptor();
  }

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
    // ESPN URLs: /football/draft, /basketball/draft, etc.
    if (url.includes('/basketball/')) return 'basketball';
    if (url.includes('/baseball/')) return 'baseball';
    if (url.includes('/hockey/')) return 'hockey';
    // Sleeper URLs: /draft/nfl/..., /draft/nba/..., etc.
    if (url.includes('/draft/nba/')) return 'basketball';
    if (url.includes('/draft/mlb/')) return 'baseball';
    if (url.includes('/draft/nhl/')) return 'hockey';
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

      // Resolve bidder name from teams if we got an ID (numeric or string)
      if (
        payload.highBidder &&
        (typeof payload.highBidder === "number" || typeof payload.highBidder === "string") &&
        Array.isArray(rawData.teams)
      ) {
        const bidderTeam = rawData.teams.find(
          (t) => String(t.id || t.teamId) === String(payload.highBidder)
        );
        if (bidderTeam && (bidderTeam.name || bidderTeam.abbrev)) {
          payload.highBidder =
            bidderTeam.name || bidderTeam.abbrev || payload.highBidder;
        }
      }

      // Draft log (completed picks)
      if (Array.isArray(detail.picks)) {
        payload.draftLog = detail.picks
          .filter((pick) => pick.playerId != null && pick.playerId !== "" && pick.playerId !== 0)
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
        const teamId = String(team.id || team.teamId);
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
      .filter((p) => p.teamId === teamId && p.playerId != null && p.playerId !== "" && p.playerId !== 0)
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
  // SECTION 3b: Sleeper — WebSocket Interceptor & API Extraction
  // =========================================================

  // In-memory player database cache (Sleeper player_id → player info)
  let sleeperPlayersCache = null;
  let sleeperPlayersCacheLoading = false;
  let sleeperDraftCache = null;
  let sleeperPicksCache = [];

  // Roster ID → display name mapping (fetched from league users/rosters)
  let sleeperRosterNames = {};  // roster_id string → display name
  let sleeperRosterNamesLoaded = false;
  let sleeperRosterNamesLoading = false;
  let sleeperLeagueRosters = [];  // Raw roster objects from league API

  // Real-time state captured from Sleeper's WebSocket
  let sleeperWsNomination = null;   // { player_id, amount, roster_id, ... }
  let sleeperWsBids = [];           // Recent bid events
  let sleeperWsLatestBid = null;    // Most recent bid on current nomination
  let sleeperWsConnected = false;
  let sleeperWsMessages = [];       // Debug: last N raw messages
  let sleeperWsSoldQueue = [];      // Picks detected as sold via WS (before REST catches up)

  /**
   * Intercept Sleeper's WebSocket to capture real-time draft events.
   * Must be called BEFORE Sleeper's JS connects (runs at document_idle in MAIN world).
   */
  function installSleeperWebSocketInterceptor() {
    const OriginalWebSocket = window.WebSocket;

    window.WebSocket = function (...args) {
      const ws = new OriginalWebSocket(...args);
      const url = args[0] || "";
      console.log("[FAA] WebSocket opened:", url);

      ws.addEventListener("message", (event) => {
        try {
          const raw = typeof event.data === "string" ? event.data : null;
          if (!raw) return;

          // Sleeper sends JSON messages — try to parse
          const msg = JSON.parse(raw);
          sleeperWsConnected = true;

          // Keep last 20 messages for debugging
          sleeperWsMessages.push(msg);
          if (sleeperWsMessages.length > 20) sleeperWsMessages.shift();

          processSleeperWsMessage(msg);
        } catch {
          // Not JSON or parse error — ignore
        }
      });

      ws.addEventListener("close", () => {
        console.log("[FAA] WebSocket closed:", url);
        sleeperWsConnected = false;
      });

      return ws;
    };

    // Preserve prototype chain so instanceof checks still work
    window.WebSocket.prototype = OriginalWebSocket.prototype;
    window.WebSocket.CONNECTING = OriginalWebSocket.CONNECTING;
    window.WebSocket.OPEN = OriginalWebSocket.OPEN;
    window.WebSocket.CLOSING = OriginalWebSocket.CLOSING;
    window.WebSocket.CLOSED = OriginalWebSocket.CLOSED;

    console.log("[FAA] Sleeper WebSocket interceptor installed");
  }

  function processSleeperWsMessage(msg) {
    // Sleeper WS messages are arrays:
    //   [null, null, "draft:<id>", "<event_type>", <data_object>]
    //
    // Known event types:
    //   "new_draft_offer"        — a bid/nomination on a player
    //     data: { user_id, time, slot, player_id, pick_no, roster_id, amount, ... }
    //   "draft_updated_by_offer" — full draft state update after a bid
    //     data: { type, status, settings, last_picked, ...,
    //             player_id, amount, bid_id, roster_id (current highest bidder) }
    //   "draft_picked"           — player sold / pick finalized
    //     data: { player_id, roster_id, amount, ... }

    if (!Array.isArray(msg) || msg.length < 4) return;

    const topic = msg[2];     // e.g. "draft:1329266100634584"
    const eventType = msg[3]; // e.g. "new_draft_offer"
    const data = msg[4];      // data object (may be undefined for some events)

    // Only process draft-related messages
    if (typeof topic !== "string" || !topic.startsWith("draft:")) return;

    console.log("[FAA] Sleeper WS event:", eventType, JSON.stringify(data).slice(0, 500));

    if (eventType === "new_draft_offer" && data) {
      // A new bid or nomination on a player
      const playerId = data.player_id != null ? String(data.player_id) : null;
      const amount = parseInt(data.amount, 10) || parseInt(data.metadata?.amount, 10) || 0;
      // Sleeper may put bidder in roster_id, bid_roster_id, or metadata.roster_id
      const rosterId = _extractRosterId(data);

      if (playerId) {
        // If this is a DIFFERENT player than current nomination, the previous was sold
        if (sleeperWsNomination && sleeperWsNomination.player_id !== playerId && sleeperWsLatestBid) {
          sleeperWsSoldQueue.push({
            player_id: sleeperWsNomination.player_id,
            playerName: sleeperWsNomination.playerName,
            amount: sleeperWsLatestBid.amount,
            bidder: sleeperWsLatestBid.bidder,
          });
          console.log("[FAA] WS detected sale:", sleeperWsNomination.playerName,
            "$" + sleeperWsLatestBid.amount, "to roster", sleeperWsLatestBid.bidder);
        }

        // New nomination (or first bid on same player)
        if (!sleeperWsNomination || sleeperWsNomination.player_id !== playerId) {
          sleeperWsNomination = {
            player_id: playerId,
            playerName: resolveSleeperPlayerName(data.player_id),
            nominatingTeamId: rosterId,
            amount: amount,
          };
        }
        // Always update latest bid
        sleeperWsLatestBid = {
          amount: amount,
          bidder: rosterId,
        };
      }
      return;
    }

    if (eventType === "draft_updated_by_offer" && data) {
      // Full draft state after a bid — this often has the current bid info
      const playerId = data.player_id != null ? String(data.player_id) : null;
      const amount = parseInt(data.amount, 10) || 0;
      const rosterId = _extractRosterId(data);

      if (playerId && amount > 0) {
        // If player changed, the previous nomination was sold
        if (sleeperWsNomination && sleeperWsNomination.player_id !== playerId && sleeperWsLatestBid) {
          sleeperWsSoldQueue.push({
            player_id: sleeperWsNomination.player_id,
            playerName: sleeperWsNomination.playerName,
            amount: sleeperWsLatestBid.amount,
            bidder: sleeperWsLatestBid.bidder,
          });
          console.log("[FAA] WS sale (via state update):", sleeperWsNomination.playerName,
            "$" + sleeperWsLatestBid.amount, "to roster", sleeperWsLatestBid.bidder);
        }

        if (!sleeperWsNomination || sleeperWsNomination.player_id !== playerId) {
          sleeperWsNomination = {
            player_id: playerId,
            playerName: resolveSleeperPlayerName(data.player_id),
            nominatingTeamId: rosterId,
            amount: amount,
          };
        }
        // Update bid — draft_updated_by_offer has authoritative bid state
        if (rosterId) {
          sleeperWsLatestBid = {
            amount: amount,
            bidder: rosterId,
          };
        }
      }
      return;
    }

    if (eventType === "draft_picked" && data) {
      // Player sold — pick finalized
      console.log("[FAA] Sleeper pick finalized:", data);
      // Record the sale if we had a nomination tracked
      if (sleeperWsNomination && sleeperWsLatestBid) {
        const soldPlayerId = data.player_id != null ? String(data.player_id) : sleeperWsNomination.player_id;
        const soldRosterId = _extractRosterId(data) || sleeperWsLatestBid.bidder;
        const soldAmount = parseInt(data.metadata?.amount, 10) || sleeperWsLatestBid.amount;
        sleeperWsSoldQueue.push({
          player_id: soldPlayerId,
          playerName: resolveSleeperPlayerName(soldPlayerId),
          amount: soldAmount,
          bidder: soldRosterId,
        });
        console.log("[FAA] WS pick sold:", resolveSleeperPlayerName(soldPlayerId), "$" + soldAmount);
      }
      sleeperWsNomination = null;
      sleeperWsLatestBid = null;
      return;
    }
  }

  function _extractRosterId(data) {
    // Sleeper uses various field names for the bidding roster
    let rid = data.roster_id ?? data.bid_roster_id ?? data.metadata?.roster_id ?? null;

    // If no roster_id, try to derive from slot + draft's slot_to_roster_id mapping
    if (rid == null && data.slot != null && sleeperDraftCache) {
      const slotMap = sleeperDraftCache.slot_to_roster_id || {};
      rid = slotMap[String(data.slot)] ?? slotMap[data.slot] ?? null;
    }

    return rid != null ? String(rid) : null;
  }

  function parseSleeperDraftId() {
    // URL pattern: /draft/nfl/<draft_id> or /draft/<draft_id>
    const match = window.location.pathname.match(/\/draft\/(?:\w+\/)?(\d+)/);
    return match ? match[1] : null;
  }

  async function loadSleeperPlayers() {
    if (sleeperPlayersCache || sleeperPlayersCacheLoading) return;
    sleeperPlayersCacheLoading = true;
    try {
      // Try to load from persisted cache via bridge first
      const cached = await requestCachedPlayers();
      if (cached && Object.keys(cached).length > 100) {
        sleeperPlayersCache = cached;
        console.log("[FAA] Sleeper player database loaded from cache:", Object.keys(cached).length, "players");
        sleeperPlayersCacheLoading = false;
        return;
      }

      // Fetch from API
      console.log("[FAA] Fetching Sleeper player database from API...");
      const resp = await fetch(`${SLEEPER_API_BASE}/players/nfl`);
      if (resp.ok) {
        sleeperPlayersCache = await resp.json();
        console.log("[FAA] Sleeper player database loaded:", Object.keys(sleeperPlayersCache).length, "players");
        // Persist via bridge for future page loads
        sendToBridge({ cacheSleeperPlayers: sleeperPlayersCache });
      }
    } catch (err) {
      console.error("[FAA] Failed to load Sleeper players:", err);
    } finally {
      sleeperPlayersCacheLoading = false;
    }
  }

  function requestCachedPlayers() {
    return new Promise((resolve) => {
      const handler = (event) => {
        if (event.source !== window) return;
        if (!event.data || event.data.type !== MESSAGE_TYPE) return;
        if (event.data.direction !== "from-bridge") return;
        if (event.data.payload?.cachedSleeperPlayers !== undefined) {
          window.removeEventListener("message", handler);
          resolve(event.data.payload.cachedSleeperPlayers);
        }
      };
      window.addEventListener("message", handler);
      sendToBridge({ requestSleeperPlayersCache: true });
      setTimeout(() => {
        window.removeEventListener("message", handler);
        resolve(null);
      }, 500);
    });
  }

  /**
   * Fetch league users and rosters to build roster_id → display_name mapping.
   * Returns a promise that resolves when loading is complete.
   */
  async function loadSleeperRosterNames(leagueId) {
    if (!leagueId || sleeperRosterNamesLoaded) return;
    if (sleeperRosterNamesLoading) {
      // Wait for the in-flight request to finish
      while (sleeperRosterNamesLoading) {
        await new Promise(r => setTimeout(r, 100));
      }
      return;
    }
    sleeperRosterNamesLoading = true;
    try {
      const [usersResp, rostersResp] = await Promise.all([
        fetch(`${SLEEPER_API_BASE}/league/${leagueId}/users`),
        fetch(`${SLEEPER_API_BASE}/league/${leagueId}/rosters`),
      ]);
      if (!usersResp.ok || !rostersResp.ok) return;

      const users = await usersResp.json();
      const rosters = await rostersResp.json();

      // Store raw rosters for team building
      sleeperLeagueRosters = rosters;

      // Build user_id → display_name
      const userNames = {};
      for (const u of users) {
        userNames[u.user_id] = u.display_name || u.username || `User ${u.user_id}`;
      }

      // Build roster_id → display_name via roster.owner_id, co_owners, or metadata
      for (const r of rosters) {
        const rid = String(r.roster_id);
        // Try owner first
        let name = userNames[r.owner_id];
        // Try co_owners if no owner
        if (!name && r.co_owners && r.co_owners.length > 0) {
          name = userNames[r.co_owners[0]];
        }
        // Try roster metadata for custom team name
        if (!name && r.metadata && r.metadata.team_name) {
          name = r.metadata.team_name;
        }
        sleeperRosterNames[rid] = name || `Team ${rid}`;
      }

      sleeperRosterNamesLoaded = true;
      console.log("[FAA] Sleeper roster names loaded:", sleeperRosterNames);
    } catch (err) {
      console.error("[FAA] Failed to load Sleeper roster names:", err);
    } finally {
      sleeperRosterNamesLoading = false;
    }
  }

  function resolveSleeperRosterName(rosterId) {
    if (!rosterId) return null;
    return sleeperRosterNames[String(rosterId)] || `Team ${rosterId}`;
  }

  function resolveSleeperPlayerName(playerId) {
    if (!sleeperPlayersCache || !playerId) return `Player #${playerId}`;
    const p = sleeperPlayersCache[String(playerId)];
    if (!p) return `Player #${playerId}`;
    return p.full_name || `${p.first_name || ""} ${p.last_name || ""}`.trim() || `Player #${playerId}`;
  }

  function resolveSleeperPlayerPosition(playerId) {
    if (!sleeperPlayersCache || !playerId) return "UNK";
    const p = sleeperPlayersCache[String(playerId)];
    return p ? (p.position || "UNK") : "UNK";
  }

  async function sleeperExtract() {
    const draftId = parseSleeperDraftId();
    if (!draftId) return null;

    // Start loading player DB in background on first call
    loadSleeperPlayers();

    try {
      // Fetch draft metadata and picks in parallel
      const [draftResp, picksResp] = await Promise.all([
        fetch(`${SLEEPER_API_BASE}/draft/${draftId}`),
        fetch(`${SLEEPER_API_BASE}/draft/${draftId}/picks`),
      ]);

      if (!draftResp.ok || !picksResp.ok) return null;

      const draft = await draftResp.json();
      const picks = await picksResp.json();

      sleeperDraftCache = draft;
      sleeperPicksCache = picks;

      // Log first pick shape for debugging roster_id resolution
      if (picks.length > 0 && !window._faaPickLogged) {
        window._faaPickLogged = true;
        console.log("[FAA] Sleeper pick sample:", JSON.stringify(picks[0]));
        console.log("[FAA] Sleeper draft.slot_to_roster_id:", draft.slot_to_roster_id);
        console.log("[FAA] Sleeper draft.draft_order:", draft.draft_order);
      }

      // Load roster names from league (once) — await so names are ready for payload
      if (draft.league_id) {
        await loadSleeperRosterNames(draft.league_id);
      }

      return buildSleeperPayload(draft, picks, draftId);
    } catch (err) {
      console.error("[FAA] Sleeper API fetch error:", err);
      return null;
    }
  }

  function buildSleeperPayload(draft, picks, draftId) {
    const draftSettings = draft.settings || {};
    const budget = draftSettings.budget || 200;

    // Helper: resolve a pick's roster_id using multiple fallbacks
    function resolvePickRosterId(pick) {
      if (pick.roster_id != null) return String(pick.roster_id);
      // Fallback: slot_to_roster_id
      if (pick.draft_slot != null) {
        const slotMap = draft.slot_to_roster_id || {};
        const mapped = slotMap[String(pick.draft_slot)] ?? slotMap[pick.draft_slot];
        if (mapped != null) return String(mapped);
      }
      // Fallback: picked_by (user_id) → roster
      if (pick.picked_by && sleeperLeagueRosters.length > 0) {
        const match = sleeperLeagueRosters.find(r => r.owner_id === pick.picked_by);
        if (match) return String(match.roster_id);
      }
      return null;
    }

    // Build per-roster spending from completed picks
    const rosterSpending = {}; // roster_id -> total spent
    const rosterPicks = {};    // roster_id -> [picks]
    for (const pick of picks) {
      const rid = resolvePickRosterId(pick);
      if (!rid) continue;  // Skip picks with unresolvable roster
      const amount = pick.metadata ? parseInt(pick.metadata.amount, 10) || 0 : 0;
      rosterSpending[rid] = (rosterSpending[rid] || 0) + amount;
      if (!rosterPicks[rid]) rosterPicks[rid] = [];
      rosterPicks[rid].push(pick);
    }
    // Include WS-detected sales not yet in REST picks
    const restPlayerIds = new Set(picks.filter(p => p.player_id).map(p => String(p.player_id)));
    for (const sold of sleeperWsSoldQueue) {
      if (!restPlayerIds.has(sold.player_id) && sold.bidder) {
        const rid = sold.bidder;
        rosterSpending[rid] = (rosterSpending[rid] || 0) + (sold.amount || 0);
      }
    }

    // Build teams — merge all sources to ensure every roster slot is covered.
    // Sources: league rosters API, slot_to_roster_id, draft_order, and picks.
    const teams = [];
    const seenRosters = new Set();

    function addTeam(rid) {
      rid = String(rid);
      if (seenRosters.has(rid)) return;
      seenRosters.add(rid);
      const spent = rosterSpending[rid] || 0;
      const teamPicks = rosterPicks[rid] || [];
      teams.push({
        teamId: rid,
        name: resolveSleeperRosterName(rid),
        abbrev: null,
        totalBudget: budget,
        remainingBudget: budget - spent,
        rosterSize: teamPicks.length,
      });
    }

    // 1) League rosters API (has all human-owned rosters)
    for (const r of sleeperLeagueRosters) {
      addTeam(r.roster_id);
    }

    // 2) slot_to_roster_id from draft metadata (maps every draft slot to a roster)
    const slotMap = draft.slot_to_roster_id || {};
    for (const rid of Object.values(slotMap)) {
      addTeam(rid);
    }

    // 3) draft_order (may have additional mappings)
    const draftOrder = draft.draft_order || {};
    for (const rid of Object.values(draftOrder)) {
      addTeam(rid);
    }

    // 4) Any roster_id seen in picks that we haven't covered yet
    for (const rid of Object.keys(rosterSpending)) {
      addTeam(rid);
    }

    // Build draft log from completed picks (REST API)
    const draftLog = picks
      .filter(p => p.player_id)
      .map(p => ({
        playerId: String(p.player_id),
        playerName: resolveSleeperPlayerName(p.player_id),
        teamId: resolvePickRosterId(p),
        bidAmount: p.metadata ? parseInt(p.metadata.amount, 10) || 0 : 0,
        keeper: p.is_keeper || false,
      }));

    // Merge WS-detected sales that REST hasn't picked up yet
    const restDraftedIds = new Set(draftLog.map(d => d.playerId));
    for (const sold of sleeperWsSoldQueue) {
      if (!restDraftedIds.has(sold.player_id)) {
        draftLog.push({
          playerId: sold.player_id,
          playerName: sold.playerName,
          teamId: sold.bidder, // roster_id of winning bidder
          bidAmount: sold.amount,
          keeper: false,
        });
      }
    }
    // Clean up: remove from queue once REST has caught up
    sleeperWsSoldQueue = sleeperWsSoldQueue.filter(
      s => !restDraftedIds.has(s.player_id)
    );

    // Build rosters from picks (position = player's position from DB)
    const rosters = {};
    for (const [rid, teamPicks] of Object.entries(rosterPicks)) {
      rosters[rid] = teamPicks.map(p => ({
        playerId: String(p.player_id),
        playerName: resolveSleeperPlayerName(p.player_id),
        position: resolveSleeperPlayerPosition(p.player_id),
        acquisitionType: "DRAFT",
      }));
    }

    // Current nomination from WebSocket interceptor (real-time)
    let currentNomination = null;
    let currentBid = null;
    let highBidder = null;

    if (sleeperWsNomination) {
      currentNomination = {
        playerId: sleeperWsNomination.player_id,
        playerName: sleeperWsNomination.playerName,
        // Send roster_id as nominatingTeamId — backend resolves via teams list
        nominatingTeamId: sleeperWsNomination.nominatingTeamId,
      };
      // Also set highBidder for initial nomination if no separate bid yet
      if (!sleeperWsLatestBid && sleeperWsNomination.nominatingTeamId) {
        highBidder = resolveSleeperRosterName(sleeperWsNomination.nominatingTeamId);
        currentBid = sleeperWsNomination.amount;
      }
      if (sleeperWsLatestBid) {
        currentBid = sleeperWsLatestBid.amount;
        // Resolve bidder roster_id to display name
        highBidder = resolveSleeperRosterName(sleeperWsLatestBid.bidder);
      }
    }

    const payload = {
      timestamp: Date.now(),
      currentNomination,
      currentBid,
      highBidder,
      teams,
      draftLog,
      rosters,
      sport: detectSport(),
      platform: "sleeper",
      source: "sleeper-api",
    };

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
        <span id="faa-strategy" style="font-size:10px;color:#8899aa;margin-left:4px"></span>
        <span id="faa-status" class="faa-disconnected">&#x25CF;</span>
        <button id="faa-minimize">_</button>
      </div>
      <div id="faa-compact" style="display:none">
        <div id="faa-compact-line"></div>
      </div>
      <div id="faa-body">
        <div id="faa-nomination"></div>
        <div id="faa-bid-info"></div>
        <div id="faa-advice">Waiting for draft data...</div>
        <div id="faa-ai-reasoning"></div>
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

  function applyOverlayPosition(position) {
    if (!overlayElement) return;
    // Reset all corner positions
    overlayElement.style.top = "auto";
    overlayElement.style.right = "auto";
    overlayElement.style.bottom = "auto";
    overlayElement.style.left = "auto";

    switch (position) {
      case "top-left":
        overlayElement.style.top = "10px";
        overlayElement.style.left = "10px";
        break;
      case "bottom-right":
        overlayElement.style.bottom = "10px";
        overlayElement.style.right = "10px";
        break;
      case "bottom-left":
        overlayElement.style.bottom = "10px";
        overlayElement.style.left = "10px";
        break;
      case "top-right":
      default:
        overlayElement.style.top = "10px";
        overlayElement.style.right = "10px";
        break;
    }
  }

  function applyInlineStyles() {
    const el = overlayElement;
    el.style.cssText = `
      position: fixed; top: 10px; right: 10px; width: 340px;
      max-height: 460px; background: #1a1a2e; color: #e0e0e0;
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
    title.style.cssText = "font-weight: 600; font-size: 14px; color: #e94560;";

    const strategy = el.querySelector("#faa-strategy");
    strategy.style.cssText = "flex: 1; font-size: 10px; color: #8899aa; margin-left: 4px;";

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
    body.style.cssText = "padding: 10px 12px; overflow-y: auto; max-height: 400px;";

    // Nomination — top of body, prominent
    const nom = el.querySelector("#faa-nomination");
    nom.style.cssText = `
      padding: 6px 8px; font-weight: 600; color: #e94560; font-size: 14px;
      background: #12203a; border-radius: 6px; margin-bottom: 4px;
    `;

    // Bid info — right below nomination
    const bid = el.querySelector("#faa-bid-info");
    bid.style.cssText = `
      padding: 3px 8px; color: #aaa; font-size: 12px; margin-bottom: 6px;
    `;

    // Advice — main action block
    const advice = el.querySelector("#faa-advice");
    advice.style.cssText = `
      padding: 8px 10px; background: #0f3460; border-radius: 6px;
      margin-bottom: 6px; line-height: 1.5; white-space: pre-wrap;
    `;

    // AI reasoning section
    const aiReasoning = el.querySelector("#faa-ai-reasoning");
    aiReasoning.style.cssText = `
      padding: 6px 8px; margin-bottom: 6px; background: #12203a;
      border-radius: 4px; font-size: 11px; color: #8899aa;
      line-height: 1.4; white-space: pre-wrap; display: none;
      max-height: 70px; overflow-y: auto;
    `;

    // Ticker section — compact
    const tickerEl = el.querySelector("#faa-ticker");
    tickerEl.style.cssText = `
      padding: 6px 8px; background: #12203a;
      border-radius: 4px; font-size: 10px; color: #aaa; line-height: 1.4;
      max-height: 70px; overflow-y: auto;
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
      el.style.bottom = "auto";
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
      // Debug: dump Sleeper WebSocket messages to overlay
      if (cmd.toLowerCase() === "debug ws") {
        const msgs = sleeperWsMessages || [];
        const nom = sleeperWsNomination;
        const bid = sleeperWsLatestBid;
        let html = `<b style="color:#2196f3">Sleeper WS Debug</b><br>`;
        html += `WS Connected: ${sleeperWsConnected}<br>`;
        html += `Nomination: ${nom ? JSON.stringify(nom) : 'null'}<br>`;
        html += `Latest bid: ${bid ? JSON.stringify(bid) : 'null'}<br>`;
        html += `Last ${msgs.length} messages:<br>`;
        msgs.slice(-5).forEach((m, i) => {
          // For array messages, show event type and data separately for readability
          if (Array.isArray(m) && m.length >= 4) {
            const evtType = m[3] || "?";
            const evtData = m[4] ? JSON.stringify(m[4]).slice(0, 500) : "null";
            html += `<span style="font-size:10px;color:#888">[${evtType}] ${evtData}</span><br>`;
          } else {
            html += `<span style="font-size:10px;color:#888">${JSON.stringify(m).slice(0, 200)}</span><br>`;
          }
        });
        updateOverlayAdvice(html);
        console.log("[FAA] WS debug — all messages:", msgs);
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
      // Stop the draft page from capturing keystrokes while typing
      e.stopPropagation();
    });
    // Also stop keyup/keypress from bubbling to the draft page
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
      const bidderLabel = payload.highBidder || "?";
      bidEl.textContent = `Current bid: $${payload.currentBid} (${bidderLabel})`;
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
    if (p.overlayPosition) applyOverlayPosition(p.overlayPosition);

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

      // Live ticker
      if (raw.tickerEvents) {
        updateTickerDisplay(raw.tickerEvents);
      }

      // Strategy label
      if (raw.strategyLabel) {
        const stratEl = document.getElementById("faa-strategy");
        if (stratEl) stratEl.textContent = raw.strategyLabel;
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

      MARKET_SHIFT: "#e94560",
    };
    const TYPE_ICONS = {
      NEW_NOMINATION: "\u{1F4E2}",
      BID_PLACED: "\u{1F4B5}",
      PLAYER_SOLD: "\u2705",
      BUDGET_ALERT: "\u26A0\uFE0F",

      MARKET_SHIFT: "\u{1F4C8}",
    };
    // Events arrive in chronological order (oldest first) — newest at bottom like a chat
    const html = events.slice(-8).map(e => {
      const color = TYPE_COLORS[e.event_type] || "#aaa";
      const icon = TYPE_ICONS[e.event_type] || "";
      return `<div style="color:${color};padding:1px 0">${icon} ${e.message}</div>`;
    }).join("");
    el.innerHTML = `<div style="font-weight:600;color:#e94560;margin-bottom:2px;font-size:10px">LIVE TICKER</div>` + html;
    // Auto-scroll to newest (bottom)
    el.scrollTop = el.scrollHeight;
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

  /**
   * ESPN extraction: React fiber traversal → payload builder → DOM fallback
   */
  function espnExtract() {
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
      payload.platform = "espn";

      // One-time debug dump
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
        payload._debug = {
          draftDetailKeys: Object.keys(rawData.draftDetail),
          firstTeamKeys: rawData.teams && rawData.teams[0]
            ? Object.keys(rawData.teams[0])
            : [],
        };
      }
    } else {
      payload = scrapeDOMFallback();
      payload.platform = "espn";
    }

    return payload;
  }

  function poll() {
    if (PLATFORM === "sleeper") {
      // Sleeper: async API-based extraction
      sleeperExtract().then(payload => {
        if (!payload) return;

        updateOverlayNomination(payload);

        const hash = hashPayload(payload);
        if (hash !== lastDataHash) {
          lastDataHash = hash;
          sendToBridge(payload);
        }
      }).catch(err => {
        console.error("[Fantasy Auction Assistant] Sleeper poll error:", err);
        updateOverlayStatus(false);
      });
    } else {
      // ESPN: synchronous React fiber / DOM extraction
      try {
        const payload = espnExtract();

        updateOverlayNomination(payload);

        const hash = hashPayload(payload);
        if (hash !== lastDataHash) {
          lastDataHash = hash;
          sendToBridge(payload);
        }
      } catch (err) {
        console.error("[Fantasy Auction Assistant] ESPN poll error:", err);
        updateOverlayStatus(false);
      }
    }
  }

  // =========================================================
  // SECTION 7: Init
  // =========================================================

  function init() {
    console.log(`[Fantasy Auction Assistant] Content script loaded (MAIN world) — platform: ${PLATFORM}`);
    createOverlay();

    // For Sleeper, start loading the player database
    if (PLATFORM === "sleeper") {
      loadSleeperPlayers();
    }

    setInterval(poll, POLL_INTERVAL_MS);
    // Request CSS URL and overlay position from bridge
    sendToBridge({ requestCSS: true });
    sendToBridge({ requestOverlayPosition: true });
  }

  // For Sleeper (document_start), the WebSocket interceptor is already installed above.
  // Defer DOM-dependent init until the page is ready.
  if (document.readyState === "complete" || document.readyState === "interactive") {
    init();
  } else {
    // On document_start, wait for DOMContentLoaded before creating overlay/polling
    document.addEventListener("DOMContentLoaded", init);
  }
})();
