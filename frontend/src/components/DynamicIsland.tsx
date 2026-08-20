import { motion, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { SPRING } from "./motion";

/**
 * Dynamic island status pill.
 *
 * It replaces the shell's static "● healthy" chip. The point of the island
 * shape is that one element carries several states by changing size, so the
 * user's eye never has to find a new widget: idle collapses to the dataset
 * status, and a route change expands it briefly to name where you are.
 *
 * It reports API state and nothing else. An island that animated on a timer
 * would be a decoration claiming to be an indicator.
 */

export type IslandState =
  | { kind: "ok"; label: string }
  | { kind: "loading"; label: string }
  | { kind: "error"; label: string };

export function DynamicIsland({ state }: { state: IslandState }) {
  const { pathname } = useLocation();
  const still = useReducedMotion();
  const [flash, setFlash] = useState<string | null>(null);
  const first = useRef(true);

  // A route change expands the island for a moment, then it settles back.
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    const name = pathname === "/" ? "Overview" : pathname.split("/").filter(Boolean)[0];
    setFlash(name ? name.replace(/^./, (c) => c.toUpperCase()) : "Overview");
    const timer = setTimeout(() => setFlash(null), 1400);
    return () => clearTimeout(timer);
  }, [pathname]);

  const expanded = flash ?? null;

  return (
    <motion.div
      className={`island island--${state.kind}`}
      layout={still ? false : true}
      transition={still ? { duration: 0 } : SPRING}
      role="status"
      aria-live="polite"
    >
      <motion.span layout className={`island__dot island__dot--${state.kind}`} aria-hidden="true" />
      {/* No AnimatePresence. The label is a single keyed span, so a changed
          key is an ordinary React remount: the old node is gone in the same
          commit the new one appears, and it plays its enter animation.
          Both alternatives were tried and both broke:
            - `popLayout` with two branches orphaned a span on every route
              change, and each orphan widened a `nowrap` bar until the page
              scrolled sideways.
            - `mode="wait"` deadlocked. The child is never absent, so the exit
              that mode waits for never resolved and the label stuck on
              "connecting" permanently while the dot went on updating.
          Dropping the exit fade costs a 160ms crossfade on a 60px label and
          removes both failure modes. */}
      <motion.span
        key={expanded ?? `${state.kind}-${state.label}`}
        className="island__text mono"
        initial={still ? false : { opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.16 }}
      >
        {expanded ?? state.label}
      </motion.span>
    </motion.div>
  );
}
