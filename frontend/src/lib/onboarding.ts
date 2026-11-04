// Remembers how far a person got in the onboarding wizard, so signing in again
// takes them back to where they stopped. The API has no "onboarding progress"
// field yet, so this is kept in the browser: it works on the same browser and
// device, not across devices. (Ask the backend for a real flag if that matters.)

const KEY = "wos_onboarding_progress";

interface Progress {
  userId: string;
  path: string;
  done: boolean;
}

function read(): Progress | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Progress;
    if (!parsed || typeof parsed.userId !== "string" || typeof parsed.path !== "string") return null;
    return parsed;
  } catch {
    return null;
  }
}

function write(value: Progress): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(value));
  } catch {
    // Storage can be blocked; the wizard works the same without it.
  }
}

// Called by the onboarding pages as the person moves through them.
export function rememberOnboardingStep(userId: string, path: string): void {
  const current = read();
  // A person who already finished doesn't get pulled back by revisiting a step.
  if (current && current.userId === userId && current.done) return;
  write({ userId: userId, path: path, done: false });
}

export function markOnboardingDone(userId: string): void {
  write({ userId: userId, path: "", done: true });
}

// The step this person should resume at, or null when there's nothing to resume.
export function resumePath(userId: string): string | null {
  const current = read();
  if (!current || current.userId !== userId || current.done || !current.path) return null;
  return current.path;
}
