# ADR 0004: Shared semantic CSS and accessible primitives

Date: 2026-11-24
Status: Accepted for the first slice

The handoff specifies the Soft Keepsake Editorial palette, Fraunces/DM Sans, semantic tokens and reusable UI primitives. It suggests Tailwind/shadcn with Radix as a baseline. This implementation uses the supplied CSS custom properties directly with a shared component package, Lucide icons and Radix Dialog for dialog interaction. It uses Three.js directly for the viewer.

This reduces styling and 3D wrapper dependencies while preserving the same visual contract and React/TypeScript architecture. New styles must reuse semantic tokens. The `/design-system` gallery documents the actual primitives. The source checker covers token usage, focus styles, reduced motion, responsive rules and image alt attributes; browser checks supply the interaction and layout evidence. Source checks are not a substitute for full accessibility conformance testing.
