# Label Printer: the MakeID BLE protocol

Worked out from the MakeID-Life Android app (2.2.0) and checked on an E1 (protocol version 1.30, 96-dot head,
170 rows per chunk): test labels and a ruler printed correctly.

## Transport
- BLE service `0000abf0-0000-1000-8000-00805f9b34fb`
  - write `abf1` (write without response), notify `abf2`
  - older printers: service `49535343-fe7d-4ae5-8fa9-9fafd205e455`, write `49535343-8841-...`, notify `49535343-1e4d-...`
- Split writes to MTU-3 (20 bytes at the default MTU). Wait for the reply after each packet.
- Reply notifications may start with `23 23 xx xx` (4 bytes) -> strip. Reply = `66 len_lo len_hi cmd ...`.
- Checksum (last byte of every packet) = (0 - sum of all previous bytes) & 0xFF.

## Status `66 06 00 10 00 84`
E1 reply (44 bytes): `66 2c 00 10 00 3c 18 0f 3b 01 45 31 ... 01 00 01 1e 01 0c 00 aa 00 71`
- [4] status: 0 = OK; bit7 = wait; bit6 = resend; other low-6-bit values = error codes (no tape, cover open...)
- [6] & 7 = DPI (0 = 203)
- [10..11] model "E1"
- [35] bit7 = printing; bits5-6: 1 pause, 3 cancel
- [36].[37] = protocol version (E1: 1.30). >= 1.3 means the New Protocol below
- [38] & 3 = position (1 = centre), bit2 = swap byte pairs (E1: 0)
- [39..40] = head width in bytes (E1: 12 = 96 dots = 12 mm)
- [41..42] = max rows per chunk (E1: 170)

## Print: one `0x1B` frame per chunk
```
66 LL LL 1B  DK CT  TT TT  CC CC  01  RR RR  NN NN  RM 00  <LZO1X data>  CK
```
- LL LL: total frame length (LE) = 17 + data + 1
- DK: darkness (1-31, the app uses 15) | 0x20 (gap / die-cut mode "ddf"); continuous = no bits
- CT: cut type & 7 | save type << 3 (the app uses 0x03)
- TT TT: total labels in the job; CC CC: this label's number (from 1)
- RR RR: total rows of this label (length in dots, 8 dots per mm)
- NN NN: rows in this chunk (<= max rows); RM: chunks remaining after this one
- Image: label rotated so each row runs across the head; 1 bit per dot, MSB = first dot, black = 1;
  head-width bytes per row; LZO1X-1 compressed per chunk. A literal-only LZO stream
  (`17+n` or `00 ..` length, raw bytes, then `11 00 00`) is valid and is what we send.
- The reply to every frame is a status (see above); continue when [4] == 0.

## Older protocol (< 1.3, "Common") - not used by the E1
`66 04 AE ck` ready; `66 0A AA left/8 top(2) bytesPerRow height(2) ck` block; `66 AB len(2) raw rows` data;
`66 09 AD count(2) copies(2) last ck` print.
