// Elevare Workforce OS desktop app.
//
// This is a window around the live web app, so the desktop app and the website
// are always the same product and a website deploy updates both. Everything the
// app does still goes through the website's own sign-in and the same API.

const { app, BrowserWindow, shell, Menu } = require("electron/main");
const path = require("node:path");

const PRODUCTION_URL = "https://workforceos.online";
const DEV_URL = "http://localhost:3000";

// `npm run dev` points the window at a locally running `npm run dev` of the
// web app. WOS_URL overrides both, which is handy for testing a preview deploy.
const isDev = process.argv.includes("--dev");
const START_URL = process.env.WOS_URL || (isDev ? DEV_URL : PRODUCTION_URL);
const APP_ORIGIN = new URL(START_URL).origin;

let mainWindow = null;

function isAppUrl(url) {
  try {
    return new URL(url).origin === APP_ORIGIN;
  } catch {
    return false;
  }
}

function openExternally(url) {
  // Only web links go to the person's browser; anything else (file:, custom
  // protocols) is ignored on purpose.
  try {
    const parsed = new URL(url);
    if (parsed.protocol === "https:" || parsed.protocol === "http:") {
      shell.openExternal(url);
    }
  } catch {
    // Not a valid URL; ignore it.
  }
}

function showOfflinePage() {
  if (!mainWindow) return;
  mainWindow.loadFile(path.join(__dirname, "offline.html"), {
    query: { retry: START_URL },
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1360,
    height: 860,
    minWidth: 1000,
    minHeight: 640,
    backgroundColor: "#05070f",
    autoHideMenuBar: true,
    title: "Elevare Workforce OS",
    icon: path.join(__dirname, "build", "icon.png"),
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      // The web app is remote content, so it gets no access to Node.
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  // Links to other sites open in the default browser, never inside the app.
  mainWindow.webContents.setWindowOpenHandler(function (details) {
    if (isAppUrl(details.url)) return { action: "allow" };
    openExternally(details.url);
    return { action: "deny" };
  });

  // The window only ever shows this app (or the local offline page).
  mainWindow.webContents.on("will-navigate", function (event, url) {
    if (url.startsWith("file://") || isAppUrl(url)) return;
    event.preventDefault();
    openExternally(url);
  });

  // No connection: show a friendly page with a Try again button.
  mainWindow.webContents.on("did-fail-load", function (_event, errorCode, _description, _url, isMainFrame) {
    // -3 means the load was cancelled (for example by another navigation).
    if (isMainFrame && errorCode !== -3) showOfflinePage();
  });

  mainWindow.on("closed", function () {
    mainWindow = null;
  });

  mainWindow.loadURL(START_URL);
}

// One copy of the app at a time: opening it again focuses the existing window.
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", function () {
    if (!mainWindow) return;
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  });

  app.whenReady().then(function () {
    if (!isDev) Menu.setApplicationMenu(null);
    createWindow();
    app.on("activate", function () {
      if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
  });

  app.on("window-all-closed", function () {
    if (process.platform !== "darwin") app.quit();
  });
}
