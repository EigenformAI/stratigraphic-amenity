# Security Policy

## Supported Versions

Security fixes are provided for the latest `0.1.x` release. Pre-release code on
the default branch may change without notice and is not a supported release.

| Version | Supported |
| --- | --- |
| 0.1.x | Yes |
| Earlier versions | No |

## Reporting a Vulnerability

Do not open a public issue or discussion for a suspected vulnerability. Use
GitHub's
[private vulnerability reporting](https://github.com/EigenformAI/stratigraphic-amenity/security/advisories/new)
to send the maintainers a confidential report.

Include the affected version or commit, installation profile, impact,
reproduction steps or proof of concept, and any suggested mitigation. Redact
maps, credentials, filesystem paths, and provider responses that contain
sensitive information.

Maintainers aim to acknowledge a report within three business days and provide
an initial assessment within ten business days. Timing for a fix and disclosure
depends on severity and coordination needs. Reporters will receive material
status updates through the private advisory. Please allow a fix to be prepared
before public disclosure.

## Security Model

Stratigraphic Amenity is a local Python SDK and stdio MCP server, not a sandbox
or a hardened multi-tenant service. Hosts should grant the process only the
filesystem access and network credentials it needs.

Relevant trust boundaries include:

* Allowed filesystem roots reduce accidental access, but host permissions are
  the security boundary. Symlinks, map paths, cache roots, and generated
  resources should be treated as security-sensitive inputs.
* MCP messages, map images, metadata, SVG, and provider responses are untrusted
  input. Clients must not execute returned text or render active content in an
  unsafe context.
* Large images, complex geometries, and provider responses can consume
  significant CPU, memory, disk, or network capacity. Apply process and host
  resource limits for untrusted workloads.
* Network providers are explicit opt-ins. Credentials belong in the process
  environment or host credential mechanism, never in maps, prompts, logs,
  repository files, or issue reports.
* `geomap_prepare_detectors` and `geomap_prepare_knowledge` are exposed by default and can be
  disabled independently by the operator. They authorize model-triggered bandwidth and disk use
  for fixed immutable manifest entries only. They accept no URLs, paths, asset IDs, package names,
  or force option and never run `pip`, `uv`, `apt`, or a shell. Apply host resource limits and
  require client-side confirmation before invoking either tool.
* MCP protocol traffic uses stdout. Diagnostics belong on stderr; exposing
  protocol traffic or logs can disclose request content and resource handles.
* `geomap://` identifiers are opaque references, not authorization tokens.
  Anyone with access to the same server process may be able to request a known
  resource identifier.

The first public release does not provide a remote HTTP transport. Deploying
the stdio server behind a network service requires a separate authentication,
authorization, origin-validation, isolation, and tenancy design.

Optional detector and knowledge assets are installed outside the Python distribution from
attributed manifest sources. Archive/tree digests and extraction-size limits are enforced before
atomic installation. Report archive extraction, checksum, path handling, and managed
runtime loading issues here. Vulnerabilities in the AGPL Ultralytics runtime, model weights, or
upstream data should also be reported to the component's source maintainer when appropriate.
