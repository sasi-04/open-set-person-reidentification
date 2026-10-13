# Interface design - direction, tokens, accessibility, responsiveness

## 1. Direction

The interface should read as a **computer-vision research workstation**: precise, calm, and honest - an engineering tool for investigating matching failures, not a marketing dashboard. The default is a **graphite** theme (deep neutral surfaces, white and cool-grey text, hairline borders, almost no shadow), with a light theme one click away; the choice is remembered. A single restrained **crimson** accent (`#E31B23`) marks the primary action and the active navigation item only,
**Poppins** headings and **Inter** body text. The broad principles (operational clarity, restraint, a single red accent, pill-shaped buttons, modular cards) echo [zed.digital](https://zed.digital/)'s public site; nothing is copied from it. No Zed Digital logo, imagery or other assets are used; the product mark is an original "OpenID Vision" logo (two overlapping rings with a red tick), and the sidebar footer states that this is an **independent prototype, not an official Zed Digital product**.

Principles: graphite surfaces by default (a dark navigation rail, in both themes) · red appears only on the primary action and the active-navigation marker · status colours are separate from the brand red so "error" is never confused with "brand" ·
no gradients, glows or decorative animation · compact operational headings (no marketing hero text) · every empty state says what to do next.

## 2. Design tokens

All colours, radii, shadows and fonts are CSS variables in [`frontend/src/styles/index.css`](../frontend/src/styles/index.css), exposed to Tailwind through `@theme`. **Components contain no raw colour values**, so the dark theme (and any rebranding) is a change in one file.

| Token | Light | Dark | Use |
|---|---|---|---|
| `--canvas` / `--surface` / `--surface-2` | `#f6f7f8` / `#ffffff` / `#f2f4f6` | `#0e1115` / `#161a20` / `#1c2128` | page / cards / subtle panels |
| `--line` / `--line-strong` | `#e3e5e9` / `#cdd1d7` | `#2a3039` / `#3a414c` | fine borders (1 px) |
| `--ink` / `--ink-2` / `--ink-3` | `#0b0d10` / `#454b54` / `#5f6672` | `#f3f4f6` / `#b6bcc6` / `#8e96a3` | primary / secondary / muted text |
| `--brand`, `--brand-ink` | `#e31b23`, `#c8161e` | `#e31b23`, `#ff7a80` | primary button / accent *as text* |
| status `ok` `warn` `neutral` `bad` `info` | green / amber / slate / red / blue, each with a matching tinted background | lightened for dark | outcome and policy badges - always icon **and** text |
| `--nav-*` | `#0b0d10` rail, `#171b21` active | slightly darker | sidebar |
| chart `--series-1…5` | `#2a78d6 #eb6834 #1baf7a #eda100 #e87ba4` | `#3987e5 #d95926 #199e70 #c98500 #d55181` | fixed per entity, never cycled |

Radii 6 / 10 / 14 px and pill (999 px) for buttons and badges · shadows `0 1px 2px` (cards) and `0 6px 24px` (popovers) · fonts: **Inter** (variable, UI) and **Poppins** (headings), both self-hosted via `@fontsource` so the app works offline ·
spacing is Tailwind's 4 px scale · numbers use `tabular-nums` only where they align in columns.

Light is the default theme; the toggle persists the choice and is applied before first paint (no flash).

## 3. Accessibility measures

| Area | What is done |
|---|---|
| **Structure** | One `<h1>` per screen; landmarks (`header`, a single `nav` "Main", `main`); a **skip link**; tables have captions and `scope` headers; dialogs are real modal dialogs (Radix: focus trapped, Escape closes, focus returns). |
| **Forms** | Every control has a visible `<label>`; hints and errors are tied with `aria-describedby`; invalid fields get `aria-invalid`; errors use `role="alert"`; touch targets ≥ 40 px. |
| **Keyboard** | All actions are real buttons/links; tabs follow the ARIA pattern (arrows, Home/End); the detection boxes on an image are buttons; a visible 2 px focus ring everywhere; info tooltips open on focus/click and close with Escape. |
| **Screen readers** | Live regions announce toasts, the decision panel and job progress; progress bars and score meters expose `aria-valuenow/valuetext`; badges always pair an icon with text; images have alt text; decorative icons are `aria-hidden`. |
| **Colour** | Information never relies on colour alone (outcome = icon + words; charts have a legend, tooltips **and** a data table). Contrast ratios below. |
| **Motion** | Subtle 180 ms fades only; `prefers-reduced-motion` disables them. `forced-colors` keeps badge and card borders. |

### Contrast (computed WCAG 2.x ratios, every text/background pair used)

| Pair (light theme) | Ratio | Pair (dark theme) | Ratio |
|---|---|---|---|
| body text on card / page | 19.5 / 18.1 | body text on card / page | 15.9 / 17.2 |
| secondary text on card | 8.8 | secondary text on card | 9.1 |
| **muted text** on card / page / subtle panel | **5.8 / 5.4 / 5.3** | muted text on card / page / panel | 5.9 / 6.4 / 5.4 |
| accent text on card | 5.9 | accent text on card | 6.9 |
| primary button (white on red) | 4.7 | primary button | 4.7 |
| status badges (ok / warn / neutral / error / info) | 5.3 - 8.6 | status badges | 7.2 - 8.8 |
| sidebar idle / active text | 7.5 / 15.7 | sidebar | 7.6 / 16.2 |
| focus ring, brand red (non-text, ≥ 3) | 6.1, 4.7 | focus ring, brand red | 8.0, 3.7 |

This check found and fixed one real failure (muted text on the subtle panel was 4.38:1; the muted colour was darkened from `#6b7280` to `#5f6672`). Worth knowing: the *accent as text* uses a darker red than the button (`#c8161e` vs `#e31b23`) for that reason.

## 4. Charts

Built with Recharts, following a validated data-visualisation method: **fixed entity→colour order** (a variant keeps its colour whichever others are shown), thin 2 px lines, solid hairline grids (never dashed), operating-point markers ≥ 10 px with a surface ring, direct axis titles, a legend whenever ≥ 2 series,
informative tooltips, and a **"View data as a table"** twin under every chart (a tooltip is never the only way to read a value). The five-colour palette was run through a colour-vision-deficiency / contrast validator against *this app's own* light and dark surfaces:
all hard checks pass in both themes (worst adjacent colour-blind ΔE 9.1 light / 8.4 dark); three light-mode colours are below 3:1 against white, which the method makes acceptable only with a visible legend and table - both are always present.
Charts use only measured data from the run's JSON and skip missing values rather than drawing zeros. Axes avoid misleading scales (FAR on a linear axis by default; an optional log axis states that FAR = 0 cannot be drawn).

## 5. Responsive layout

| Width | Layout |
|---|---|
| ≥ 1280 px | sidebar (256 px) + three-column workspace (query · preview · decision) |
| 1024 - 1279 | sidebar + two columns (decision moves below); dashboards use one column of wide cards |
| 768 - 1023 | **icon rail** (72 px) + content; labels are in the accessible name and tooltip |
| < 768 | top bar with a **menu button** opening the navigation as a slide-over dialog; everything stacks; tables become card lists (History) or scroll *inside* their card |

Rules: `min-w-0` cards (a wide child must never stretch the page), images and charts scale with their container, dialogs are `calc(100vw − 1.5rem)` wide and scroll inside, buttons wrap rather than overflow.

### Responsive testing

Layout cannot be tested in jsdom, so it was tested in a real browser with a scripted audit ([`scripts/responsive_audit.js`](../scripts/responsive_audit.js)): for **each of the 7 screens at 360, 390, 768, 1024 and 1440 px** it measures whether the page scrolls horizontally and lists any element that sticks
out of the viewport without its own scroll container. Result of the final run for the seven-screen version: **no horizontal overflow on any screen at any width** (the audit now also covers the three Settings tabs, the decision history, a finished Video Explorer job and every tab of a finished Lookalike Failure Lab experiment, and it found and led to the fix of two more real defects: long filter menus stretching the lab at 360 px, and long status badges stretching the three-column pair cards at 1440 px).
(The earlier six-screen result, kept for the record:) no horizontal overflow on any screen at any width. The Evaluation Lab's wide content only exists once a run has finished, so a second check (`__auditTabs`) opens **each of its 7 result tabs** (ablation table, ROC, score distribution, CMC, same-clothing subset, speed, metadata) on a real finished run
at the same five widths: also no overflow. The audit found and led to the fix of two real defects (a wide table stretching the Settings page on phones; a badge overflowing the Overview cards at 1024 px).
Repeat it yourself: open the app, paste the script into the DevTools console, resize, run `await window.__audit()` (and `await window.__auditTabs()` on a finished evaluation).
The ROC chart, score-distribution chart and results cards were also inspected visually at phone width.

## 6. Component inventory

`components/ui/`: Button, Badge (+ OutcomeBadge, PolicyBadge), Card/Stat/DefinitionList, InfoTip, Field/TextInput/Select/Checkbox/Segmented, Dialog/ConfirmDialog, Toast, Tabs, Progress, FileDrop, AuthImage, Feedback (Spinner, Skeleton, EmptyState, ErrorState, Notice), PageHeader.
`features/lookalike/`: LabForm, LabResults (six tabs), ChallengePanel, cards (PairCard, HardGenuineCard, FailureCard - observed facts and unproven hypotheses in separate blocks). `features/video/`: VideoUpload, VideoStatus, VideoResults (timeline, frame viewer, people table). `features/evaluation/ThresholdSandbox`. `features/settings/`: SystemPanel, PreferencesPanel.
`components/layout/`: AppShell, Sidebar (+ NavList), Topbar (readiness, device, theme, and role when access keys are on), Brand. Each has a plain-words header comment, and behaviour-level tests in `ui.test.tsx` and `pages.test.tsx`.
