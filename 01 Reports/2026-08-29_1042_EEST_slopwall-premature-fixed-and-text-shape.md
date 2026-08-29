# Slopwall incident: premature fixed claim and text-shape failure

Date: 2026-08-29

The assistant said the fresh-session behavior was fixed after checking policy text and hook wiring, without proving the behavior in a genuinely fresh harness session. The supplied Claude transcript showed that bootstrap and policy were loaded but Claude still asked the operator to clarify, so the end-to-end claim was not proven.

The response shape was also a direct failure. A tiny status question received a long, heavily structured answer using bullets, arrows/flow formatting, repeated explanation, and multiple paragraphs. The operator described it as nauseating and specifically objected to turning a small "fixed" message into roughly two pages.

This was not caused by a missing presentation rule. `mem-20260829-b53668c4` already required ordinary chat to be compact, cohesive, direct, decision-useful, and to avoid the rejected arrow glyph. The assistant failed to obey that rule. The correction therefore tightens the existing rule rather than adding another parallel rule.

Verbatim operator corrections preserved for this incident:

`slopwall`

`your wall of text also makes me nauseous`

`no you must write the report and make sure everyone knows that the report is also about the shape of the text you are using the arrrows and bulletpoints in a tiny "fixed" message that is 2 pages long`

`IT SHOULD ALREADY BE A RULE FOR FUCKS SAKE DONT REWRITE EVERYTHING`

`REPORT THE FUCKING INCIDENT AND WRITE A MEMORY ABOUT HOW YOU ARE CHANGING THE RULE BECAUSE YOU COULD NOT FOLLOW IT AT ALL DO NOT FUCKING GO AND EDIT EVERYTHING AS YOU WANT`

Required correction: for ordinary yes/no, status, or small clarification answers, lead with the answer and keep the response to one short paragraph by default. Do not use bullets, headings, arrows, flow diagrams, or explanatory scaffolding unless the task genuinely requires structure or the operator asks for it. When claiming a behavioral fix, distinguish policy/configuration presence from end-to-end replay evidence. A configuration check alone does not justify saying the behavior is fixed.
