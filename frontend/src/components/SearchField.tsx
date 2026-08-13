import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { Loader2, Search, X } from "lucide-react";
import { ICON } from "./icons";
import { SPRING } from "./motion";

/**
 * Animated search input.
 *
 * Ported from the favicon-search reference: the leading glyph cross-fades
 * between states and the clear button springs in once there is something to
 * clear. The favicon lookup itself is dropped -- it fetches from Google's
 * favicon service, and this application has no URLs to resolve and makes no
 * third-party network calls.
 */
export function SearchField({
  id,
  label,
  value,
  onChange,
  placeholder,
  loading = false,
  autoFocus,
  className,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  loading?: boolean;
  autoFocus?: boolean;
  className?: string;
}) {
  const still = useReducedMotion();
  const pop = still
    ? {}
    : {
        initial: { opacity: 0, scale: 0.7 },
        animate: { opacity: 1, scale: 1 },
        exit: { opacity: 0, scale: 0.7 },
        transition: SPRING,
      };

  return (
    <div className={`searchfield ${className ?? ""}`}>
      <label className="searchfield__label" htmlFor={id}>
        {label}
      </label>
      <div className="searchfield__box">
        <span className="searchfield__glyph" aria-hidden="true">
          <AnimatePresence mode="wait" initial={false}>
            {loading ? (
              <motion.span key="load" {...pop} className="searchfield__spin">
                <Loader2 {...ICON} size={16} />
              </motion.span>
            ) : (
              <motion.span key="idle" {...pop}>
                <Search {...ICON} size={16} />
              </motion.span>
            )}
          </AnimatePresence>
        </span>
        <input
          id={id}
          className="searchfield__input"
          type="search"
          autoFocus={autoFocus}
          placeholder={placeholder}
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
        <AnimatePresence>
          {value.length > 0 && (
            <motion.button
              type="button"
              className="searchfield__clear"
              onClick={() => onChange("")}
              aria-label="Clear search"
              {...pop}
            >
              <X {...ICON} size={14} />
            </motion.button>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
