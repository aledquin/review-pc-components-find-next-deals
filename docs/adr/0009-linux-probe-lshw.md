# 0009 - lshw-first Linux probe, `/proc` and `/sys` fallback

- Status: Accepted
- Date: 2026-04-17
- Deciders: @pca-team
- Tags: inventory, wave-2

## Context

The Wave 1 probe only supported Windows (WMI). Linux exposes hardware
information through multiple, partially-overlapping sources:

| Source       | Requires root | Coverage                                 |
| ------------ | ------------- | ---------------------------------------- |
| `lshw -json` | often         | CPU, GPU, RAM, storage, chassis          |
| `dmidecode`  | yes           | SMBIOS (socket, chassis, BIOS)           |
| `/proc`      | no            | CPU only                                 |
| `/sys`       | no            | drives, block devices, PCI hierarchy     |
| `lspci`      | no            | PCI tree (GPU identification)            |

## Decision

Primary source is `lshw -json`. When its output is empty or lacks a kind we
fall back to `/proc/cpuinfo` (CPU), `/proc/meminfo` (RAM totals), and later
`lspci` for GPUs. Every shell-out routes through a single injectable
``CommandRunner`` so unit tests never touch the host.

## Consequences

Positive:

- 95%+ of modern distros ship `lshw`; single call gives us almost everything.
- Fallbacks keep the probe useful on stripped images where `lshw` is absent.
- Tests are pure-function, driven by JSON fixtures in `tests/data/`.

Negative:

- Users without root get a partial snapshot. We surface this in the CLI.
- `lshw` field names have drifted between major versions; we rely on
  `children[]` walks rather than positional indexing to absorb that drift.

## Alternatives considered

- **dmidecode as primary**: requires root and is restricted to SMBIOS data.
- **Pure `/proc` + `/sys`**: forces us to re-implement vendor/model parsing
  per device class.
- **Python bindings (py-lshw, hwinfo)**: unmaintained.
