# M2.2 quarterly pilot-universe coverage

Run: `20260906T061523076221Z`. 392 historical CSI300 members; 2015–2016 only.

All fiscal requests span 2013Q3–2016Q3. Publication must be strictly before the signal date; publication age <=400 and fiscal age <=550 days. Membership is historical and date-specific.

| field     |   year |   eligible_cells |   available_cells |   coverage |
|:----------|-------:|-----------------:|------------------:|-----------:|
| roeAvg    |   2015 |            73200 |             73137 |   0.999139 |
| roeAvg    |   2016 |            73200 |             73143 |   0.999221 |
| npMargin  |   2015 |            73200 |             73137 |   0.999139 |
| npMargin  |   2016 |            73200 |             73143 |   0.999221 |
| YOYNI     |   2015 |            73200 |             73137 |   0.999139 |
| YOYNI     |   2016 |            73200 |             73143 |   0.999221 |
| YOYAsset  |   2015 |            73200 |             72548 |   0.991093 |
| YOYAsset  |   2016 |            73200 |             72652 |   0.992514 |
| YOYEquity |   2015 |            73200 |             72548 |   0.991093 |
| YOYEquity |   2016 |            73200 |             72652 |   0.992514 |

Accepted records: 9896; quarantined: 0.

Candidates fixed before collection: Quality +roeAvg, Growth +YOYNI, Investment -YOYAsset. Existing BP is the Value reference. Coverage is a data gate, not factor acceptance; no return-based results were calculated.

## Limits

- Vendor historical revisions are unknown; publication alignment does not reconstruct historical vintages.
- ROE is the vendor reporting-period ratio, not an independently reconstructed TTM ROE. Fiscal-period mixing and restatement risks need sensitivity checks.
- Asset growth is an investment proxy; financial firms and corporate actions may make it incomparable.
- Missing newest report fields remain missing. Invalid/ambiguous records are quarantined; no zero-fill or backdated publication.
- This completes collection for the pilot universe, not the full 2008–2020 research history or M2. No qualification/lockbox access.
- Next: evaluate the three frozen candidates against BP and the technical reference on this observed history; expand quarterly history before rolling-model claims.
