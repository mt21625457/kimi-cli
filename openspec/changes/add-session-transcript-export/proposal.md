# Proposal: Session Transcript Export

## Change ID
add-session-transcript-export

## Summary
Add first-class support for exporting a Kimi CLI session transcript (chat history, tool
invocations, metadata) to Markdown or JSON so users can share or audit completed runs.

## Why
- Engineers need to attach AI collaboration history to tickets, compliance logs, or handoffs.
- Today users must copy/paste terminal output, which loses structure and tool context.
- Formalizing the capability clarifies how the agent stores, sanitizes, and surfaces transcript
  data for downstream tooling.

## What Changes
- Define a new `session-transcript` capability describing export formats, metadata, and privacy
  requirements.
- Extend the CLI shell UI with an `export-transcript` command (and Print mode flag) that writes a
  file to the workspace.
- Teach `KimiSoul` to produce a normalized transcript artifact (messages, tool calls, tokens,
  redacted secrets) for consumption by the UI layer.

## Impact
- Users can reliably capture collaboration history for audits and async reviews.
- Tool builders can pipe transcripts into other systems without scraping terminal history.
- Slight increase in disk writes per session when exports are triggered.

## Open Questions
1. Should transcripts include raw tool stderr/stdout or only summaries?
2. What retention policy should apply to generated transcript files?
