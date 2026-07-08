# Design System — Oriental Ink-Wash (水墨风)

## 1. Visual Theme & Atmosphere

This design system reimagines the chat journal interface through the lens of traditional East Asian ink-wash painting (水墨画). The entire canvas is built upon a **watercolor background image** (`style_1.jpeg`) that provides the primary artistic atmosphere — soft blue gradients with scattered white four-petaled flowers, evoking the serene beauty of a misty garden. UI elements float above this canvas on **semi-transparent backgrounds**, allowing the watercolor art to breathe through the gaps between messages and around cards.

The ink-blue text (`#2c3e3e`) against this cool, layered surface creates a tonal harmony reminiscent of brush strokes on rice paper, with contrast that remains effortlessly readable. The Ma Shan Zheng (马善正) typeface anchors the system in calligraphic tradition, used prominently at 22px for screen titles to showcase the brush-drawn character of each stroke.

The depth model relies on **hard-offset shadows** rather than Gaussian blur, simulating the shadow of objects resting on handmade paper. Combined with hand-drawn-style borders (`1.5px solid #2c3e3e`), every component feels like a carefully placed element on an ink-wash scroll.

**Key Characteristics:**
- **Watercolor background** (`style_1.jpeg`): Phone frame background — gradient blue with white floral motifs
- **Semi-transparent UI**: Headers (82%), input areas (88%), panels (94%), message bubbles (90-92%)
- Ma Shan Zheng calligraphic typeface for **all CJK text**, with Latin override (`local('Arial')`) ensuring English renders in clean sans-serif
- Hard-offset shadow system: `2px 2px 0 rgba(44,62,62,0.15)` — no blur, pure displacement
- Ink-blue border palette: `#2c3e3e` for bold strokes, `#c0d8d8` for subtle divisions
- Full-pill radius (`9999px`) for pills and icon buttons, 14px–16px for cards and containers
- Ink-wash radial gradients at screen corners (12-18% opacity)
- Opacity-controlled tinting for accent colors

## 2. Color Palette & Roles

### Primary
- **Paper Canvas** (`#d4e8e8`): Page background — pale cyan wash, the foundation.
- **Ink Blue** (`#2c3e3e`): Primary text, headings, dark button backgrounds, strokes. Not pure black — a teal-leaning dark that mimics real ink's blue-grey undertone.
- **Paper Card** (`#f0f6f4`): Card surfaces, AI avatar background. The lightest rice-paper white.

### Paper Tones (Canvas Layer)
- **Paper Canvas** (`#d4e8e8`): Page body background — the outer wash, visible outside the phone frame.
- **Paper Inner** (`#e8f2f0`): Phone frame **fallback** background color (used only when `style_1.jpeg` fails to load).
- **Paper Card** (`#f0f6f4`): Cards, containers, avatars — the brightest paper surface.
- **Paper Surface** (`#f5faf8`): AI message bubbles — pure, clean white for readability.
- **Paper Warm** (`#dce8e4`): Hover states, tool backgrounds, trace headers — subtle warmth.

### Ink Gradient (Text & Stroke Layer)
- **Ink Primary** (`#2c3e3e`): Headings, primary text, dark surfaces, bold strokes.
- **Ink Muted** (`#5a7272`): Secondary text, descriptions, captions.
- **Ink Faint** (`rgba(44,62,62,0.35)`): Placeholders, subtle borders.
- **Ink Ghost** (`rgba(44,62,62,0.12)`): Scrollbars, barely-visible overlays.

### Surface & Border
- **Border Passive** (`#c0d8d8`): Dividers, non-interactive separators — the faint wash line.
- **Border Interactive** (`rgba(44,62,62,0.35)`): Interactive boundaries, button outlines on hover.
- **Border Ink** (`#2c3e3e`): Hand-drawn strokes — bold, confident, defining.

### Accent (Floral & Nature)
- **Blossom White** (`#ffffff`): Primary decorative flower petals — the star motif.
- **Plum Pink** (`#c4a0a0`): Warm accent — progress fills, heart fills, Mochi skin.
- **Bamboo Green** (`#8aaa8a`): Life accent — success states, "done" nodes, activity icon.
- **Sky Blue** (`#a0c4d4`): Openness accent — tool nodes, info states.
- **Wisteria Purple** (`#b8a8c8`): Thought accent — thinking nodes, contemplation.

