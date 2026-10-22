// Stand-in for the window.storage API that only exists inside Claude's chat preview.
// Same shape: get(key, shared) -> { value } | null, set(key, value, shared).
// Data lives in this browser's localStorage, so it is per-device, not shared between people.
// Swap this file for a real backend (Supabase, Firebase, your own API) later.

const PREFIX = "nursesync:";

if (typeof window !== "undefined" && !window.storage) {
  window.storage = {
    async get(key) {
      const value = localStorage.getItem(PREFIX + key);
      return value === null ? null : { key, value };
    },
    async set(key, value) {
      localStorage.setItem(PREFIX + key, value);
      return { key, value };
    },
    async delete(key) {
      localStorage.removeItem(PREFIX + key);
      return { key, deleted: true };
    },
  };
}
