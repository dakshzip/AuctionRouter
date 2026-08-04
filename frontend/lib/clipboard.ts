/**
 * Copy text, with a fallback for when the async Clipboard API won't run.
 *
 * navigator.clipboard.writeText rejects on an unfocused document and is absent
 * entirely on insecure origins. Both cases used to fail silently — the promise
 * rejected, the .then never ran, and the button gave no feedback at all. The
 * execCommand path is deprecated but still works in exactly those situations.
 */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // fall through to the legacy path
  }
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    // Keep it off-screen and non-focusable-looking so nothing visibly shifts
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    ta.style.pointerEvents = "none";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}