### Shadows
- **Card Shadow** (`2px 2px 0 rgba(44,62,62,0.15)`): Standard cards and containers.
- **Float Shadow** (`3px 3px 0 rgba(44,62,62,0.15)`): Elevated elements — traces, pet companion.
- **Button Shadow** (`2px 2px 0 var(--ink-primary)`): Primary dark buttons — bold displacement.

### CSS Custom Properties

```css
:root {
  --paper-canvas: #d4e8e8;
  --paper-inner: #e8f2f0;
  --paper-card: #f0f6f4;
  --paper-surface: #f5faf8;
  --paper-warm: #dce8e4;
  --ink-primary: #2c3e3e;
  --ink-muted: #5a7272;
  --ink-faint: rgba(44,62,62,0.35);
  --ink-ghost: rgba(44,62,62,0.12);
  --border-passive: #c0d8d8;
  --border-interactive: rgba(44,62,62,0.35);
  --border-ink: #2c3e3e;
  --accent-blossom: #ffffff;
  --accent-plum: #c4a0a0;
  --accent-bamboo: #8aaa8a;
  --accent-sky: #a0c4d4;
  --accent-wisteria: #b8a8c8;
  --shadow-card: 2px 2px 0 rgba(44,62,62,0.15);
  --shadow-float: 3px 3px 0 rgba(44,62,62,0.15);
  --shadow-btn: 2px 2px 0 var(--ink-primary);
}
```

## 3. Typography Rules

### Font Family
- **Calligraphic (Primary)**: `'Ma Shan Zheng', 'ZCOOL KuaiLe', 'Noto Sans SC', cursive` — brush-stroke personality for **all CJK text** across the entire UI (titles, pills, labels, timestamps, card text, inputs, message bubbles).
- **Latin Override (System Sans-serif)**: Via custom `@font-face`, Latin characters (U+0000–00FF etc.) in Ma Shan Zheng and ZCOOL KuaiLe are redirected to `local('Arial')` / `local('Helvetica Neue')`, ensuring English text renders in a clean sans-serif rather than calligraphy.
- **Monospace (Code)**: `ui-monospace, 'SF Mono', Menlo, monospace` — reserved exclusively for code blocks and terminal-style content.

> **Latin Override Mechanism**: Google Fonts' Ma Shan Zheng and ZCOOL KuaiLe include Latin glyph subsets rendered in calligraphy style, which makes English text difficult to read. We override these subsets with `@font-face` rules that use `local()` to map Latin characters to system sans-serif fonts. This is a global, zero-maintenance solution — no per-element inline styles needed.
>
> ```css
> @font-face {
>     font-family: 'Ma Shan Zheng';
>     src: local('Arial'), local('Helvetica Neue'), local('Helvetica'), local('Noto Sans');
>     unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA,
>                    U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122,
>                    U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD;
> }
> ```

### Hierarchy

| Role | Font | Size | Weight | Line Height | Letter Spacing | Notes |
|------|------|------|--------|-------------|----------------|-------|
| Display Hero | Ma Shan Zheng | 60px | 400 | 1.10 | normal | Page titles, brand moments |
| Screen Title | Ma Shan Zheng | 22px | 400 | 1.25 | 1px | Screen headers ("咪兔", "聊天记录") |
| Section Heading | Ma Shan Zheng | 48px | 600 | 1.00 | -0.5px | Feature section titles |
| Card Title | Ma Shan Zheng | 20px | 400 | 1.25 | normal | Card headings, journal titles |
| Body Large | Ma Shan Zheng | 18px | 400 | 1.38 | normal | Introductions, descriptions |
| Body | Ma Shan Zheng | 16px | 400 | 1.60 | normal | Standard reading text, message bubbles |
| Body Small | Ma Shan Zheng | 15px | 400 | 1.625 | normal | Compact message bubbles (`.msg-user`, `.msg-ai`) |
| Button | Ma Shan Zheng | 16px | 500 | 1.50 | normal | Button labels, tool pills, suggestion chips |
| Button Small | Ma Shan Zheng | 14px | 500 | 1.50 | normal | Compact buttons |
| Caption | Ma Shan Zheng | 12px | 400 | 1.50 | normal | Timestamps, metadata, tags, card descriptions |
| Tool Trace Body | Ma Shan Zheng | 12.5px | 400 | 1.65 | normal | Trace step descriptions (`.t-body-inner`) |
| Code | Monospace | 12px | 400 | 1.60 | normal | Code blocks only (`.t-code`) |

