# Design System: 咪兔 Frontend
**Surface:** `scene/http_sse/static` — React + TypeScript chat companion UI

---

## Configuration — Set Your Style

| Dial | Level | Description |
|------|-------|-------------|
| **Creativity** | `4` | `1` = generic SaaS. `5` = balanced product personality. `10` = editorial/expressive. This UI is a chat tool first; personality comes from the ASCII companion and warm neutrals, not from layout theatrics. |
| **Density** | `6` | `1` = gallery-airy. `5` = balanced. `10` = cockpit-dense. Chat UIs are information-dense by nature, but whitespace is preserved around messages to keep reading comfortable. |
| **Variance** | `3` | `1` = rigid repeated grids. `5` = subtle offsets. `10` = artsy chaos. Conversational UI rewards predictable rhythms; variance is limited to welcome prompts and page layouts. |
| **Motion Intent** | `5` | `1` = static. `5` = subtle hover/entrance cues. `10` = cinematic. Motion is functional: message entry, button press, panel expansion. |

---

## 1. Visual Theme & Atmosphere

**Creative North Star: "Handmade Digital Companion"**

The frontend visualizes 咪兔 as a warm AI companion wrapped in a restrained terminal aesthetic. The tension is between **ASCII craft** (monospace sprites, code blocks, muted labels) and **emotional warmth** (tinted neutrals, soft pastels, tactile button feedback). It is not a cold developer dashboard, nor a bubbly consumer chat app. It is the visual equivalent of a well-worn notebook filled with carefully typed notes and a small cat doodle in the corner.

The interface is light by default. The dark theme exists as a system/user toggle and is not merely an inversion — it keeps the warm tint in neutrals and raises accent saturation to maintain readability in low light.

A deliberate exception lives inside the chat stream: the **EvolutionPanel** is a dark, noise-grained, scan-lined "precision lab" terminal. It is intentionally foreign to the warm canvas, signaling that the companion is undergoing internal transformation.

---

## 2. Color Palette & Roles

All colors are authored as CSS custom properties in `src/theme/tokens.css`. Both light and dark themes share the same semantic variable names; values swap under `[data-theme="dark"]`.

### Neutral Canvas (Primary Surfaces)
- **Canvas** `#fdfcfc` — Primary app background. Warm-white, not pure white.
- **Surface Soft** `#f8f7f7` — Sidebar, assistant bubbles, code headers, secondary panels.
- **Surface Card** `#f1eeee` — Hover states, pressed states, code block backgrounds.
- **Surface Dark** `#201d1d` — User message bubbles, primary button fills, dark mode deepest layer.

### Text
- **Ink** `#201d1d` — Primary text and strong fills.
- **Body** `#424245` — Assistant message text, descriptions.
- **Mute** `#646262` — Secondary text, borders, scrollbars.
- **Stone** `#6e6e73` — Timestamps, code language labels, tertiary hints.
- **Ash** `#595959` — Placeholders, disabled hints.
- **On Dark** `#fdfcfc` — Text on top of Surface Dark.

### Structural
- **Hairline** `rgba(15, 0, 0, 0.10)` — Default 1px borders.
- **Hairline Strong** `#646262` — Hover/active borders, scrollbar thumbs.
- **Backdrop** `rgba(0, 0, 0, 0.35)` — Modal overlays.
- **Shadow** `rgba(0, 0, 0, 0.04)` — Subtle elevation.
- **Focus Ring** `rgba(32, 29, 29, 0.10)` — Focus-within glow.

### Accent & Semantic
- **Accent** `#007aff` (light) / `#409cff` (dark) — Links, focus outlines, active toggles, selected model.
- **Accent Hover** `#0056b3` (light) / `#6db5ff` (dark)
- **Danger** `#ff3b30` (light) / `#ff453a` (dark)
- **Warning** `#ff9f0a`
- **Success** `#30d158`

### Pastel Category Markers
Used for tags, badges, connector types, and status chips. Each pairing guarantees readable contrast.

- **Rose** — bg `#FDEBEC`, text `#9F2F2D`
- **Sky** — bg `#E1F3FE`, text `#1F6C9F`
- **Sage** — bg `#EDF3EC`, text `#346538`
- **Honey** — bg `#FBF3DB`, text `#956400`

### Banned Colors
- Pure black `#000000` and pure white `#ffffff`.
- Cold, desaturated greys without a warm tint.
- Neon gradients or "AI purple" aesthetics.
- Oversaturated accents outside the semantic set.

### Named Rules
**The Warm Neutral Rule.** Every grey must carry a warm tint (hue ~15–30°). `#646262`, `#424245`, and `#6e6e73` all obey this. Pure neutral greys are not allowed.

**The One Blue Rule.** Accent Blue is the only functional emphasis color. Pastels are for category marking, not interactive hierarchy.

---

## 3. Typography Rules

