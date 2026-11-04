# Elevare Workforce OS desktop app

A desktop window (Electron) around the live web app. It opens the production
site by default, so a website deploy updates the desktop app too.

## Run it

```
cd desktop
npm install
npm start          # opens https://workforceos.online
npm run dev        # opens http://localhost:3000 (run the web app first)
```

To test a preview deploy: `set WOS_URL=https://your-preview.vercel.app` (Windows
PowerShell: `$env:WOS_URL="https://your-preview.vercel.app"`), then `npm start`.

## Build a Windows installer

```
npm run dist
```

The installer is written to `desktop/dist/`.

## What it does

- Opens the web app in its own window, one copy at a time.
- Links to other websites open in the normal browser.
- Shows an offline page with a Try again button when there is no connection.
- The web app gets no access to Node or the computer's files (context isolation
  and sandbox are on). `preload.js` only tells the web app it is running on
  desktop (`window.wosDesktop.isDesktop`).

## Not done yet

- Code signing (without it Windows shows a "unknown publisher" warning).
- Auto-update, tray icon and native notifications.
- macOS and Linux installers.
