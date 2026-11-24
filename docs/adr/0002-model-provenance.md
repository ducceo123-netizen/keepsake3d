# ADR 0002: Model-derived artifacts and explicit production gates

Date: 2026-11-24
Status: Accepted

## Context

The Better Together image establishes art direction. It is not a source mesh, a dimensioned drawing, an approved physical product or proof of a mating connector. Approval must refer to the actual generated revision.

## Decision

Use a checked-in procedural Blender implementation to create a versioned demonstration master. The worker loads that master, applies only validated parameters, and exports GLB, STL and PNG from the configured scene. Record the master hash, parameter hash, revision, Blender version, script provenance and artifact hashes. Compare locked geometry and transforms before and after permitted changes.

Keep the image visibly labeled as concept art. Label procedural output as an engineering demo. Keep appearance extraction deterministic and visibly mocked. An absent or failing Blender executable is an actionable failure; it must never produce a fake successful model.

Treat geometric tests, slicer validation, physical sample validation and production authorization as separate outcomes. The local customer action approves only a specific preview revision and checksum. No live cart, payment, supplier routing or production approval is implemented.

## Consequences

The output files are genuine digital artifacts. Their existence does not establish commercial likeness, printable assembly, stability, clearance, thickness, finish or manufacturing suitability. STL carries geometry without the GLB's color materials. The unvalidated demo geometry and labels must not be represented as an approved manufacturing design.

An authored commercial master, engineered feature envelopes, printer/material profile, slicer pass, physical sample and explicit production signoff remain required before a commercial launch.