### Principles
- **Calligraphic unity**: Ma Shan Zheng is the single CJK typeface across the entire UI — screen titles, suggestion pills, tool drawer buttons, timestamps, journal card text, message bubbles, and input fields all share the same brush-stroke character. This creates a cohesive hand-written journal feel.
- **Latin separation**: English/Latin text automatically renders in system sans-serif (Arial) via `@font-face` Latin override — no per-element inline styles needed. This ensures English readability while preserving the calligraphic aesthetic for CJK text.
- **Normal tracking throughout**: The ink-wash system uses normal tracking at all sizes to maintain the flowing, brush-drawn aesthetic.
- **Three weights, clear roles**: 400 (body/UI), 500 (buttons/emphasis), 600 (headings). Weight 700 reserved for `font-bold` Tailwind utility only.
- **Monospace isolation**: Code blocks use `ui-monospace` exclusively — never mixed with calligraphic fonts.

## 4. Component Stylings

### Buttons

**Primary Dark (Ink Button)**
- Background: `var(--ink-primary)` (`#2c3e3e`)
- Text: `var(--paper-card)` (`#f0f6f4`)
- Padding: 8px 16px
- Radius: 10px (standard button)
- Shadow: `2px 2px 0 var(--ink-primary)` — bold ink displacement
- Active: scale(0.96) + reduced shadow
- Disabled: opacity 0.45, no transform
- Use: Primary CTA (send button, confirm actions)

**Tool Pill**
- Background: `var(--paper-card)`
- Text: `var(--ink-primary)`
- Radius: 10px
- Border: `2px solid var(--border-ink)`
- Shadow: `var(--shadow-card)`
- Active: scale(0.96) + `1px 1px 0 var(--ink-primary)`
- Hover: background shifts to `var(--paper-warm)`
- Use: Quick action pills, suggestion chips (font: Ma Shan Zheng via `.font-hand`)

**Ghost / Outline**
- Background: transparent
- Text: `var(--ink-primary)`
- Border: `1.5px solid var(--border-interactive)`
- Active: opacity 0.8
- Use: Secondary actions, close buttons

### Cards & Containers
- Background: `rgba(240, 246, 244, 0.90)` — semi-transparent paper card
- Border: `1.5px solid var(--border-ink)` (hand-drawn style)
- Radius: 16px (standard card), 10px (compact)
- Shadow: `var(--shadow-card)` — hard offset, no blur
- Hover: scale(0.98) + stronger shadow

### Message Bubbles

**User Message**
- Background: `rgba(44, 62, 62, 0.92)` — semi-transparent dark ink
- Text: `var(--paper-card)` — light paper
- Border: `rgba(44, 62, 62, 0.95)`
- Radius: 16px 16px 4px 16px (tail at bottom-right)
- Shadow: `1px 1px 0 rgba(44,62,62,0.2)`

**AI Message**
- Background: `rgba(245, 250, 248, 0.90)` — semi-transparent brightest paper
- Text: `var(--ink-primary)` — dark ink
- Border: `rgba(44, 62, 62, 0.6)`
- Radius: 16px 16px 16px 4px (tail at bottom-left)
- Shadow: `var(--shadow-card)`

**Note**: Message bubbles use 90-92% opacity to allow the watercolor background to subtly show through while maintaining text readability.

### Inputs & Forms
- Background: `var(--paper-card)`
- Text: `var(--ink-primary)`
- Border: `2px solid var(--border-ink)`
- Radius: 10px
- Focus: border stays `var(--ink-primary)`, shadow `1px 1px 0 var(--ink-primary)`
- Placeholder: `var(--ink-faint)`

### Reasoning Thread (Trace)
- Container: `var(--paper-card)` bg, `2px solid var(--border-ink)`, 16px radius, `var(--shadow-float)`
- Header: `var(--paper-warm)` bg, flex layout, cursor pointer, chevron toggle
- Step nodes (18px circles, `2px solid var(--border-ink)`):
  - `.think` → `var(--accent-wisteria)` (purple — contemplation)
  - `.tool` → `var(--accent-sky)` (blue — mechanical)
  - `.skill` → `var(--accent-bamboo)` (green — learned)
  - `.running` → `var(--paper-surface)` (white — in progress)
  - `.done` → `var(--accent-bamboo)` (green — complete)
