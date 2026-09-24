# PaperLab Interface System

## Direction

- **Personality:** Data & Analysis with a quiet paper-lab identity
- **Foundation:** Warm neutral with cool ink and restrained evergreen accents
- **Depth:** Borders-only; raised surfaces are reserved for active controls

## Tokens

### Spacing
- **Base:** 4px
- **Scale:** 4, 8, 12, 16, 24, 32, 48

### Colors
```css
--ink: #182522;
--muted: #68736e;
--canvas: #f4f6f3;
--surface: #ffffff;
--line: #dfe6e1;
--accent: #167b62;
--accent-soft: #e5f3ed;
--warning: #a66b15;
--danger: #a84d48;
```

### Radius
Scale: 8px, 12px, 16px

### Typography
- **Font:** Geist Sans, system sans fallback
- **Scale:** 12, 13, 14, 16, 18, 24, 32
- **Weights:** 400, 500, 600, 700

## Patterns

### Button Primary
- Height: 40px
- Padding: 12px 16px
- Radius: 8px
- Usage: one clear primary action per view

### Card Default
- Border: 1px solid `--line`
- Padding: 20px
- Radius: 12px
- Background: `--surface`

## Decisions

| Decision | Rationale | Date |
|---|---|---|
| Quiet warm canvas with evergreen accents | Supports dense financial data without resembling a trading terminal | 2026-09-23 |
| Borders-only surfaces | Keeps hierarchy clear and makes tables and traces easy to scan | 2026-09-23 |
| Labels always identify DEMO or PAPER | Prevents synthetic sample evidence from being mistaken for external market results | 2026-09-23 |
| One pilot screen with the virtual balance as the focal point | Keeps the five-day question, observed result, and limits legible without mixing the synthetic A/B/C demonstration into the main flow | 2026-09-24 |
