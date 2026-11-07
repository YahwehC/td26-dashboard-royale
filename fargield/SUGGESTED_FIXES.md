# Suggested fixes to the submission (from a read-through of main @ 011244b)

Findings below are from reading the reports and write-up, not from re-running the pipeline.

## 1. Baseline comparison is selective (WRITEUP.md, Model paragraph)
The write-up compares the model only to raw house win (11.7% relative error). The stronger baseline,
`B_theo_rate`, gets 3.8% and the model beats it on relative error (-0.70 pts, CI -0.95 to -0.47), but the
model LOSES on absolute error (MAE 1.26 vs 1.06; model minus baseline +0.21, CI +0.16 to +0.25).
Both numbers are in `docs/evidence/model_report.md`, so a judge can see the omission. Name the stronger
baseline and state both results.

## 2. Use the same-slot swap as direct evidence against replacing machines
M-1120 (Royal Draw, slot L-38-5) retired 2025-05-13; M-5076 (same game G-VID95, same slot) was installed
that day. Theo/day: $143 vs $153. Only 49 days, so caveat it. See `fargield/NOTES.md`.

## 3. Plan risk (not in the write-up)
- Most of the benefit rests on the $15k promotion. "Promotion flops, others MID" returns $16.4k vs $23.7k cost.
- Signs at LOW effect return $2.7k vs a $7.5k cost.
- A promotion doesn't answer the GM's machine question; say why it is funded.

## 4. Closure caveat
The traffic table shows Bar up ~15% and Entrance down ~14% during the closure (Pit flat), so some Back Forty
traffic may have shifted to Bar and the rest-of-floor control is not perfectly clean. "Never fully recovered"
(0.669 to 0.643) may be partly seasonal since the rest of the floor also softened.

## 5. Word count
Previous WRITEUP.md was 399 words; adding items 1 and 2 pushes it over 400. `WRITEUP.suggested.md` has
both added and is trimmed to fit (check the count yourself before pasting). The trims are: the
"Priced and rejected" line, the card-holder-losses sentence, and "possibly more carding, not more play".
Keep any of those back if you prefer and cut elsewhere.

## 6. Minor
EV-EDC25 shows `announced 2024-05-20` in the Model B event table, a year before the event. Probably a data
quirk; check before citing.
