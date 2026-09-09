---
name: Kinetic Institutional SaaS
colors:
  surface: '#f7f9fb'
  surface-dim: '#d8dadc'
  surface-bright: '#f7f9fb'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f2f4f6'
  surface-container: '#eceef0'
  surface-container-high: '#e6e8ea'
  surface-container-highest: '#e0e3e5'
  on-surface: '#191c1e'
  on-surface-variant: '#464555'
  inverse-surface: '#2d3133'
  inverse-on-surface: '#eff1f3'
  outline: '#777587'
  outline-variant: '#c7c4d8'
  surface-tint: '#4d44e3'
  primary: '#3525cd'
  on-primary: '#ffffff'
  primary-container: '#4f46e5'
  on-primary-container: '#dad7ff'
  inverse-primary: '#c3c0ff'
  secondary: '#565e74'
  on-secondary: '#ffffff'
  secondary-container: '#dae2fd'
  on-secondary-container: '#5c647a'
  tertiary: '#3130c0'
  on-tertiary: '#ffffff'
  tertiary-container: '#4b4dd8'
  on-tertiary-container: '#d9d8ff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#e2dfff'
  primary-fixed-dim: '#c3c0ff'
  on-primary-fixed: '#0f0069'
  on-primary-fixed-variant: '#3323cc'
  secondary-fixed: '#dae2fd'
  secondary-fixed-dim: '#bec6e0'
  on-secondary-fixed: '#131b2e'
  on-secondary-fixed-variant: '#3f465c'
  tertiary-fixed: '#e1e0ff'
  tertiary-fixed-dim: '#c0c1ff'
  on-tertiary-fixed: '#07006c'
  on-tertiary-fixed-variant: '#2f2ebe'
  background: '#f7f9fb'
  on-background: '#191c1e'
  surface-variant: '#e0e3e5'
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 36px
    fontWeight: '700'
    lineHeight: 44px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.05em
  label-sm:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 14px
  headline-lg-mobile:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  unit: 4px
  container-padding: 24px
  gutter: 16px
  stack-sm: 8px
  stack-md: 16px
  stack-lg: 32px
---

## Brand & Style

The design system centers on a "Premium Utility" aesthetic, blending the high-end polish of modern fintech with the rigorous functionality required for educational administration. The brand personality is authoritative yet frictionless—positioning the software as a sophisticated tool that values a user's time and intelligence.

The visual style is **Corporate Modern** with a focus on high-clarity information density. It utilizes a structured sidebar-to-canvas architecture. The interface creates a sense of security and speed through ample whitespace, precision-engineered typography, and a "Glass-Canvas" approach where overlays use subtle backdrop blurs to maintain context without visual clutter.

## Colors

The palette is anchored by **Indigo (#4F46E5)** for primary actions and brand presence. The interface utilizes a high-contrast structural split: 
- **Deep Slate/Charcoal (#0F172A)** is reserved for persistent navigation elements (sidebars) to provide a grounded, professional frame.
- **Crisp White (#FFFFFF)** and **Slate-50 (#F8FAFC)** serve as the primary canvas for content, ensuring maximum legibility of data tables and attendance rosters.

Status indicators are highly semantic to allow for "at-a-glance" auditing:
- **Success Emerald** for "Present"
- **Danger Rose** for "Absent"
- **Warning Amber** for "Late"
- **Info Sky** for "Manual override"
- **Violet** for "Suspicious activity"
- **Slate-500** for "Cooldown/Neutral states"

## Typography

This design system utilizes **Inter** exclusively to leverage its exceptional legibility in data-heavy environments. The hierarchy is characterized by tight letter-spacing on headlines to create a "compact" premium feel, and generous line-heights for body text to ensure ease of reading during long administrative sessions. 

All labels and captions use a slightly increased font weight (Medium/Semi-bold) to ensure they are distinct from primary body content. Use uppercase sparingly for section headers to provide structural rhythm.

## Layout & Spacing

The layout follows a **12-column fluid grid** for the main content area, while the primary navigation is a fixed 280px sidebar. 

- **Spacing Rhythm:** Based on a 4px baseline grid. Most components use 16px (4 units) or 24px (6 units) of internal padding.
- **Desktop:** 24px margins with 16px gutters between cards.
- **Tablet:** 16px margins; the sidebar may collapse into an icon-only rail (72px).
- **Mobile:** Single column layout with 16px margins. Headers and large data tables should transition to card-based views or horizontal-scroll lists to maintain accessibility.

## Elevation & Depth

Hierarchy is established through **Tonal Layering** supplemented by **Soft Shadows**.

1.  **Background Layer:** Slate-50 serves as the base.
2.  **Surface Layer (Cards):** Pure White (#FFFFFF) with a 1px border in #E5E7EB. Shadows are highly diffused (Y: 4px, Blur: 6px, Opacity: 0.05, Color: #0F172A).
3.  **Overlay Layer (Modals/Dropdowns):** Uses a Glassmorphism effect with a `backdrop-filter: blur(8px)` and a semi-transparent white background (80% opacity). This maintains the user's focus on the workflow while acknowledging the underlying state.

Avoid heavy shadows or dark outlines. Depth should feel "airy" and intentional.

## Shapes

The design system uses a "Rounded-Refined" language. 
- **Cards/Containers:** Use `rounded-lg` (16px) to soften the density of data-heavy screens.
- **Input Fields/Buttons:** Use `rounded-md` (8px) for a more precise, clickable feel.
- **Status Badges/Chips:** Use `rounded-full` (pill-shaped) to distinguish them from actionable buttons and interactive cards.

## Components

### Buttons
Primary buttons use the Indigo background with white text. Hover states should darken the Indigo slightly. Ghost buttons use a 1px border (#E5E7EB) and Slate-700 text.

### Cards
All cards must have a 1px border (#E5E7EB) and the standard soft shadow. Header sections within cards should be separated by a subtle horizontal rule.

### Status Chips
Status chips are small, high-contrast indicators. Use a light background (10-15% opacity of the status color) and a dark, bold version of the same color for text.

### Input Fields
Inputs must have a height of 40px, a 1px border (#E5E7EB), and use the `body-md` type level. Focused states should use a 2px Indigo ring with 0.15 opacity.

### Attendance List
Row items should have a hover state of Slate-50. Include a vertical "status bar" (4px width) on the far left of each row to reinforce the attendance state through color.

### Data Tables
Headers should be `label-md` in Slate-500. Row borders should be 1px solid Slate-100. Use fixed headers for long attendance rosters.