- Code block: `var(--ink-primary)` bg, `var(--paper-warm)` text, 10px radius
- Dashed connector: `2px dashed rgba(44,62,62,0.30)`

### Progress Bar
- Track: `var(--paper-warm)` bg, `2px solid var(--border-ink)`, pill radius
- Fill: `var(--accent-plum)` — warm pink, pill radius

### Companion (Mochi)
- Skin: `var(--accent-plum)` fill
- Eyes/mouth: `var(--ink-primary)` stroke
- Container: `var(--accent-plum)` bg circle with ink border

## 5. Layout Principles

### Spacing System
- Base unit: 8px (consistent with original)
- Scale: 8px, 10px, 12px, 16px, 24px, 32px, 40px, 56px, 80px
- Phone frame: 390px × 844px (standard mobile viewport)
- Max height: 98vh on desktop, 100dvh on mobile (< 420px) — uses dynamic viewport height to avoid iOS Safari address bar clipping

### Grid & Container
- Phone frame: centered flex container with 40px border-radius
- Chat screen: flex column with header + scrollable messages + fixed input
- History screen: scrollable card list with search
- Bottom sheets: max 70% height, rounded top corners (20px radius)

### Whitespace Philosophy
- **Contemplative breathing**: Like ink-wash paintings that value empty space (留白), the layout uses generous padding (16px–24px) around content groups.
- **Content-driven rhythm**: Tight internal spacing within trace components (8px–12px) contrasts with wider message gaps (16px), creating a reading rhythm between focused detail and visual rest.
- **Section separation**: Dashed dividers (`2px dashed var(--border-ink)` at 0.3 opacity) mark temporal boundaries — like the creases in a folded scroll.

### Border Radius Scale
- Compact (10px): Buttons, inputs, small containers
- Card (16px): Standard cards, message bubbles, traces
- Container (20px): Bottom sheet top corners
- Frame (40px): Phone frame outer edge
- Circle (50%): Avatars, progress indicators
- Full Pill (9999px): Pills, icon buttons, toggles

## 6. Depth & Elevation

| Level | Treatment | Use |
|-------|-----------|-----|
| Flat (Level 0) | No shadow, paper background | Page surface, most content |
| Bordered (Level 1) | `1.5px solid var(--border-ink)` | Cards, containers, dividers |
| Elevated (Level 2) | `var(--shadow-card)` — 2px 2px 0 | Standard cards, message bubbles |
| Floating (Level 3) | `var(--shadow-float)` — 3px 3px 0 | Trace threads, companion pill |
| Overlay (Level 4) | `rgba(44,62,62,0.25)` semi-transparent | Bottom sheet overlays, dimming |
| Focus (Accessibility) | `3px solid var(--ink-primary)` outline, 2px offset | Keyboard focus ring |

**Shadow Philosophy**: The ink-wash depth system uses **hard-offset shadows with zero blur**, simulating the crisp shadow of objects resting on handmade paper. This creates a distinctly analog, tactile quality — elements feel physically placed rather than digitally floating. The consistent ink-blue tint (`rgba(44,62,62,0.15)`) unifies all shadows into the same tonal family as the borders and text.

### Z-index Scale

| Value | Use |
|-------|-----|
| `z-0` | Decorative overlays (`::before` pseudo-elements for ink-wash gradients, frosted glass) |
| `z-1` | Content children inside layered containers (tool drawer grid buttons) |
| `z-20` | Sticky headers (chat header, history header) |
| `z-30` | Dimming overlays (tool/companion backdrop) |
| `z-40` | Bottom sheets (tool drawer, companion panel) |

> Z-index values follow Tailwind's default scale. Keep at least 10 units of gap between layers to allow future insertions without renumbering.

### Decorative Depth Layers
- **Watercolor Background** (`style_1.jpeg`): Phone frame `background-image` with `background-size: cover`. Provides the primary artistic atmosphere — gradient blue wash with scattered white four-petaled flowers. Fallback: `var(--paper-inner)` (`#e8f2f0`) solid color + ink-wash CSS gradient overlay (`linear-gradient` with sky/plum/wisteria tones) that displays even when the image fails to load.
- **Tool Drawer Background** (`wallpaper.jpeg`): Tool drawer uses `wallpaper.jpeg` with `center/cover no-repeat`, plus a frosted overlay `rgba(212, 232, 232, 0.82)` via `::before` pseudo-element to match the header's frosted glass aesthetic.
- **Ink-Wash Gradients**: Dual radial gradients at screen corners via `::before` pseudo-elements:
  - Chat screen: bottom-left ink wash (`rgba(44,62,62,0.18)`) + top-right sky wash (`rgba(160,196,212,0.15)`)
  - History screen: top-right ink wash (`rgba(44,62,62,0.16)`) + bottom-left plum wash (`rgba(196,160,160,0.12)`)
