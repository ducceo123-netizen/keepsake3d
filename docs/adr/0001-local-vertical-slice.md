# ADR 0001: An executable local vertical slice

Date: 2026-11-24
Status: Accepted for the engineering demo

## Context

The handoff specifies a Next.js storefront, FastAPI service, private photos, asynchronous Blender work and revision-bound approvals. It suggests Postgres/Supabase and Redis/Celery for deployment. The supplied package contains specifications and concept art, but no application, credentials, commercial master, print profile or physical sample.

## Decision

Use Next.js/TypeScript for the storefront and FastAPI/Pydantic for the API. Run the first slice with SQLite and filesystem storage under a private, ignored data directory. A bounded local executor schedules Blender subprocesses. Keep the design/appearance contracts separate from HTTP handlers. Include a Postgres-compatible migration as a deployment starting point; the local app does not connect to Postgres or Redis.

The local owner token is an opaque bearer credential whose hash is stored server-side. Every private photo, status and artifact request must pass a session ownership check. The operator token is a separate, explicitly configured credential. Customer preview approval never authorizes production.

## Consequences

A developer can run the fixture-to-preview path without hosted services or paid accounts. SQLite and the in-process queue are not a multi-instance production architecture. Process restarts can interrupt work; recovery must preserve an honest failed/retryable state rather than fabricate completion. A production port needs durable queue acknowledgements, transactional scheduling, isolated render workers, managed private object storage and a real identity system.

This is an explicit local-demo deviation from the suggested Postgres/Redis/Celery stack, not a claim of equivalent production behavior.