- **Display / Serif:** `'Newsreader', 'Playfair Display', 'Lyon Text', 'Instrument Serif', serif` — Used only for the welcome screen brand wordmark.
- **Body / Sans:** `-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', Arial, 'PingFang SC', 'Microsoft YaHei', sans-serif` — All UI text and chat content.
- **Mono:** `'JetBrains Mono', 'IBM Plex Mono', ui-monospace, 'SF Mono', Menlo, Monaco, Consolas, 'PingFang SC', 'Microsoft YaHei', monospace` — Labels, timestamps, code, skill names, ASCII companion art.

### Scale
- **Display:** 32px, serif, `-0.02em` tracking, line-height `1.1`.
- **Headline:** 15–16px, sans, weight 600–700, line-height `1.4`.
- **Body:** 14px desktop, 15px in H5 bubbles, line-height `1.6`, max-width ~72ch inside assistant bubbles.
- **Label / Mono:** 11–12px, weight 500, `0.04em` tracking for uppercase labels.

### Named Rules
**The Mono Thread Rule.** All short non-body text — labels, timestamps, skill names, code language tags, model names — uses the mono font stack. This keeps the terminal texture present without dominating the interface.

**No Flat Hierarchy Rule.** Hierarchy is built through weight contrast and color, not font-size inflation. Most of the UI lives between 11px and 16px.

---

## 4. Component Stylings

### Buttons
- **Base:** 4px radius (`--radius-sm`), 1px hairline border, min-height 44px on H5.
- **Primary:** Surface Dark fill + Canvas text. Hover darkens to `#0f0000`. Active `transform: scale(0.98)`.
- **Default / Secondary:** Canvas fill + hairline border. Hover darkens border to hairline-strong.
- **Danger:** Canvas fill + Rose border/text. Hover adds 6% Rose background.
- **Icon Action Button:** 44px touch target, transparent, hover fills Surface Card.
- **Send Button:** Square 44px, Surface Dark fill, Canvas icon.

### Inputs
- **Textarea / Chat Input:** Surface Soft fill, hairline border, 4px radius. Focus: Accent border + 3px focus-ring glow.
- **Search Field:** Same pattern, with a search icon and optional clear button.
- **Form Inputs:** Canvas fill, hairline border, 4px radius. Focus ring in Accent.

### Message Bubbles
- **User Bubble:** Surface Dark fill, Canvas text, max-width 75% desktop, 72% H5, rounded 4px.
- **Assistant Bubble:** Surface Soft fill, Body text, 1px hairline border, max-width 100% (800px on large screens).
- **Tool Bubble:** Surface Soft fill, Mute text, mono 12px.
- **Error Bubble:** 6% Rose background, Rose border/text, mono 13px.

### Code Blocks
- **Wrapper:** Surface Card background, 1px hairline border, 4px radius, `overflow: hidden`.
- **Header:** Surface Soft background, hairline bottom border, mono language label + copy button.
- **Body:** 13px mono, horizontal scroll, padding 12px 16px.

### Cards / Lists
- **Card:** Surface Soft fill, 1px hairline border, 4px radius, padding 14px. Hover lifts with a 2px shadow.
- **Card Grid:** `repeat(auto-fill, minmax(260px, 1fr))` on desktop; single column on mobile.
- **Connector Item:** Surface Soft, 4px radius, hairline border. Status indicated by a 2px left border (success/danger) — this is the only allowed side-stripe usage because it is status semantics, not decorative accent.
- **Expert Item:** Horizontal divider list, no card wrapper.

### Tags / Chips
- **Pastel Tag:** 9999px radius (pill), 11px sans, weight 500, `0.03em` tracking, uppercase. Uses the pastel bg/text pairs.
- **Connector Badge / Tool Badge:** Same pill pattern, 10px.

### Navigation
- **Sidebar (Desktop):** 260px width, Surface Soft background, hairline right border. Collapses to 52px icon-only mode. Mobile becomes a fixed overlay sliding from the left.
- **Bottom Tab Bar (H5):** Fixed bottom, Canvas fill, hairline top, icon + label tabs.
- **Compact Header (H5):** Fixed top, Canvas fill, hairline bottom, back + title + actions.

### Modal / Dialog
- **Backdrop:** 35% black.
- **Panel:** Canvas fill, 1px hairline-strong border, 4px radius, max-width 400px.
- **Animation:** Fade in backdrop, slide/scale panel with `cubic-bezier(0.22, 1, 0.36, 1)`.

### Companion Sprite (Signature)
- **Render:** `<pre>` block, mono font, fixed ASCII grid.
- **Sizes:** Small header avatar (~3 lines) and large login companion (full frame).
- **Animation:** CSS frame-loop (3 frames, ~0.4s/frame); sleeping emotion uses slower zzz float.
- **Rarity Reveal:** Mono stars + sans label, spring entrance.

---

## 5. Layout Principles

