---
id: m-18
title: "m-18: Zero-friction install — curl bootstrap + prebuilt artifacts"
---

## Description

Kill installation friction: curl bootstrap that provisions its own dependencies (zellij, Python >=3.11 standalone) and fetches the prebuilt WASM plugin from GitHub Releases. Public tracking: GH epic #348 + sub-issues #349-356. Replaces the npm channel of epic #97 per 2026-09-19 decisions; CLI unification descoped out (stays parked in m-14/#97). Targets Linux + macOS; WSL deferred to spike #356.
