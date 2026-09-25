import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

const STORAGE_KEY = 'i2p.speech.muted';

/** Read the persisted preference, defaulting to unmuted so the booth demo speaks on first load. */
function initialMuted(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === 'true';
  } catch {
    return false;
  }
}

/**
 * Theo's voice, on the browser's built-in speech synthesis.
 *
 * Deliberately no dependency and no cloud call: `speechSynthesis` ships in every current browser,
 * costs nothing and has no latency, which matters at a booth. Where it is unavailable the hook
 * reports `supported: false` and every call is a no-op, so nothing breaks.
 *
 * Long answers are trimmed before speaking. Theo's replies carry bullet lists and tables of
 * figures that are miserable read aloud, so only the headline sentences are spoken; the detail
 * stays on screen to be read.
 */
export function useSpeech() {
  const [muted, setMuted] = useState<boolean>(initialMuted);
  const [speaking, setSpeaking] = useState(false);
  const supported = typeof window !== 'undefined' && 'speechSynthesis' in window;
  const voiceRef = useRef<SpeechSynthesisVoice | null>(null);

  // Voices load asynchronously in some browsers, so pick one when the list arrives.
  useEffect(() => {
    if (!supported) return;
    function pick() {
      const voices = window.speechSynthesis.getVoices();
      voiceRef.current =
        voices.find((voice) => /en-GB/i.test(voice.lang) && /female|libby|sonia|hazel/i.test(voice.name)) ??
        voices.find((voice) => /en-GB/i.test(voice.lang)) ??
        voices.find((voice) => /^en/i.test(voice.lang)) ??
        null;
    }
    pick();
    window.speechSynthesis.addEventListener('voiceschanged', pick);
    return () => window.speechSynthesis.removeEventListener('voiceschanged', pick);
  }, [supported]);

  const stop = useCallback(() => {
    if (!supported) return;
    window.speechSynthesis.cancel();
    setSpeaking(false);
  }, [supported]);

  const speak = useCallback(
    (text: string) => {
      if (!supported || muted || !text.trim()) return;
      // Never queue: a new answer supersedes whatever was still being read out.
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(spoken(text));
      if (voiceRef.current) utterance.voice = voiceRef.current;
      utterance.lang = voiceRef.current?.lang ?? 'en-GB';
      utterance.rate = 1.04;
      utterance.pitch = 1.02;
      utterance.onstart = () => setSpeaking(true);
      utterance.onend = () => setSpeaking(false);
      utterance.onerror = () => setSpeaking(false);
      window.speechSynthesis.speak(utterance);
    },
    [muted, supported],
  );

  const toggleMute = useCallback(() => {
    setMuted((current) => {
      const next = !current;
      try {
        window.localStorage.setItem(STORAGE_KEY, String(next));
      } catch {
        // Persistence is a convenience; the toggle still works for this visit.
      }
      if (next && supported) window.speechSynthesis.cancel();
      return next;
    });
  }, [supported]);

  // Stop talking when the screen goes away, so a voice does not follow the user around.
  useEffect(() => stop, [stop]);

  // Memoised so callers can safely put this in an effect's dependency list.
  return useMemo(
    () => ({ speak, stop, muted, toggleMute, speaking, supported }),
    [speak, stop, muted, toggleMute, speaking, supported],
  );
}

/** Trim a reply down to what is worth hearing, and strip characters that read badly aloud. */
function spoken(text: string): string {
  const [headline] = text.split('\n\n');
  const trimmed = (headline || text).replace(/[•·]/g, ',').replace(/\s+/g, ' ').trim();
  if (trimmed.length <= 320) return trimmed;
  // Cut on the last sentence boundary inside the budget rather than mid-word.
  const clipped = trimmed.slice(0, 320);
  const lastStop = clipped.lastIndexOf('. ');
  return lastStop > 80 ? clipped.slice(0, lastStop + 1) : `${clipped}…`;
}
