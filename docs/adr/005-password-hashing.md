# ADR-005: Password Hashing — argon2-cffi (Argon2id)

**Status**: Accepted | **Date**: 2026-06-06

## Context
OWASP 2024 recommends Argon2id as the primary choice for new systems.

## Decision
Use `argon2-cffi` library with `PasswordHasher()` defaults (memory-hard, time-hard). bcrypt is explicitly excluded.

## Consequences
- Stronger resistance to GPU/ASIC brute-force than bcrypt
- password_hash never exposed in API responses or logs
