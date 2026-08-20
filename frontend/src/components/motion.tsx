import { AnimatePresence, motion, useReducedMotion, type Transition } from "motion/react";
import { useLocation } from "react-router-dom";
import type { CSSProperties, ReactNode } from "react";

/**
 * The app's motion vocabulary.
 *
 * Three rules hold everywhere:
 *
 *   1. Every animation is opt-out. `useReducedMotion` collapses each variant
 *      to its resting state, so a user who asked the OS for less motion gets
 *      a static page rather than a faster one.
 *   2. Motion never gates content. Reveals animate opacity and offset only --
 *      the element is in the DOM and readable the whole time, so a dropped
 *      frame or a blocked IntersectionObserver cannot hide data.
 *   3. Springs, not durations, for anything the pointer drives. Durations are
 *      reserved for enter/exit, where there is no input to track.
 */

export const SPRING: Transition = { type: "spring", stiffness: 400, damping: 32, mass: 0.6 };

/** Route-level fade + lift. Keyed on pathname so each page animates once. */
export function PageTransition({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const still = useReducedMotion();
  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={pathname}
        initial={still ? false : { opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={still ? undefined : { opacity: 0, y: -4 }}
        transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
}

/**
 * Scroll reveal.
 *
 * `once` and a generous margin mean a section animates as it comes into
 * reading range and then stops being animated at all -- no re-triggering
 * while the user scrolls back over content they have already read.
 */
export function Reveal({
  children,
  delay = 0,
  className,
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
}) {
  const still = useReducedMotion();
  if (still) return <div className={className}>{children}</div>;
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 12 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "0px 0px -80px 0px" }}
      transition={{ duration: 0.35, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  );
}

/** Container whose children enter one after another. Pair with `StaggerItem`. */
export function Stagger({
  children,
  className,
  style,
  step = 0.03,
}: {
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
  step?: number;
}) {
  const still = useReducedMotion();
  if (still)
    return (
      <div className={className} style={style}>
        {children}
      </div>
    );
  return (
    <motion.div
      className={className}
      style={style}
      initial="hidden"
      animate="shown"
      variants={{ shown: { transition: { staggerChildren: step } } }}
    >
      {children}
    </motion.div>
  );
}

export const staggerItem = {
  hidden: { opacity: 0, y: 6 },
  shown: { opacity: 1, y: 0, transition: { duration: 0.25, ease: [0.22, 1, 0.36, 1] as const } },
};
