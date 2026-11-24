# ADR 0003: Local photo handling and bounded retention

Date: 2026-11-24
Status: Accepted for the engineering demo

## Context

The first slice must exercise private uploads without sending personal images to an unapproved provider. Browsers need access to previews while unrelated sessions must not be able to read each other's files.

## Decision

Accept a bounded set of image formats, inspect decoded content and magic bytes, bound dimensions and file size, and re-encode accepted uploads to remove EXIF metadata. Store normalized photos outside the public web directory. Use authenticated artifact/photo requests and browser object URLs instead of public raw-image URLs. Require explicit consent before submission and provide deletion.

Set a default retention period of 24 hours, configurable through `KEEPSAKE_RETENTION_HOURS`. Retention cleanup only runs while the local service is operating; it is not a hosted deletion scheduler. A stopped local app cannot perform filesystem cleanup. Use the synthetic fixture for routine testing.

The appearance adapter does not identify people, create embeddings, infer demographics or call an external model. It returns documented deterministic demo values and confidence/default metadata. Original photo bytes and owner credentials must not appear in application logs.

## Consequences

The demo can test authorization and consent boundaries locally. Internet-facing use requires additional deployment controls: authenticated accounts, TLS, external rate limiting, managed key rotation, durable scheduled deletion, storage permissions, audit retention policy and a reviewed processor agreement for any future model provider.