- **Semi-Transparent UI**: All UI surfaces use `rgba()` backgrounds with 78-94% opacity to let the watercolor art show through:
  - Headers: `rgba(212, 232, 232, 0.82)` — frosted glass effect
  - Input areas: `rgba(212, 232, 232, 0.88)` — slightly more opaque for focus
  - Panels/drawers: `rgba(212, 232, 232, 0.94)` — near-opaque for content density
  - Message bubbles: 90-92% opacity — balance readability and background visibility
  - Cards: `rgba(240, 246, 244, 0.90)` — semi-transparent paper

## 7. Do's and Don'ts

### Do
- Use CSS custom properties (`var(--*)`) for all colors — never hardcode hex values
- Use `rgba()` backgrounds (78-94% opacity) for all UI surfaces to let the watercolor background show through
- Use `pointer-events: none` on all decorative overlay elements
- Include complete font fallback chains to prevent FOIT on slow connections
- Maintain `@font-face` Latin override rules for Ma Shan Zheng and ZCOOL KuaiLe — **never remove them**, as they prevent English text from rendering in calligraphy style
- Annotate all overrides with `/* was: ... */` comments for easy rollback
- Keep SVG pattern node count below 50 for rendering performance
- Use `currentColor` for inline SVG stroke/fill when possible
- Maintain all original JS-driven class names (`.screen-active`, `.hidden-sheet`, etc.)
- Provide `background-color` fallback alongside `background-image` for graceful degradation

### Don't❌ Don't use `backdrop-blur` — replace with semi-transparent solid colors for performance
- ❌ Don't use `transition: all` — specify exact properties (transform, background-color, box-shadow)
- ❌ Don't modify the original `lovable-chat-journal.html` file
- ❌ Don't hardcode colors in JavaScript templates — use Tailwind utility classes that reference CSS variables
- ❌ Don't use pure black (`#000000`) — the ink-blue (`#2c3e3e`) for warmth
- ❌ Don't use pure white (`#ffffff`) as a page background — the paper tones are intentional
- ❌ Don't use Gaussian blur shadows with blur — the system uses hard-offset only
- ❌ Don't increase decorative gradient opacity above 0.20 — content readability must be preserved (current max: 0.18)
- ❌ Don't remove `@font-face` Latin override rules — they are essential for English text readability
- ❌ Don't use per-element inline `font-family` overrides — the global `@font-face` Latin mechanism handles all elements automatically

## 8. Responsive Behavior

### Breakpoints
| Name | Width | Key Changes |
|------|-------|-------------|
| Mobile | < 420px | Full-screen mode, no phone frame border-radius/border/shadow |
| Desktop | ≥ 420px | Phone frame with 40px radius, ink border, offset shadow |

### Touch Targets
- Buttons: minimum 44px height (w-11 h-11)
- Pill buttons: generous padding (px-3 py-2) for comfortable tap
- Close buttons: 32px minimum (w-8 h-8)
- Companion toggle: full-width tap area on the pill

### Collapsing Strategy
- Phone frame: 390px fixed width → 100vw on mobile
- Border radius: 40px → 0 on mobile
- Box shadow: full offset → none on mobile
- Border: 1.5px ink → none on mobile
- Decorative layers: preserved at all breakpoints

### Accessibility
- `prefers-reduced-motion: reduce`: All animations disabled (slideUp, slideDown, fadeIn, popIn, gentleBounce, typing, cursorBlink, tSpin)
- Focus visible: 3px solid ink outline with 2px offset on all interactive elements
- Color contrast: `--ink-primary` on `--paper-canvas` = 8.2:1 (WCAG AAA)
- Color contrast: `--ink-muted` on `--paper-card` = 5.1:1 (WCAG AA)
- Viewport: `user-scalable` not restricted — allows pinch-to-zoom for visually impaired users
- Form inputs: All `<textarea>` and `<input>` elements have associated `<label>` with `.sr-only` visually-hidden class for screen readers
- Dynamic content: Messages area uses `role="log"` + `aria-live="polite"` so screen readers announce new messages
- Pet toast: Uses `role="status"` for screen reader announcements
- Global `button { cursor: pointer; }` ensures consistent pointer cursor on all interactive elements

