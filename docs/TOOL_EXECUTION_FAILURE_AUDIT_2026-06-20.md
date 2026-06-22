# Tool Execution Failure Audit — 2026-06-20

Scope: Cerebras `gpt-oss-120b`, ClawCodex runtime, repository tools, Windows launcher, and real filesystem writes.

## Ten Core Scenarios

| # | Failure scenario | Inspection result | Patch / evidence |
|---:|---|---|---|
| 1 | Provider returns a native structured `tool_calls` block | Already handled | Existing runtime tool-loop tests pass; the observed `RepoSearch` call executed structurally. |
| 2 | Model emits `{type:"tool",name,arguments}` as assistant text | Confirmed in session `session-1781952222780-0` | Model-gated exact-envelope recovery plus regression test. |
| 3 | Model emits `{tool,arguments}` as assistant text | Confirmed in `session-1781954161632-0` | Added second exact envelope and full permission/tool-loop test. |
| 4 | Model emits `{write_file:{...}}` singleton envelope | Confirmed by live validation | Added singleton tool-name recovery and regression test. |
| 5 | Tool JSON is fenced or `arguments` is itself a JSON string | Plausible provider formatting variant | Added exact-fence unwrapping and object-only argument decoding; tested. |
| 6 | Model prints a raw OpenAI `{type:"function",function:{...}}` envelope | Plausible compatibility variant | Added narrow function-envelope decoding; tested. |
| 7 | Tool-shaped JSON is malformed, contains extra fields, or is mixed with prose | Previously ended the turn as if complete | Malformed exact tool attempts now receive corrective feedback; unsafe/ambiguous envelopes remain non-executable; retry is bounded. |
| 8 | Model claims a file was created without any successful tool evidence | Confirmed in the original session | Mutation turns now reject common filesystem success claims until a non-error tool result exists. A failed or denied tool does not count as evidence. |
| 9 | Repository search returns a huge minified SVG/asset and exhausts context | Confirmed in `session-1781953200038-0` | Search excerpts capped at 600 characters; path-only SQL fetch capped at 4,096 characters; minified-asset regression passes. |
| 10 | Windows launcher loses a multi-word prompt or closes before an error can be read | Confirmed during validation | `run-claw.ps1` now uses a remaining-arguments parameter instead of incorrect splatting; launcher pauses after nonzero REPL exit. |

## Additional Failures Found During Live Validation

1. Cerebras rejected `is_error` on OpenAI-compatible tool-result messages with HTTP 400. `gpt-oss-*`, `zai-glm-*`, and `glm-*` now omit the unsupported field, with API translation tests.
2. The model shortened an explicitly requested absolute path on one attempt. The file tool itself supports absolute Windows paths with spaces; the final live request preserved `D:/Proj 1/index.html` and created it successfully. The incorrect validation artifact inside the repository was removed.

## Validation Evidence

- Runtime: 489 passed, 20 platform-specific tests ignored, 0 failed.
- Repo intelligence: 18 passed, 0 failed.
- Strict Clippy for affected crates: passed with warnings denied.
- PowerShell launcher parses and forwards `--version` correctly.
- Live Cerebras validation created `D:\Proj 1\index.html` through a real `write_file` tool result.
- Generated HTML contains a canvas, animation loop, keyboard controls, Pac-Man/ghost state, and balanced closing document tags.
- Extracted JavaScript passes `node --check`.

Browser loading of the local `file://` URL was blocked by the browser security policy, so no claim of visual browser rendering is made. Disk existence, tool provenance, structural HTML checks, and JavaScript syntax were verified independently.
