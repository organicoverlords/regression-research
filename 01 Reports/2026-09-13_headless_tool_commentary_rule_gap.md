# Headless tool commentary rule gap

Status: bounded shared-behavior regression evidence; owner is agents#402.

## Failure boundary

The system already requires output-lean final replies and concise announce-before-act notices for visible foreground UI interaction, but ordinary background/headless terminal, file, process, API, and tool calls had no explicit chat-surface boundary. That gap allowed repeated “checking now / next I will / tool result” narration between routine calls, turning deep research into a user-visible process transcript.

## Supported correction

Ordinary headless execution should be silent in chat by default. Intermediate assistant commentary is justified only when it changes what the user needs to know or do, such as a required clarification or permission, a material blocker/decision, or the existing foreground notice. Client-rendered/collapsed tool-status metadata is a separate UI surface and is not a reason to duplicate the chronology in prose.

## Regression scope

This contract does not reduce research depth, hide material blockers, suppress required foreground notices, or treat the client tool UI itself as assistant narration. It prevents routine headless progress narration from displacing the result.