## 9. Agent Prompt Guide

### Quick Color Reference
- Primary text/ink: `var(--ink-primary)` / `#2c3e3e`
- Background: `var(--paper-canvas)` / `#d4e8e8`
- Card surface: `var(--paper-card)` / `#f0f6f4`
- Muted text: `var(--ink-muted)` / `#5a7272`
- Border (bold): `var(--border-ink)` / `#2c3e3e`
- Border (subtle): `var(--border-passive)` / `#c0d8d8`
- Accent pink: `var(--accent-plum)` / `#c4a0a0`
- Accent green: `var(--accent-bamboo)` / `#8aaa8a`
- Shadow: `var(--shadow-card)` / `2px 2px 0 rgba(44,62,62,0.15)`

### Example Component Prompts
- "Create a message bubble with semi-transparent background: rgba(245,250,248,0.90) for AI or rgba(44,62,62,0.92) for user. Border: 1.5px solid rgba(44,62,62,0.6) or rgba(44,62,62,0.95). Radius 16px 16px 16px 4px (AI) or 16px 16px 4px 16px (user). Shadow: 2px 2px 0 rgba(44,62,62,0.15). Text at 15px Ma Shan Zheng weight 400, line-height 1.625, color #2c3e3e. English text auto-renders in Arial via Latin override."
- "Design a screen header: rgba(212,232,232,0.82) background, 22px Ma Shan Zheng title with 1px letter-spacing, ink-blue text (#2c3e3e). Include lucide icons (book-open, settings) at w-5 h-5. Bottom border: 2px solid var(--border-passive)."
- "Design a trace thread container: rgba(240,246,244,0.90) bg, 2px solid #2c3e3e border, 16px radius, 3px 3px 0 shadow. Header with rgba(220,232,228,0.92) bg. Step nodes as 18px circles: think=#b8a8c8, tool=#a0c4d4, skill=#8aaa8a, done=#8aaa8a. Dashed connector lines."
- "Build a tool drawer bottom sheet: rgba(212,232,232,0.94) bg, rounded top 20px, 1.5px solid #2c3e3e border-top. Tool grid 3 columns, each card semi-transparent paper-card bg with ink border. Hover shifts to paper-warm. 44px touch targets."
- "Create an input area: rgba(212,232,232,0.88) container bg, paper-card input bg, 2px solid #2c3e3e border, 10px radius. Placeholder at ink-faint opacity. Focus: border stays ink-primary, adds 1px 1px 0 ink-primary shadow. Font: Ma Shan Zheng 15px."
- "Design a companion panel: rgba(212,232,232,0.94) bg, Mochi avatar as plum-pink circle with ink-blue eyes/stroke. Status cards with ink border and card shadow. Progress bar: paper-warm track, plum-pink fill, pill radius."

### Iteration Guide
1. The phone frame background is `style_1.jpeg` (watercolor with flowers) — all UI surfaces must be semi-transparent to let it show
2. Use `rgba()` values for component backgrounds (78-94% opacity range) rather than solid CSS variables
3. All colors should still reference CSS custom properties for accent/border/shadow consistency
4. Use `var(--border-ink)` for bold strokes, `var(--border-passive)` for subtle dividers
5. Hard-offset shadows only — no Gaussian blur at any elevation level
6. Screen titles use Ma Shan Zheng at 22px with `letter-spacing: 1px` (`.font-ink-title` class); all other UI text also uses Ma Shan Zheng via `.font-hand` class
7. Ink-wash gradients use `::before` pseudo-elements on screens — keep `pointer-events: none` (opacity range: 12-18%)
8. Font stack: `'Ma Shan Zheng', 'ZCOOL KuaiLe', 'Noto Sans SC', cursive` for ALL text. Latin override via `@font-face` + `local('Arial')` ensures English renders as sans-serif. Monospace only for code blocks.
9. Maintain all original interaction class names to preserve JavaScript functionality
10. Annotate every override with its original value for easy rollback
