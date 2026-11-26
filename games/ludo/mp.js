// ---------------------------------------------------------------------------
// Khelo Ludo - rooms over Firebase Realtime Database
//
// Paste your Firebase project config below (Firebase console -> Project
// settings -> Your apps -> Web app -> Config). SETUP.md has the rest.
// ---------------------------------------------------------------------------

export const FIREBASE_CONFIG = {
  apiKey: "AIzaSyCnlICK4v4E9-mqUVcguzIn2LaIfI_D7G8",
  authDomain: "khelo-1bfaa.firebaseapp.com",
  databaseURL: "https://khelo-1bfaa-default-rtdb.asia-southeast1.firebasedatabase.app",
  projectId: "khelo-1bfaa",
  storageBucket: "khelo-1bfaa.firebasestorage.app",
  messagingSenderId: "606000164368",
  appId: "1:606000164368:web:dbba92dc91d3e846662495"
};

const SDK = "https://www.gstatic.com/firebasejs/10.12.2";
const ROOM_MAX_AGE = 3 * 60 * 60 * 1000;      // rooms older than this are junk

export function configured() {
  return !String(FIREBASE_CONFIG.apiKey).startsWith("PASTE");
}

let db = null, api = null, uid = null, room = null;
let stateRef = null, playersRef = null, metaRef = null, actionsRef = null;
let unsubPlayers = null, unsubMeta = null, unsubActions = null;
let isHost = false, hostId = "";
let lastPush = 0;

export const me = () => uid;
export const roomCode = () => room;
export const hosting = () => isHost;
export const host = () => hostId;

function randomId(n) {
  const a = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  let s = "";
  for (let i = 0; i < n; i++) s += a[Math.floor(Math.random() * a.length)];
  return s;
}

async function load() {
  if (db) return;
  let appMod, dbMod;
  try {
    appMod = await import(`${SDK}/firebase-app.js`);
    dbMod = await import(`${SDK}/firebase-database.js`);
  } catch (e) {
    throw new Error("Firebase could not be loaded. Check your internet " +
                    "connection, then try again.");
  }
  const app = appMod.initializeApp(FIREBASE_CONFIG);
  db = dbMod.getDatabase(app);
  api = dbMod;
  uid = randomId(6);
}

function explain(err) {
  const msg = String((err && err.message) || err);
  if (msg.indexOf("PERMISSION_DENIED") >= 0) {
    return new Error("The database is refusing writes. In Firebase open " +
      "Realtime Database -> Rules and allow .read and .write (test mode).");
  }
  if (msg.indexOf("does not exist") >= 0 || msg.indexOf("not found") >= 0) {
    return new Error("This project has no Realtime Database yet. Open Firebase " +
      "-> Realtime Database -> Create Database.");
  }
  return new Error("Cannot reach the database. Check databaseURL in mp.js. (" +
                   msg + ")");
}

// Old rooms pile up because nobody deletes them. Clear out the stale ones
// whenever a new room is made.
async function sweepOldRooms() {
  try {
    const snap = await api.get(api.ref(db, "rooms"));
    if (!snap.exists()) return;
    const now = Date.now();
    const jobs = [];
    snap.forEach((child) => {
      const meta = (child.val() || {}).meta || {};
      const at = typeof meta.at === "number" ? meta.at : 0;
      if (at && now - at > ROOM_MAX_AGE) {
        jobs.push(api.remove(child.ref));
      }
    });
    await Promise.all(jobs);
  } catch (e) {
    // a failed sweep is not worth bothering the player about
  }
}

export async function enter(code, name) {
  await load();
  const wanted = String(code || "").trim().toUpperCase();

  if (wanted) {
    const snap = await api.get(api.ref(db, `rooms/${wanted}/meta`));
    if (!snap.exists()) throw new Error("No room called " + wanted);
    room = wanted;
    isHost = false;
    hostId = String((snap.val() || {}).host || "");
  } else {
    // pick a code nobody is using
    for (let attempt = 0; attempt < 6; attempt++) {
      const candidate = randomId(5);
      const taken = await api.get(api.ref(db, `rooms/${candidate}/meta`));
      if (taken.exists()) continue;
      room = candidate;
      break;
    }
    if (!room) throw new Error("Could not find a free room code. Try again.");
    isHost = true;
    hostId = uid;
    await sweepOldRooms();
    await api.set(api.ref(db, `rooms/${room}/meta`), {
      host: uid, state: "lobby", at: Date.now()
    });
  }

  playersRef = api.ref(db, `rooms/${room}/players`);
  stateRef = api.ref(db, `rooms/${room}/players/${uid}`);
  metaRef = api.ref(db, `rooms/${room}/meta`);
  actionsRef = api.ref(db, `rooms/${room}/actions`);

  // onDisconnect has to be armed BEFORE we appear, or a crash in between
  // leaves a ghost player that nobody can clear
  try {
    await api.onDisconnect(stateRef).remove();
  } catch (e) {
    // not fatal - the player just lingers if they drop
  }

  try {
    await api.set(stateRef, {
      name: (name || "Player").slice(0, 12),
      seat: -1, connected: 1, joined: Date.now()
    });
  } catch (err) {
    throw explain(err);
  }
  return room;
}

export function watchPlayers(cb) {
  if (!playersRef) return;
  unsubPlayers = api.onValue(playersRef, (snap) => {
    const out = [];
    snap.forEach((child) => {
      const v = child.val() || {};
      out.push({
        id: child.key,
        name: v.name || "Player",
        seat: typeof v.seat === "number" ? v.seat : -1,
        connected: !!v.connected,
        joined: +v.joined || 0
      });
    });
    cb(out);
  });
}

export function watchMeta(cb) {
  if (!metaRef) return;
  unsubMeta = api.onValue(metaRef, (snap) => {
    const v = snap.val() || {};
    if (v.host) hostId = String(v.host);
    cb(v);
  });
}

// A guest cannot run the game, so it asks the host to roll or move for it.
export function sendAction(payload) {
  if (!actionsRef) return;
  const r = api.push(actionsRef);
  api.set(r, { payload: String(payload), from: uid, at: Date.now() });
}

// The host picks those up, applies them, and clears them away.
export function watchActions(cb) {
  if (!actionsRef) return;
  unsubActions = api.onValue(actionsRef, (snap) => {
    snap.forEach((child) => {
      const v = child.val() || {};
      if (v.payload) cb(String(v.payload));
      api.remove(child.ref);
    });
  });
}

export function publishMeta(m) {
  if (!metaRef || !isHost) return;
  api.update(metaRef, m);
}

export function setRoomState(s) {
  publishMeta({ state: s });
}

export function pushState(s) {
  if (!stateRef) return;
  const now = Date.now();
  if (now - lastPush < 95) return;
  lastPush = now;
  api.update(stateRef, { t: now });
}

export async function leave() {
  if (unsubPlayers) { unsubPlayers(); unsubPlayers = null; }
  if (unsubMeta) { unsubMeta(); unsubMeta = null; }
  if (unsubActions) { unsubActions(); unsubActions = null; }
  try {
    if (stateRef) {
      await api.onDisconnect(stateRef).cancel();
      await api.remove(stateRef);
    }
    // the host tidies the whole room away on the way out
    if (isHost && metaRef) await api.remove(api.ref(db, `rooms/${room}`));
  } catch (e) {}
  db = null; api = null; room = null; stateRef = null;
  playersRef = null; metaRef = null; actionsRef = null;
  isHost = false; hostId = "";
}
