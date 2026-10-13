/*
 * Responsive audit - paste into the browser DevTools console while the app is open and signed in.
 *
 * In plain words: it visits each of the seven screens (and the three Settings tabs and the decision
 * history) without reloading the page and reports any element that sticks out past the right edge of
 * the viewport and is NOT inside its own scrolling container. An empty "problems" list means the screen
 * has no horizontal overflow at the current window width. Repeat it at 360, 390, 768, 1024 and 1440 px
 * (DevTools > device toolbar).
 *
 *     await window.__audit()        // -> { viewport: 360, problems: [] }
 */
window.__audit = async () => {
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const routes = ["/", "/gallery", "/match", "/video", "/lookalike", "/evaluation", "/settings?tab=model", "/settings?tab=system", "/settings?tab=preferences", "/history"];
  const problems = [];

  for (const route of routes) {
    history.pushState({}, "", route);
    window.dispatchEvent(new PopStateEvent("popstate")); // the router listens for this
    await sleep(1600); // let the screen load its data

    const viewport = document.documentElement.clientWidth;
    const pageWidth = document.documentElement.scrollWidth;

    const offenders = [...document.querySelectorAll("main *, header *, aside *")]
      .filter((element) => {
        const box = element.getBoundingClientRect();
        if (box.width === 0 || box.right <= viewport + 1) return false;
        // Fine if some ancestor scrolls (a table in an overflow-x container, the tab strip, ...).
        for (let parent = element.parentElement; parent && parent !== document.body; parent = parent.parentElement) {
          const overflow = getComputedStyle(parent).overflowX;
          if (overflow === "auto" || overflow === "scroll" || overflow === "hidden") return false;
        }
        return getComputedStyle(element).position !== "fixed";
      })
      .slice(0, 3)
      .map((element) => `${element.tagName.toLowerCase()}.${String(element.className).split(" ").slice(0, 2).join(".")} right=${Math.round(element.getBoundingClientRect().right)}`);

    if (pageWidth > viewport || offenders.length) problems.push({ route, viewport, pageWidth, offenders });
  }
  return { viewport: document.documentElement.clientWidth, problems };
};
/*
 * The labs only have wide tables and charts once a run has finished. With a finished result on screen
 * (open /evaluation or /lookalike first), this checks every tab (Ablation, ROC, Look-alike pairs, Mistakes,
 * Threshold sandbox ...) the same way:
 *
 *     await window.__auditTabs()    // -> { viewport: 360, tabsChecked: 7, problems: [] }
 */
window.__auditTabs = async () => {
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const viewport = document.documentElement.clientWidth;
  const problems = [];
  for (const tab of document.querySelectorAll("[role=tab]")) {
    tab.click();
    await sleep(900);
    const pageWidth = document.documentElement.scrollWidth;
    const offenders = [...document.querySelectorAll("main *")]
      .filter((element) => {
        const box = element.getBoundingClientRect();
        if (box.width === 0 || box.right <= viewport + 1) return false;
        for (let parent = element.parentElement; parent && parent !== document.body; parent = parent.parentElement) {
          const overflow = getComputedStyle(parent).overflowX;
          if (overflow === "auto" || overflow === "scroll" || overflow === "hidden") return false;
        }
        return true;
      })
      .slice(0, 3)
      .map((element) => `${element.tagName.toLowerCase()}.${String(element.className).split(" ").slice(0, 2).join(".")} right=${Math.round(element.getBoundingClientRect().right)}`);
    if (pageWidth > viewport || offenders.length) problems.push({ tab: tab.textContent, viewport, pageWidth, offenders });
  }
  return { viewport, tabsChecked: document.querySelectorAll("[role=tab]").length, problems };
};
"audit installed - run:  await window.__audit()   (and, on /evaluation with a finished run:  await window.__auditTabs())";
