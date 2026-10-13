/**
 * Tabs with full keyboard support.
 *
 * In plain words: follows the standard ARIA tabs pattern - Left/Right arrows move between
 * tabs, Home/End jump to the first/last one, and only the active panel is in the tab order.
 * On narrow screens the tab strip scrolls sideways inside itself (the page never does).
 */
import clsx from "clsx";
import { useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

export interface TabDef {
  id: string;
  label: string;
  content: ReactNode;
}

export function Tabs({ tabs, initial }: { tabs: TabDef[]; initial?: string }) {
  const [active, setActive] = useState(initial ?? tabs[0]?.id);
  const base = useId();
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  function onKeyDown(event: KeyboardEvent, index: number) {
    const last = tabs.length - 1;
    const target = { ArrowRight: index === last ? 0 : index + 1, ArrowLeft: index === 0 ? last : index - 1, Home: 0, End: last }[event.key];
    if (target === undefined) return;
    event.preventDefault();
    setActive(tabs[target].id);
    refs.current[tabs[target].id]?.focus();
  }

  return (
    <div>
      <div role="tablist" aria-orientation="horizontal" className="-mx-1 flex gap-1 overflow-x-auto border-b border-line px-1">
        {tabs.map((tab, index) => (
          <button
            key={tab.id}
            ref={(el) => {
              refs.current[tab.id] = el;
            }}
            role="tab"
            id={`${base}-tab-${tab.id}`}
            aria-selected={active === tab.id}
            aria-controls={`${base}-panel-${tab.id}`}
            tabIndex={active === tab.id ? 0 : -1}
            onClick={() => setActive(tab.id)}
            onKeyDown={(e) => onKeyDown(e, index)}
            className={clsx(
              "-mb-px min-h-10 shrink-0 border-b-2 px-3 text-sm font-medium whitespace-nowrap",
              active === tab.id ? "border-brand text-ink" : "border-transparent text-ink-3 hover:text-ink",
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>
      {tabs.map((tab) => (
        <div key={tab.id} role="tabpanel" id={`${base}-panel-${tab.id}`} aria-labelledby={`${base}-tab-${tab.id}`} hidden={active !== tab.id} tabIndex={0} className="pt-4">
          {active === tab.id && tab.content}
        </div>
      ))}
    </div>
  );
}
