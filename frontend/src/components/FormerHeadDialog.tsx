"use client";

import { useState } from "react";
import Modal from "@/components/Modal";
import { ApiError, apiFetch } from "@/lib/api";
import { roleLabel } from "@/lib/tasks";
import { ACCESS_LEVELS } from "@/lib/formerHead";
import type { FormerHead } from "@/lib/formerHead";

interface Props {
  former: FormerHead;
  // changed is true when HR saved a new access level, so the page can refresh what it shows.
  onClose: (changed: boolean) => void;
}

// Shown right after a department's head was replaced: the old head keeps their access level
// (they may still manage people elsewhere), so HR is asked what to do with it.
export default function FormerHeadDialog({ former, onClose }: Props) {
  const [role, setRole] = useState(former.role);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function save() {
    setSaving(true);
    setError("");
    try {
      await apiFetch("/memberships/" + former.membershipId, { method: "PATCH", body: { role: role } });
      onClose(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't change the access level.");
      setSaving(false);
    }
  }

  return (
    <Modal title={former.name + " is no longer head of " + former.department} onClose={function () { onClose(false); }}>
      <p className="text-sm text-gray-300">
        Their access level is still <span className="font-semibold text-white">{roleLabel(former.role)}</span>. It did not
        change when the head changed. Keep it, or set a new one now.
      </p>

      <label className="mt-4 block text-xs text-gray-400">
        Access level
        <select
          value={role}
          disabled={saving}
          onChange={function (e) { setRole(e.target.value); }}
          className="mt-1 block w-full rounded-lg border border-white/10 bg-[#05070f] px-3 py-2 text-sm text-gray-200 outline-none focus:border-indigo-500"
        >
          {ACCESS_LEVELS.map(function (level) {
            return <option key={level} value={level}>{roleLabel(level)}</option>;
          })}
        </select>
      </label>

      {error ? <p className="mt-3 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">{error}</p> : null}

      <div className="mt-5 flex flex-wrap justify-end gap-3">
        <button
          type="button"
          disabled={saving}
          onClick={function () { onClose(false); }}
          className="rounded-lg border border-white/10 px-4 py-2 text-xs text-gray-200 hover:bg-white/5 disabled:opacity-50"
        >
          Keep {roleLabel(former.role)}
        </button>
        <button
          type="button"
          disabled={saving || role === former.role}
          onClick={save}
          className="rounded-lg bg-indigo-500 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-600 disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save"}
        </button>
      </div>
    </Modal>
  );
}
