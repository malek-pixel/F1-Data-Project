import { useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { NavLink } from "react-router-dom";
import { Icons, type IconName } from "./icons";

/**
 * macOS-style magnifying dock, adapted to this app's vertical rail.
 *
 * The reference implementation is horizontal and drives each icon from a
 * chained `useTransform`/`useSpring` pair off `mouseX`. The rail is a 56px
 * column, so the falloff is measured on Y instead, and one piece of pointer
 * state drives every icon rather than a motion value per icon. The scale is
 * a CSS transform with a CSS transition: no layout work per frame.
 *
 * Magnification is pointer-only: keyboard users get full-size targets, and
 * `prefers-reduced-motion` disables the size change entirely, since a control
 * that resizes under the cursor is what that setting exists to prevent.
 */

export interface DockItem {
  to: string;
  label: string;
  icon: IconName;
  end?: boolean;
  badge?: string;
}

/** Bell curve: 1 at the pointer, falling to 1.0 by `distance` px away. */
function magnify(offset: number, magnification: number, distance: number) {
  return (magnification - 1) * Math.exp(-(offset * offset) / (2 * distance * distance)) + 1;
}

export function Dock({
  items,
  magnification = 1.5,
  distance = 80,
  iconSize = 40,
}: {
  items: DockItem[];
  magnification?: number;
  distance?: number;
  iconSize?: number;
}) {
  const still = useReducedMotion();
  const [pointerY, setPointerY] = useState<number | null>(null);
  const [hovered, setHovered] = useState<{ label: string; top: number } | null>(null);

  return (
    <>
      <nav
        aria-label="Primary"
        className="rail__nav"
        onPointerMove={(event) => {
          if (still || event.pointerType === "touch") return;
          const rect = event.currentTarget.getBoundingClientRect();
          setPointerY(event.clientY - rect.top);
        }}
        onPointerLeave={() => setPointerY(null)}
      >
        {items.map((item, index) => (
          <DockIcon
            key={item.to}
            item={item}
            index={index}
            pointerY={pointerY}
            magnification={magnification}
            distance={distance}
            iconSize={iconSize}
            onHover={setHovered}
          />
        ))}
      </nav>

      {/* The label the icon-only rail otherwise hides. Fixed-positioned so it
          can escape the 56px column instead of being clipped by it. */}
      <AnimatePresence>
        {hovered && (
          <motion.span
            key="dock-tip"
            className="dock__tip mono"
            style={{ top: hovered.top }}
            initial={still ? false : { opacity: 0, x: -6, scale: 0.94 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={still ? undefined : { opacity: 0, x: -6, scale: 0.94 }}
            transition={{ duration: 0.13, ease: "easeOut" }}
          >
            {hovered.label}
          </motion.span>
        )}
      </AnimatePresence>
    </>
  );
}

function DockIcon({
  item,
  index,
  pointerY,
  magnification,
  distance,
  iconSize,
  onHover,
}: {
  item: DockItem;
  index: number;
  pointerY: number | null;
  magnification: number;
  distance: number;
  iconSize: number;
  onHover: (next: { label: string; top: number } | null) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const Icon = Icons[item.icon];

  // Measured against the icon's RESTING centre, not its current box. Using
  // the live rect would feed each frame's growth back into the next one and
  // the row would oscillate as neighbours pushed each other around.
  const restingCentre = index * iconSize + iconSize / 2;
  const scale = pointerY === null ? 1 : magnify(pointerY - restingCentre, magnification, distance);

  const report = () => {
    const rect = ref.current?.getBoundingClientRect();
    onHover({ label: item.label, top: rect ? rect.top + rect.height / 2 : 0 });
  };

  // Only the glyph scales. Animating the slot's height instead makes every
  // pointer move a reflow of the rail's flex column -- and that column is
  // height-constrained, so it shrinks the slot straight back. A transform
  // costs no layout and is what the eye reads as magnification anyway.
  return (
    <div className="dock__slot" ref={ref}>
      <NavLink
        to={item.to}
        end={item.end}
        className="rail__item"
        aria-label={item.label}
        onMouseEnter={report}
        onFocus={report}
        onMouseLeave={() => onHover(null)}
        onBlur={() => onHover(null)}
      >
        <span className="dock__glyph" style={{ transform: `scale(${scale})` }}>
          <Icon />
        </span>
        {item.badge && <span className="rail__badge mono">{item.badge}</span>}
      </NavLink>
    </div>
  );
}
