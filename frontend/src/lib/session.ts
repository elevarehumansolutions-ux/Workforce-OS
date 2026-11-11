import { apiFetch, clearAccessToken } from "@/lib/api";

// Signs this device out. Asking the server to end the session is best effort: if it cannot be
// reached, the person must still be able to sign out here, so the local token is cleared either way.
export async function signOut(): Promise<void> {
  try {
    await apiFetch("/auth/logout", { method: "POST" });
  } catch {
    // Signing out on this device should work even if the server can't be reached.
  }
  clearAccessToken();
}
