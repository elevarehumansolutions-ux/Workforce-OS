// Runs before the web app loads, in a locked-down bridge. It tells the web app
// that it is running inside the desktop app and nothing more. Add anything new
// here deliberately, one small function at a time.

const { contextBridge } = require("electron/renderer");

contextBridge.exposeInMainWorld("wosDesktop", {
  isDesktop: true,
  platform: process.platform,
});
