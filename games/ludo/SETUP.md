# Ludo with friends - one time setup

The game already points at a Firebase project. If you want your own, or the
room buttons show an error, do this once.

## 1. Make the database

1. Open [Firebase console](https://console.firebase.google.com/) and pick your
   project (or make one).
2. **Build -> Realtime Database -> Create Database**, pick a region near you,
   and start in **test mode**.
3. Copy the config from **Project settings -> Your apps -> Web app** into
   `FIREBASE_CONFIG` at the top of `mp.js`.

## 2. Paste the rules

**Realtime Database -> Rules**, replace everything with the contents of
`database.rules.json` in this folder, and press **Publish**.

What they do:

- **Only signed-in clients** can read a room, so a random script cannot
  list every game in progress.
- **A player may only write their own entry** under `players/`, and the host
  may clear anyone's - that is how a disconnected player is removed.
- **Payloads are size-capped**, so nobody can dump a huge blob into your
  database and run up your bill.
- **A room can be created by anyone**, but only its host may rewrite the room
  as a whole (including deleting it when they leave).

## 3. Turn on anonymous sign-in

**Build -> Authentication -> Get started -> Sign-in method -> Anonymous ->
Enable.**

This gives every player a stable id. Without it the game still works, but it
falls back to a random id that changes on every reload, so a player who
refreshes cannot get their old seat back.

## What is still open

These rules cannot stop a determined player from writing a false board to a
room they are in - that needs a server (a Cloud Function) to run the game, and
this game runs entirely in the browser to stay free. For a game between
friends this is fine. Do not put anything private in a room.