### Desktop
- **App Shell:** Full-height flex row. Sidebar 260px fixed. Main area is a flex column: header optional, chat container scrolls, input pinned to bottom.
- **Chat Container:** Max-width 800px centered, 16px/24px padding.
- **Page Body:** 20px/24px padding, flex column, scrollable.

### H5 Mobile
- **Phone Frame:** On desktop viewport the H5 app renders inside a 430px max-width, centered, shadowed phone frame.
- **True Mobile:** 100% width, 100dvh height, no phone frame.
- **App Shell:** Flex column. Header pinned top. Content scrolls. Bottom tab bar + safe-area inset.
- **Chat Padding:** 8px/10px horizontal. Bubbles nearly full-width for assistant.
- **Pages:** Single-column card grids, compact spacing (6–8px gaps).

### Containment
- No global `max-width` on the app root itself.
- Chat content is contained to 800px for readability.
- Page cards use responsive grids, not fixed percentages.

### Named Rules
**Tonal Layering First.** Depth is expressed through Surface Canvas → Soft → Card, not through heavy shadows. Shadows are limited to 2–8px blur at 4% opacity.

**No Card Nesting.** A card may contain lists or form fields; it may not contain another card.

---

## 6. Responsive Rules

The frontend serves two distinct targets from one codebase:

1. **Desktop Web** (`src/desktop/App.tsx`) — sidebar + main column, pointer-first.
2. **H5 Mobile** (`src/h5/App.tsx`) — phone-chrome or full-viewport, touch-first.

### Breakpoints
- `--bp-phone`: 480px
- `--bp-tablet`: 768px
- `--bp-wide`: 1024px

### Desktop Behavior
- Sidebar collapsible to 52px.
- Assistant bubbles cap at 800px width.
- Multi-column card grids.

### Tablet Behavior
- Sidebar remains collapsible.
- Card grids relax to smaller min widths.
- Page body padding reduces to 16px/20px.

### Mobile Behavior (< 768px)
- Sidebar becomes fixed overlay.
- All grids collapse to single column.
- Touch targets 44px minimum.
- Form inputs use 16px font to prevent iOS zoom.
- Header actions may hide text below 380px (icon-only).

### H5 Specifics
- Bubbles: user 72%, assistant 92% max-width.
- Input: rounded 18px inner textarea, minimal actions bar.
- Bottom tab bar + safe-area inset.
- Scroll-to-bottom floats above bottom chrome.

---

## 7. Motion & Interaction

All motion respects `prefers-reduced-motion`.

### Easing
- **Entrance:** `cubic-bezier(0.22, 1, 0.36, 1)` — ease-out-expo feel.
- **Hover / UI:** `ease` or `0.15s ease`.
- **Press:** `transform: scale(0.97–0.98)`.

### Common Animations
- **Message Entry:** User slides from right (`translateX(16px)`), assistant from left (`translateX(-12px)`), both fade + translateY.
- **Button Entry:** Scale from 0.8 to 1 with fade.
- **Popover:** `translateY(4px)` fade in.
- **Modal:** Backdrop fade, panel `translateY(-8px) scale(0.98)`.
- **Welcome Logo:** 3s ease-in-out float loop.
- **Recording Button:** 1.5s pulse opacity loop.
- **Companion Zzz:** 2s float + scale loop.
- **Companion Rarity:** 0.5s spring entrance.
- **Spinner:** 1.2s linear rotation for session loader.

### Hardware Rules
- Animate only `transform` and `opacity` for runtime animations.
- `width`, `height`, `top`, `left` are avoided.
- Sidebar collapse uses `transform: translateX` on mobile; desktop uses `width/min-width` transition because layout must reflow.

---

## 8. Anti-Patterns (Banned)

- No pure black `#000000` or pure white `#ffffff`.
- No gradient text (`background-clip: text`).
- No glassmorphism as decoration.
- No decorative side-stripe borders on cards or lists. (The only allowed side stripe is the 2px connector status indicator.)
- No identical icon + heading + text card grids for features.
- No modal as the first solution. Prefer inline expansion, popovers, or page transitions.
- No generic placeholder copy or AI clichés.
- No emojis in UI copy or iconography (ASCII companion art and inline SVG icons only).
- No circular loading spinners for content states; use skeletons where appropriate, or the existing session spinner for async operations.
- No `h-screen`; always `min-height: 100dvh`.

---

## 9. Theme Overrides

Light theme is the default. Dark theme is applied via `data-theme="dark"` on a parent element and persists through `theme-store.ts`.

Key dark swaps:
- Canvas → `#1c1c1e`
- Surface Soft → `#2c2c2e`
- Surface Card → `#3a3a3c`
- Ink → `#f5f5f7`
- Body → `#d1d1d6`
- Accent → `#409cff`
- Hairline becomes white at 12% opacity.
- Backdrop darkens to 55% black.

The EvolutionPanel does not participate in the warm light theme; it is permanently dark-terminal styled regardless of theme.
