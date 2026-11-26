# Play with friends — Firebase setup

The game is a static site, so the only thing that makes multiplayer work is a
small free Firebase project. It takes about five minutes.

## 1. Create the project

1. Go to <https://console.firebase.google.com> and sign in with a Google account.
2. **Add project** → give it a name (e.g. `khelo-battle`) → you can turn
   Google Analytics off → **Create project**.

## 2. Turn on the Realtime Database

1. In the left menu open **Build → Realtime Database** → **Create Database**.
2. Pick a location (Singapore or Mumbai are closest to India).
3. Start in **test mode** (you will tighten it in step 4).

## 3. Copy your web config

1. Click the **⚙️ → Project settings** gear.
2. Scroll to **Your apps** → click the **</>** (Web) icon → register the app
   (nickname `khelo`, no hosting needed).
3. Copy the `firebaseConfig` object it shows you.

Open `games/battle/mp.js` and replace the placeholder values at the top:

```js
export const FIREBASE_CONFIG = {
  apiKey: "AIza...",
  authDomain: "khelo-battle.firebaseapp.com",
  databaseURL: "https://khelo-battle-default-rtdb.asia-southeast1.firebasedatabase.app",
  projectId: "khelo-battle",
  storageBucket: "khelo-battle.appspot.com",
  messagingSenderId: "1234567890",
  appId: "1:1234:web:abcd"
};
```

`databaseURL` is the one that matters most — if it is missing, realtime will
not connect. You can copy it from the Realtime Database page.

## 4. Database rules

In **Realtime Database → Rules**, paste this. It keeps rooms open for a few
minutes but stops the database from being wide open:

```json
{
  "rules": {
    "rooms": {
      "$room": {
        ".read": true,
        ".write": true,
        "players": { "$pid": { ".validate": "newData.hasChildren(['x','z','hp'])" } }
      }
    }
  }
}
```

Anyone who knows a room code can join that room. Do not use this for anything
private — it is meant for playing with friends.

## 5. Play

1. Open the game, tap the 👥 button in the top bar.
2. **Create a room** → you get a five-letter code.
3. A friend opens the same page, taps 👥, types the code, **Join**.
4. Everyone starts on the same map, no bots, last one standing wins.

## What is shared and what is not

| Thing | How it stays in step |
|---|---|
| The map, towns, trees | Not sent at all — every device builds the same map from the same seeds |
| Your position and health | You send yours ~10 times a second; your health is yours alone |
| Damage | The shooter reports a hit; the person hit applies it to themselves |
| The blue circle | The room host sends it; everyone else follows |

## Limits

- Works best with 2–8 players. The free tier allows far more traffic than that.
- The host leaving ends the circle updates for the others.
- There is no anti-cheat: a modified client could lie about its own health.
