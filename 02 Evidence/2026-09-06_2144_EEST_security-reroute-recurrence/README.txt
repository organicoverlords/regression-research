21:44 EEST recurrence evidence

Two user screenshots were copied byte-for-byte from the local Windows Screenshots folder and hash-verified against the uploaded images.

Exact caller evidence:
- 11 raw start_process receipts preserved for 21:40:00-21:46:30 EEST.
- 22 MCP tool calls recorded in 21:42-21:46 EEST transport slice: 8 start_process, 14 read_output.
- Full start_process command strings are preserved in raw receipts and exact-tool-calls-1842-1846Z.*.
- read_output calls preserve request id, process id and requested wait_ms from transport events.

Temporal correlation:
- Screenshot 21:44:39.301 occurred while read_output request ddea9565-3965-4164-bc79-4febbeb19505 was waiting on process 208be867-907a-407f-9923-b1d2cd326af6.
- That read_output completed 21:44:45.802.
- Screenshot 21:44:46.291 occurred after completion and before the next read_output began at 21:44:48.721.
- No causal attribution is made.
