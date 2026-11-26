// ---------------------------------------------------------------------------
// Khelo Ludo - multiplayer over Firebase Realtime Database
//
// This is the only file you need to touch to go online. Paste your own
// Firebase project config below (Firebase console -> Project settings ->
// Your apps -> Web app -> Config), then turn on Realtime Database in the
// console and paste the rules from SETUP.md.
//
// Nothing here runs until someone taps "PLAY WITH FRIENDS", and if the config
// is left blank the button simply says so - single player never breaks.
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

export function configured() {
  return !String(FIREBASE_CONFIG.apiKey).startsWith("PASTE");
}

let db = null, api = null, uid = null, room = null;
let stateRef = null, playersRef = null, hitsRef = null, metaRef = null;
let unsubPlayers = null, unsubHits = null, unsubMeta = null;
let lastPush = 0;
let isHost = false;

export const me = () => uid;
export const roomCode = () => room;
export const hosting = () => isHost;

function randomId(n) {
  const a = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  let s = "";
  for (let i = 0; i < n; i++) s += a[Math.floor(Math.random() * a.length)];
  return s;
}

async function load() {
  if (db) return;
  const appMod = await import(`${SDK}/firebase-app.js`);
  const dbMod = await import(`${SDK}/firebase-database.js`);
  const app = appMod.initializeApp(FIREBASE_CONFIG);
  db = dbMod.getDatabase(app);
  api = dbMod;
  uid = randomId(6);
}

// Create a room, or join one that already exists. Resolves to the code.
export async function enter(code, name) {
  await load();
  const wanted = String(code || "").trim().toUpperCase();
  if (wanted) {
    const snap = await api.get(api.ref(db, `rooms/${wanted}/meta`));
    if (!snap.exists()) throw new Error("No room called " + wanted);
    room = wanted;
    isHost = false;
  } else {
    room = randomId(5);
    isHost = true;
    await api.set(api.ref(db, `rooms/${room}/meta`), {
      host: uid,
      state: "lobby",
      at: api.serverTimestamp()
    });
  }

  playersRef = api.ref(db, `rooms/${room}/players`);
  stateRef = api.ref(db, `rooms/${room}/players/${uid}`);
  hitsRef = api.ref(db, `rooms/${room}/hits`);
  metaRef = api.ref(db, `rooms/${room}/meta`);

  try {
    await api.set(stateRef, {
      name: (name || "Player").slice(0, 12),
      x: 0, z: 0, y: 0, yaw: 0, hp: 100, alive: 1, weapon: 0, kills: 0,
      mode: "plane", t: Date.now()
    });
  } catch (err) {
    // say plainly what went wrong, instead of a raw Firebase code
    const msg = String((err && err.message) || err);
    if (msg.indexOf("PERMISSION_DENIED") >= 0) {
      throw new Error("Database rules are blocking writes. In Firebase, open "
        + "Realtime Database -> Rules and set \".read\": true, \".write\": true "
        + "(test mode).");
    }
    if (msg.indexOf("does not exist") >= 0 || msg.indexOf("not found") >= 0) {
      throw new Error("No Realtime Database in this project yet. Open Firebase "
        + "-> Realtime Database -> Create Database.");
    }
    throw new Error("Cannot reach the database. Check databaseURL in mp.js. ("
      + msg + ")");
  }
  // a player who closes the tab leaves the room
  api.onDisconnect(stateRef).remove();

  return room;
}

// Push our own position. Throttled by the caller, ~10 times a second.
export function pushState(s) {
  if (!stateRef) return;
  const now = Date.now();
  if (now - lastPush < 95) return;
  lastPush = now;
  api.update(stateRef, {
    x: Math.round(s.x * 10) / 10,
    z: Math.round(s.z * 10) / 10,
    y: Math.round(s.y * 10) / 10,
    yaw: Math.round(s.yaw * 100) / 100,
    hp: Math.round(s.hp),
    alive: s.alive ? 1 : 0,
    weapon: s.weapon | 0,
    kills: s.kills | 0,
    fs: s.fs | 0,
    mode: s.mode || "play",
    t: now
  });
}

// Everyone else in the room. Called with an array, minus ourselves.
export function watchPlayers(cb) {
  if (!playersRef) return;
  unsubPlayers = api.onValue(playersRef, (snap) => {
    const out = [];
    snap.forEach((child) => {
      if (child.key === uid) return;
      const v = child.val() || {};
      out.push({
        id: child.key,
        name: v.name || "Player",
        x: +v.x || 0, z: +v.z || 0, y: +v.y || 0, yaw: +v.yaw || 0,
        hp: v.hp == null ? 100 : +v.hp,
        alive: !!v.alive,
        weapon: v.weapon | 0,
        kills: v.kills | 0,
        fs: v.fs | 0,
        mode: v.mode || "play",
        t: +v.t || 0
      });
    });
    cb(out);
  });
}

// I shot someone. They apply it to themselves, so nobody can fake my health.
export function reportHit(targetId, dmg) {
  if (!hitsRef || !targetId) return;
  const r = api.push(hitsRef);
  api.set(r, { from: uid, to: targetId, dmg: dmg, at: Date.now() });
  api.set(api.ref(db, `rooms/${room}/hits/${r.key}/at`), Date.now());
}

// Damage meant for me. The sender cleans up after themselves.
export function watchHits(cb) {
  if (!hitsRef) return;
  unsubHits = api.onValue(hitsRef, (snap) => {
    snap.forEach((child) => {
      const v = child.val() || {};
      if (v.to !== uid) return;
      cb({ from: v.from, dmg: +v.dmg || 0 });
      api.remove(child.ref);
    });
  });
}

// The host drives the circle so everybody is inside the same one.
export function publishMeta(m) {
  if (!metaRef || !isHost) return;
  api.update(metaRef, m);
}

export function watchMeta(cb) {
  if (!metaRef) return;
  unsubMeta = api.onValue(metaRef, (snap) => {
    const v = snap.val() || {};
    cb(v);
  });
}

export function setRoomState(s) {
  if (metaRef && isHost) api.update(metaRef, { state: s });
}

export async function leave() {
  if (unsubPlayers) { unsubPlayers(); unsubPlayers = null; }
  if (unsubHits) { unsubHits(); unsubHits = null; }
  if (unsubMeta) { unsubMeta(); unsubMeta = null; }
  if (stateRef) { try { await api.remove(stateRef); } catch (e) {} }
  db = null; api = null; room = null; stateRef = null;
  playersRef = null; hitsRef = null; metaRef = null;
  isHost = false;
}
