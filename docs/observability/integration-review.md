# Integration review (2026-10-28)

This temporary integration branch starts from observability PR
[#398](https://github.com/svenshi/oxidns/pull/398), commit
`30e982d55f57d5677003296b5edef379fc5ac049`.
It does not replace the installed Windows service.

## Other open pull requests

### #402: server fixes

Source: [SharerMax's PR #402](https://github.com/svenshi/oxidns/pull/402),
head `337c3eed428c7334cf240fc72db9268e798affda`.

Its eight functional commits were cherry-picked individually, preserving their
authors. Merging its head directly also imports the release branch and conflicts
with our recorder API and store. That unrelated release merge is excluded.

| Original commit | Change |
| --- | --- |
| [c555180a](https://github.com/svenshi/oxidns/commit/c555180a7734d6fa90c5eb84709210d626c24842) | TCP keepalive start time |
| [a5f9b67b](https://github.com/svenshi/oxidns/commit/a5f9b67b21df95fc1f33286d2e3602d54668a79c) | Track QUIC/H3 request tasks during shutdown |
| [2d90e6e6](https://github.com/svenshi/oxidns/commit/2d90e6e65eb9f121929582f9136c8e284e549b5b) | Refuse non-query ingress before execution |
| [8785686c](https://github.com/svenshi/oxidns/commit/8785686c99e99889b6f9ec15da3724b885e1125e) | Reduce malformed UDP log amplification |
| [5ab8ac57](https://github.com/svenshi/oxidns/commit/5ab8ac57a95ace6a79e6c522bc0e39e2d572d7f2) | Reject oversized TCP frame lengths |
| [4e927394](https://github.com/svenshi/oxidns/commit/4e927394a8eb54e68a6909e2e5082f94441435c1) | BADVERS for unsupported EDNS versions |
| [9591ba12](https://github.com/svenshi/oxidns/commit/9591ba12abca798fcbb90fe548be2654153689ca) | Honor explicit fallback threshold zero |
| [12cc5554](https://github.com/svenshi/oxidns/commit/12cc5554e1f015d2ce3ca6c2ebaa16d717ffc49a) | Validate UDP ingress before spawning |

The original PR has nine successful checks and one skipped nightly powerset
check at the reviewed head. Those results do not validate our combined branch.

### #404: liquid-glass WebUI

Source: [encounter0v0's PR #404](https://github.com/svenshi/oxidns/pull/404),
head `bc92361480b113c1ca0c3ca1b2b8bd7bb1d5be2c`.

Not imported in this integration. A direct merge conflicts in the sidebar and
also changes release workflows, release notes, and the package version. The
appearance could be ported independently, but the proposed dashboard has
demonstrable accounting problems:

1. `webui/components/dashboard/dns-overview.tsx:418` maps `error_count` to
   `blocked`. An upstream timeout or SERVFAIL is not evidence of a policy block.
   Line 389 similarly uses all error queries as the blocked-domain ranking.
2. Lines 84-97 initialize the weekly count from a process-lifetime counter on
   the browser's first visit. A process running since last week includes last
   week's requests in this week's count. If a saved browser returns after a
   week boundary, it instead starts at zero, omitting requests before the visit.
3. The key at line 69 is not scoped to a server endpoint. Changing endpoints in
   the same browser combines unrelated servers' cumulative counters.
4. Lines 248-250 fall back to metrics from every plugin when the selected
   plugin has no metrics. With the same upstream address in two forwarders,
   the first forwarder's counters can be attributed to the second.
5. Line 306 reports 100% success when no queries have been recorded. The
   success rate is unknown until at least one query is observed.

No checks were reported on that PR at review time. Our existing observation
page remains available, including actual upstream races, candidate IP timings,
query details, and topology.

## Open issues

All 18 open issue bodies were inspected. "Deferred" means not implemented by
this branch; it does not mean impossible.

| Issue | Decision |
| --- | --- |
| [#403](https://github.com/svenshi/oxidns/issues/403) | Await restoration before publishing the cache or starting persistence writers. Failed candidate initialization and later API-start failures use rollback cleanup without writing a pruned candidate cache over the old dump. A restore I/O failure now fails initialization rather than allowing an empty cache to overwrite the dump; missing dump files still start with an empty cache. |
| [#394](https://github.com/svenshi/oxidns/issues/394) | Deferred. Reverse IP search and bulk actions require API/UI contracts and separate behavior tests. |
| [#391](https://github.com/svenshi/oxidns/issues/391) | Deferred. Discovering DHCP-provided DNS independently of system settings needs platform-specific network integration and loop avoidance. |
| [#385](https://github.com/svenshi/oxidns/issues/385) | Cherry-picked the [upstream OpenWrt timezone fix](https://github.com/svenshi/oxidns/commit/9ab687bdf09a35b5a43785ef79305eb3d313accb); the issue does not identify its OS, so this cannot prove every reported timestamp mismatch is fixed. |
| [#375](https://github.com/svenshi/oxidns/issues/375) | Cherry-picked the author's [`has_cname` matcher](https://github.com/svenshi/oxidns/commit/185768c00e7113bb5d203194417b923f72313e3b). |
| [#374](https://github.com/svenshi/oxidns/issues/374) | Deferred. SNI probing requires a defined TLS validation and failure policy. |
| [#373](https://github.com/svenshi/oxidns/issues/373) | Deferred. An adaptive rule exporter is a new plugin/workflow. |
| [#372](https://github.com/svenshi/oxidns/issues/372) | Deferred. Learning registrable domains needs public-suffix semantics; truncating to the last two labels is incorrect for domains such as `example.co.uk`. |
| [#371](https://github.com/svenshi/oxidns/issues/371) | Deferred. Continuing after missing rules changes policy enforcement; do not silently disable configured rules. |
| [#370](https://github.com/svenshi/oxidns/issues/370) | Deferred. Executor load balancing is a new execution policy. |
| [#360](https://github.com/svenshi/oxidns/issues/360) | Deferred. DNSCrypt and stamps are new protocol support. |
| [#358](https://github.com/svenshi/oxidns/issues/358) | Deferred. Repository-wide module renaming does not fix the requested runtime behavior. |
| [#343](https://github.com/svenshi/oxidns/issues/343) | Partly covered by #398's actual upstream selection details. Dedicated policy-block counts still need explicit instrumentation; do not substitute DNS errors. |
| [#320](https://github.com/svenshi/oxidns/issues/320) | Cherry-picked [upstream hosts-format support](https://github.com/svenshi/oxidns/commit/9db9232679b3308198c7cc3c7b5dbdd0049b1554), addressing the format request only. HTTPS/SVCB handling is a separate behavior and must not be claimed fixed by a format parser change. |
| [#318](https://github.com/svenshi/oxidns/issues/318) | Deferred. VyOS integration needs a supported device/API and runtime validation. |
| [#308](https://github.com/svenshi/oxidns/issues/308) | Deferred. nftables timeout renewal requires Linux/kernel-backed tests. |
| [#232](https://github.com/svenshi/oxidns/issues/232) | Deferred. The historical benchmark cannot establish the current bottleneck; requires comparable load and response correctness measurements. |
| [#227](https://github.com/svenshi/oxidns/issues/227) | Deferred. Proactive prefetch is different from the existing refresh-on-stale-query behavior. |

## Validation

Combined-branch validation results are recorded after the checks complete.
Neither another author's successful CI nor the earlier #398 CI is a pass for
this branch.
