# File transfer integrity receipt

`tools/transfer_integrity.py` supplies the transport-independent proof layer for #394 file delivery. Create a receipt beside the source before transfer, then verify the received bytes at the destination. A transfer is `PROVEN` only when byte size and SHA-256 both match.

```powershell
python tools/transfer_integrity.py create artifact.mp4 --output artifact.receipt.json
# move the artifact and receipt through the selected PC -> ChatGPT or ChatGPT -> PC route
python tools/transfer_integrity.py verify received-artifact.mp4 --receipt artifact.receipt.json
```

The receipt intentionally contains only schema, filename, byte size, and SHA-256; it does not persist machine-local paths or credentials. This proves byte-for-byte delivery only. It does not prove that a media file is playable, visually correct, or user-visible in ChatGPT.
