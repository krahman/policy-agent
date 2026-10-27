# Judge calibration sheet (blind)

Answers from experiment E5. Your labels decide whether the LLM judge's scores can be trusted, so please do
this yourself and tick one box per item; leave a box empty if you cannot tell. The judge's verdicts are hidden on purpose.

**For each claim:** is it supported by the evidence shown under it? Check the measure (overall / resident / citizen;
seasonally adjusted or not), the period, and the number. Simple correct arithmetic on numbers in the evidence counts as supported.

**For each answer:** how well does it respond to the question? 5 = directly answers (or correctly explains why it cannot,
or asks a precise clarifying question); 3 = partly; 1 = does not address it. Judge responsiveness, not whether you know the number is true.

---

## Item 1: C04

**Question:** What was the citizen unemployment rate in September 2025?

**Answer status:** conflict_reported

**Answer summary:** Citizen unemployment rate for September 2025 (percent): the preliminary Advance Release gives 3.0%, while the later quarterly report gives 3.1%. The evidence does not explain the difference, so it is unexplained. The later report is the more recent figure.

### Claim 1 (source_fact)

> The Advance Release (preliminary) reported a citizen unemployment rate of 3.0% for September 2025.

Cited evidence:

- `22bfc4512d491ec1`: '5. Unemployment rates stayed low in September 2025 (overall 2.0%, resident 2.8%, citizen 3.0%), similar to the previous quarter. They also remained within the non-recessionary range.'

- [x] supported <!--g:01-C04:1:1-->
- [ ] not supported <!--g:01-C04:1:0-->

### Claim 2 (source_fact)

> The later quarterly report reported a citizen unemployment rate of 3.1% for September 2025.

Cited evidence:

- `223dd85f21e2221e`: '1. Supported by continued economic growth, the labour market grew at a faster pace in 3Q 2025 compared to the previous quarter, and unemployment and retrenchments remained low. Although economic uncertainties have receded since the first half of 2025, it remains elevated and will continue to weigh on firms, pointing to a moderation of labour demand.\n\n2. Total employment grew by 25,100 in 3Q 2025, stronger than the 10,400 increase in 2Q 2025. Resident employment continued to expand and was led by Financial & Insurance Services and Health & Social Services, while non-resident employment grew mainly in Construction and Manufacturing.\n\n3. Unemployment rates in September 2025 (overall: 2.0%; resi'

- [x] supported <!--g:01-C04:2:1-->
- [ ] not supported <!--g:01-C04:2:0-->

### Claim 3 (statistical_finding)

> The data.gov.sg citizen unemployment rate (seasonally adjusted) for 3Q 2025 is 3.1%, which is quarterly and matches the later report's figure.

Cited evidence:

- `2b2f0eb926928dc7`: 'Singapore citizen unemployment rate (seasonally adjusted), 3Q 2025: 3.1% (Source: MOM via data.gov.sg, dataset d_1353f9be1a020ba1469852c49ee62db3, retrieved 2026-10-27)'

- [x] supported <!--g:01-C04:3:1-->
- [ ] not supported <!--g:01-C04:3:0-->

### Claim 4 (source_fact)

> The Advance Release (preliminary) reported a citizen unemployment rate of 3.3% for September 2025.

Cited evidence:

- `22bfc4512d491ec1`: '5. Unemployment rates stayed low in September 2025 (overall 2.0%, resident 2.8%, citizen 3.0%), similar to the previous quarter. They also remained within the non-recessionary range.'

- [ ] supported <!--g:01-C04:4:1-->
- [x] not supported <!--g:01-C04:4:0-->

### Relevance of the whole answer (tick one)

- [ ] 1 <!--r:01-C04:1-->
- [ ] 2 <!--r:01-C04:2-->
- [ ] 3 <!--r:01-C04:3-->
- [ ] 4 <!--r:01-C04:4-->
- [x] 5 <!--r:01-C04:5-->

---

## Item 2: F02

**Question:** What was the overall unemployment rate, seasonally adjusted, in the fourth quarter of 2023?

**Answer status:** answered

**Answer summary:** 2% (overall, seasonally adjusted, quarterly, 4Q 2023).

### Claim 1 (statistical_finding)

> The overall unemployment rate (seasonally adjusted, quarterly) for 4Q 2023 was 2%.

Cited evidence:

- `6eccd25cc56adc44`: 'Singapore overall unemployment rate (seasonally adjusted), 4Q 2023: 2% (Source: MOM via data.gov.sg, dataset d_ca32584c91ee07d091a4ce75fa868414, retrieved 2026-10-27)'

- [x] supported <!--g:02-F02:1:1-->
- [ ] not supported <!--g:02-F02:1:0-->

### Claim 2 (statistical_finding)

> The overall unemployment rate (seasonally adjusted, quarterly) for 4Q 2023 was 3%.

Cited evidence:

- `6eccd25cc56adc44`: 'Singapore overall unemployment rate (seasonally adjusted), 4Q 2023: 2% (Source: MOM via data.gov.sg, dataset d_ca32584c91ee07d091a4ce75fa868414, retrieved 2026-10-27)'

- [ ] supported <!--g:02-F02:2:1-->
- [x] not supported <!--g:02-F02:2:0-->

### Relevance of the whole answer (tick one)

- [ ] 1 <!--r:02-F02:1-->
- [ ] 2 <!--r:02-F02:2-->
- [ ] 3 <!--r:02-F02:3-->
- [ ] 4 <!--r:02-F02:4-->
- [x] 5 <!--r:02-F02:5-->

---

## Item 3: F03

**Question:** What was the annual average citizen unemployment rate for 2024?

**Answer status:** answered

**Answer summary:** 2.9% (citizen unemployment rate, annual average, 2024; percent, not seasonally adjusted quarterly).

### Claim 1 (statistical_finding)

> The Singapore citizen unemployment rate, annual average, for 2024 was 2.9%.

Cited evidence:

- `8c6350182410b2ed`: 'Singapore citizen unemployment rate, annual average, the year 2024: 2.9% (Source: MOM via data.gov.sg, dataset d_dab839a10e83a6a8746e1836f3dd5629, retrieved 2026-10-27)'

- [x] supported <!--g:03-F03:1:1-->
- [ ] not supported <!--g:03-F03:1:0-->

### Claim 2 (source_fact)

> The advance release also reports the 2024 annual citizen rate at 2.9%, unchanged from 2023.

Cited evidence:

- `7bcfe15d96336a76`: '9. Unemployment rates for residents and citizens rose slightly from September to October 2024 (resident: from 2.6% to 2.8%; citizen: from 2.7% to 2.9%), but held steady in November and December, within the typical range for non-recession periods. The overall unemployment rate remained unchanged at 1.9%.\n\n10. In 2024, the unemployment situation remained relatively stable and low throughout the year, and annual rates remained broadly consistent from 2023 (overall: 2.0% in 2024 vs. 1.9% in 2023; resident: 2.8% vs. 2.7%; citizen: unchanged at 2.9%).'

- [x] supported <!--g:03-F03:2:1-->
- [ ] not supported <!--g:03-F03:2:0-->

### Claim 3 (statistical_finding)

> The Singapore citizen unemployment rate, annual average, for 2024 was 3.2%.

Cited evidence:

- `8c6350182410b2ed`: 'Singapore citizen unemployment rate, annual average, the year 2024: 2.9% (Source: MOM via data.gov.sg, dataset d_dab839a10e83a6a8746e1836f3dd5629, retrieved 2026-10-27)'

- [ ] supported <!--g:03-F03:3:1-->
- [x] not supported <!--g:03-F03:3:0-->

### Relevance of the whole answer (tick one)

- [ ] 1 <!--r:03-F03:1-->
- [ ] 2 <!--r:03-F03:2-->
- [ ] 3 <!--r:03-F03:3-->
- [ ] 4 <!--r:03-F03:4-->
- [x] 5 <!--r:03-F03:5-->

---

## Item 4: F05

**Question:** How many employees were retrenched in 2Q 2026?

**Answer status:** conflict_reported

**Answer summary:** Sources differ on 2Q 2026 retrenchments (quarterly, overall count): 4,500 in the preliminary MOM Advance Release and 4,620 in the later MOM dataset on data.gov.sg. The 120 gap is unexplained, as the evidence states no revision.

### Claim 1 (source_fact)

> The preliminary MOM Advance Release reported 4,500 retrenchments in 2Q 2026, up from 3,830 in 1Q 2026.

Cited evidence:

- `45cc33c13de6b35e`: '5 The number of retrenchments rose from 3,830 in 1Q 2026 to 4,500 in 2Q 2026, bringing the incidence of retrenchment up from 1.6 to 1.9 per 1,000 employees. The increase was concentrated in some outward-oriented sectors, driven primarily by business restructuring. Nonetheless, retrenchments remained well below levels typically seen during periods of downturn.'

- [x] supported <!--g:04-F05:1:1-->
- [ ] not supported <!--g:04-F05:1:0-->

### Claim 2 (statistical_finding)

> The later MOM dataset on data.gov.sg gives the number of retrenched employees in 2Q 2026 as 4,620.

Cited evidence:

- `d3da20c48c2d231e`: 'Singapore number of retrenched employees, 2Q 2026: 4,620 (Source: MOM via data.gov.sg, dataset d_000d49cda016c13522d7d5be6a050f59, retrieved 2026-10-27)'

- [x] supported <!--g:04-F05:2:1-->
- [ ] not supported <!--g:04-F05:2:0-->

### Claim 3 (model_inference)

> The gap between the two figures is 4,620 - 4,500 = 120 retrenchments. The evidence does not state a revision explaining it, so the difference is unexplained.

Cited evidence:

- `45cc33c13de6b35e`: '5 The number of retrenchments rose from 3,830 in 1Q 2026 to 4,500 in 2Q 2026, bringing the incidence of retrenchment up from 1.6 to 1.9 per 1,000 employees. The increase was concentrated in some outward-oriented sectors, driven primarily by business restructuring. Nonetheless, retrenchments remained well below levels typically seen during periods of downturn.'
- `d3da20c48c2d231e`: 'Singapore number of retrenched employees, 2Q 2026: 4,620 (Source: MOM via data.gov.sg, dataset d_000d49cda016c13522d7d5be6a050f59, retrieved 2026-10-27)'

- [x] supported <!--g:04-F05:3:1-->
- [ ] not supported <!--g:04-F05:3:0-->

### Claim 4 (source_fact)

> The preliminary MOM Advance Release reported 4,950 retrenchments in 2Q 2026, up from 3,830 in 1Q 2026.

Cited evidence:

- `45cc33c13de6b35e`: '5 The number of retrenchments rose from 3,830 in 1Q 2026 to 4,500 in 2Q 2026, bringing the incidence of retrenchment up from 1.6 to 1.9 per 1,000 employees. The increase was concentrated in some outward-oriented sectors, driven primarily by business restructuring. Nonetheless, retrenchments remained well below levels typically seen during periods of downturn.'

- [ ] supported <!--g:04-F05:4:1-->
- [x] not supported <!--g:04-F05:4:0-->

### Relevance of the whole answer (tick one)

- [ ] 1 <!--r:04-F05:1-->
- [ ] 2 <!--r:04-F05:2-->
- [ ] 3 <!--r:04-F05:3-->
- [ ] 4 <!--r:04-F05:4-->
- [x] 5 <!--r:04-F05:5-->

---

## Item 5: F06

**Question:** What was the published ratio of job vacancies to unemployed persons in 4Q 2025?

**Answer status:** answered

**Answer summary:** The published job vacancy to unemployed persons ratio (seasonally adjusted) was 1.58 in 4Q 2025 (December 2025), up from 1.50 in September 2025.

### Claim 1 (statistical_finding)

> Singapore ratio of job vacancies to unemployed persons (seasonally adjusted), 4Q 2025: 1.58.

Cited evidence:

- `2a451b7d759c4925`: 'Singapore ratio of job vacancies to unemployed persons (seasonally adjusted), 4Q 2025: 1.58 (Source: MOM via data.gov.sg, dataset d_80c0cf251ee9a26d240808297f52c820, retrieved 2026-10-27)'

- [x] supported <!--g:05-F06:1:1-->
- [ ] not supported <!--g:05-F06:1:0-->

### Claim 2 (source_fact)

> The quarterly report states job vacancies rose from 69,600 in September 2025 to 77,700 in December 2025, raising the job vacancy to unemployed persons ratio from 1.50 to 1.58.

Cited evidence:

- `6d1e36fb14d00a1d`: 'The labour market continued to expand in 2025, supported by economic growth and sustained labour demand. Unemployment and retrenchments remained low.\n\n2 The labour market expanded in 4Q 2025 and over the full year of 2025. Total employment expanded by 17,700 in 4Q 2025, marking the 17th consecutive quarter of growth since 4Q 2021. For the full year of 2025, total employment grew by 55,500, an increase from the 44,500 in 2024. In 2025, resident employment growth (11,600) was driven largely by Financial Services and Health & Social Services, while non-resident employment growth (43,900) was driven by the continued hiring of Work Permit holders in Construction.\n\n3 Unemployment rates remained lo'

- [x] supported <!--g:05-F06:2:1-->
- [ ] not supported <!--g:05-F06:2:0-->

### Relevance of the whole answer (tick one)

- [ ] 1 <!--r:05-F06:1-->
- [ ] 2 <!--r:05-F06:2-->
- [ ] 3 <!--r:05-F06:3-->
- [ ] 4 <!--r:05-F06:4-->
- [x] 5 <!--r:05-F06:5-->

---

## Item 6: F07

**Question:** According to MOM's Labour Market Report for 2Q 2026, what drove the increase in retrenchments?

**Answer status:** answered

**Answer summary:** The Labour Market Report for 2Q 2026 says the rise in retrenchments was driven by business reorganisation and restructuring in outward-oriented sectors such as Manufacturing, Information & Communications and Financial Services.

### Claim 1 (source_fact)

> The 2Q 2026 Labour Market Report attributes the increase in retrenchments to business reorganisation and restructuring in outward-oriented sectors such as Manufacturing, Information & Communications and Financial Services.

Cited evidence:

- `ff14cfc3440c8f63`: 'Alongside improved economic growth, Singapore’s labour market continued to expand in 2Q 2026. Total employment increased by 11,400, marking the nineteenth consecutive quarter of growth and an increase from 9,400 in 1Q 2026 and 10,400 in 2Q 2025. In 2Q 2026, resident employment growth (2,200) slowed from the previous quarter (5,400). Resident employment grew mainly in domestic-oriented sectors such as Transportation & Storage, Public Administration & Education and Health & Social Services, as well as outward-oriented sectors such as Professional Services, Financial Services and Information & Communications. Non-resident employment growth (9,200) was driven by Work Permit Holders in Constructi'

- [x] supported <!--g:06-F07:1:1-->
- [ ] not supported <!--g:06-F07:1:0-->

### Claim 2 (source_fact)

> The earlier Advance Release gave a consistent explanation: the increase was concentrated in some outward-oriented sectors, driven primarily by business restructuring.

Cited evidence:

- `45cc33c13de6b35e`: '5 The number of retrenchments rose from 3,830 in 1Q 2026 to 4,500 in 2Q 2026, bringing the incidence of retrenchment up from 1.6 to 1.9 per 1,000 employees. The increase was concentrated in some outward-oriented sectors, driven primarily by business restructuring. Nonetheless, retrenchments remained well below levels typically seen during periods of downturn.'

- [x] supported <!--g:06-F07:2:1-->
- [ ] not supported <!--g:06-F07:2:0-->

### Relevance of the whole answer (tick one)

- [ ] 1 <!--r:06-F07:1-->
- [ ] 2 <!--r:06-F07:2-->
- [ ] 3 <!--r:06-F07:3-->
- [ ] 4 <!--r:06-F07:4-->
- [x] 5 <!--r:06-F07:5-->

---

## Item 7: K05

**Question:** By what percentage did the nominal median (P50) income rise from 2024 to 2025 according to the Labour Force in Singapore 2025 advance release?

**Answer status:** answered

**Answer summary:** Nominal median (P50) gross monthly income of full-time employed residents rose about 5.0%, from $5,500 in 2024 to $5,775 in 2025. This is my calculation; the release does not state a nominal percentage change.

### Claim 1 (source_fact)

> The advance release gives nominal P50 income of $5,775 in 2025, up from $5,500 in 2024.

Cited evidence:

- `2b42f2749b76a81b`: '5. Workers at both the 20th percentile (P20) and median (P50) saw higher nominal income levels (P20: $3,164, P50: $5,775) from 2024 (P20: $3,026, P50: $5,500). After adjusting for inflation, real incomes grew year-on-year for both the P20 and median workers (P20: 3.8%, P50: 4.3%), broadly in line with productivity growth over the longer term. Real income growth at the P20 over the recent five- and ten-year periods (both 2.9% p.a.) were higher than growth at the median (2020 to 2025: 1.6% p.a., 2015 to 2025: 2.1% p.a.).\n\n6. The expansion of the Progressive Wage Model (PWM) has continued to uplift lower-wage workers, narrowing the income gap. The P20 to P50 income ratio rose to 0.55 in 2025, f'

- [x] supported <!--g:07-K05:1:1-->
- [ ] not supported <!--g:07-K05:1:0-->

### Claim 2 (model_inference)

> Working: ($5,775 - $5,500) / $5,500 = $275 / $5,500 = 0.05, so nominal median income rose about 5.0% (not inflation-adjusted).

Cited evidence:

- `2b42f2749b76a81b`: '5. Workers at both the 20th percentile (P20) and median (P50) saw higher nominal income levels (P20: $3,164, P50: $5,775) from 2024 (P20: $3,026, P50: $5,500). After adjusting for inflation, real incomes grew year-on-year for both the P20 and median workers (P20: 3.8%, P50: 4.3%), broadly in line with productivity growth over the longer term. Real income growth at the P20 over the recent five- and ten-year periods (both 2.9% p.a.) were higher than growth at the median (2020 to 2025: 1.6% p.a., 2015 to 2025: 2.1% p.a.).\n\n6. The expansion of the Progressive Wage Model (PWM) has continued to uplift lower-wage workers, narrowing the income gap. The P20 to P50 income ratio rose to 0.55 in 2025, f'

- [x] supported <!--g:07-K05:2:1-->
- [ ] not supported <!--g:07-K05:2:0-->

### Claim 3 (source_fact)

> For comparison, the release states real (inflation-adjusted) year-on-year growth of 4.3% for the median worker.

Cited evidence:

- `2b42f2749b76a81b`: '5. Workers at both the 20th percentile (P20) and median (P50) saw higher nominal income levels (P20: $3,164, P50: $5,775) from 2024 (P20: $3,026, P50: $5,500). After adjusting for inflation, real incomes grew year-on-year for both the P20 and median workers (P20: 3.8%, P50: 4.3%), broadly in line with productivity growth over the longer term. Real income growth at the P20 over the recent five- and ten-year periods (both 2.9% p.a.) were higher than growth at the median (2020 to 2025: 1.6% p.a., 2015 to 2025: 2.1% p.a.).\n\n6. The expansion of the Progressive Wage Model (PWM) has continued to uplift lower-wage workers, narrowing the income gap. The P20 to P50 income ratio rose to 0.55 in 2025, f'

- [x] supported <!--g:07-K05:3:1-->
- [ ] not supported <!--g:07-K05:3:0-->

### Claim 4 (source_fact)

> Income here means gross monthly income from employment, including employer/platform operator CPF contributions, of full-time employed residents.

Cited evidence:

- `63d666ea0dd6d788`: 'The data pertain to the resident population for the period of June each year, comprising Singapore citizens and permanent residents. The final report of the Labour Force in Singapore 2025 will be released in January 2026. Data for previous editions of the Labour Force in Singapore are available online on the Ministry of Manpower’s Research and Statistics Department website at https://stats.mom.gov.sg. Details on the survey methodology as well as the concepts and definitions are in the “Factsheet on Comprehensive Labour Force Survey” appended with this press release.\n\nBased on latest available figures (2024 for OECD countries, 2025 for Singapore), Singapore’s labour force participation rate r'

- [x] supported <!--g:07-K05:4:1-->
- [ ] not supported <!--g:07-K05:4:0-->

### Relevance of the whole answer (tick one)

- [ ] 1 <!--r:07-K05:1-->
- [ ] 2 <!--r:07-K05:2-->
- [ ] 3 <!--r:07-K05:3-->
- [ ] 4 <!--r:07-K05:4-->
- [x] 5 <!--r:07-K05:5-->

---

## Item 8: M01

**Question:** Is the 2Q 2026 Labour Market Report's statement that retrenchments rose from 3,830 to 4,620 consistent with the quarterly retrenchment dataset?

**Answer status:** answered

**Answer summary:** Partly confirmed. The dataset's 2Q 2026 figure (4,620 retrenched employees, quarterly) matches the report's 4,620. The report's 1Q 2026 figure of 3,830 cannot be checked against the dataset, because the supplied dataset evidence covers 2Q 2026 only. The earlier, preliminary Advance Release gave 4,500 for 2Q 2026.

### Claim 1 (source_fact)

> The 2Q 2026 Labour Market Report states that retrenchments rose from 3,830 in 1Q 2026 to 4,620 in 2Q 2026.

Cited evidence:

- `ff14cfc3440c8f63`: 'Alongside improved economic growth, Singapore’s labour market continued to expand in 2Q 2026. Total employment increased by 11,400, marking the nineteenth consecutive quarter of growth and an increase from 9,400 in 1Q 2026 and 10,400 in 2Q 2025. In 2Q 2026, resident employment growth (2,200) slowed from the previous quarter (5,400). Resident employment grew mainly in domestic-oriented sectors such as Transportation & Storage, Public Administration & Education and Health & Social Services, as well as outward-oriented sectors such as Professional Services, Financial Services and Information & Communications. Non-resident employment growth (9,200) was driven by Work Permit Holders in Constructi'

- [x] supported <!--g:08-M01:1:1-->
- [ ] not supported <!--g:08-M01:1:0-->

### Claim 2 (statistical_finding)

> The quarterly retrenchment dataset gives 4,620 retrenched employees for 2Q 2026, the same as the report's 2Q 2026 figure.

Cited evidence:

- `d3da20c48c2d231e`: 'Singapore number of retrenched employees, 2Q 2026: 4,620 (Source: MOM via data.gov.sg, dataset d_000d49cda016c13522d7d5be6a050f59, retrieved 2026-10-27)'

- [x] supported <!--g:08-M01:2:1-->
- [ ] not supported <!--g:08-M01:2:0-->

### Claim 3 (source_fact)

> The earlier Advance Release reported 4,500 retrenchments in 2Q 2026, up from 3,830 in 1Q 2026. It describes its 2Q 2026 data as preliminary.

Cited evidence:

- `45cc33c13de6b35e`: '5 The number of retrenchments rose from 3,830 in 1Q 2026 to 4,500 in 2Q 2026, bringing the incidence of retrenchment up from 1.6 to 1.9 per 1,000 employees. The increase was concentrated in some outward-oriented sectors, driven primarily by business restructuring. Nonetheless, retrenchments remained well below levels typically seen during periods of downturn.'
- `92817f76bd4a51c1`: 'Employment figures cited in this press release exclude Migrant Domestic Workers.\n\nData for 2Q 2026 are preliminary (denoted as “p” in the Annex).\n\nRefers to Singapore citizens and permanent residents.\n\nQuarterly retrenchments ranged from 5,980 to 12,760 and 5,640 to 9,120 during the 2009 Global Financial Crisis and the Covid-19 pandemic respectively.'

- [x] supported <!--g:08-M01:3:1-->
- [ ] not supported <!--g:08-M01:3:0-->

### Relevance of the whole answer (tick one)

- [ ] 1 <!--r:08-M01:1-->
- [ ] 2 <!--r:08-M01:2-->
- [x] 3 <!--r:08-M01:3-->
- [ ] 4 <!--r:08-M01:4-->
- [ ] 5 <!--r:08-M01:5-->

---

## Item 9: M04

**Question:** What data sources does MOM say it uses to compile employment change, and how much did total employment change in 2Q 2026?

**Answer status:** answered

**Answer summary:** Total employment grew by 10,700 in 2Q 2026 (overall, quarterly change, persons), per the MOM Advance Release, so the figure is preliminary. The evidence does not say which data sources MOM uses to compile employment change.

### Claim 1 (source_fact)

> Total employment grew by 10,700 in 2Q 2026 (overall employment, quarterly change in number of persons). This comes from the Advance Release, so it is a preliminary figure.

Cited evidence:

- `6befc468c7f9007b`: '2 Total employment grew by 10,700 in 2Q 2026, up from 9,400 in 1Q 2026 and was broadly similar to the 10,400 in 2Q 2025. This marked the 19 consecutive quarter of growth since 4Q 2021.\n\n3 Resident employment continued to grow, albeit at a slower pace compared to the previous quarter. Resident employment growth was mainly in essential and public services. Following the slower non-resident employment growth in 1Q 2026, employment growth was driven primarily by non-residents in 2Q 2026, mainly in sectors such as Construction and Manufacturing.'

- [x] supported <!--g:09-M04:1:1-->
- [ ] not supported <!--g:09-M04:1:0-->

### Relevance of the whole answer (tick one)

- [ ] 1 <!--r:09-M04:1-->
- [ ] 2 <!--r:09-M04:2-->
- [x] 3 <!--r:09-M04:3-->
- [ ] 4 <!--r:09-M04:4-->
- [ ] 5 <!--r:09-M04:5-->

---

## Item 10: M05

**Question:** How did resident employment growth in 2Q 2026 compare with 1Q 2026, and what happened to the seasonally adjusted resident unemployment rate over the same two quarters?

**Answer status:** answered

**Answer summary:** Resident employment growth slowed from 5,400 in 1Q 2026 to 2,200 in 2Q 2026 (persons, quarterly change). The seasonally adjusted resident unemployment rate was 2.9% in 2Q 2026. The evidence has no seasonally adjusted quarterly figure for 1Q 2026, so I cannot confirm the change. The advance release shows resident unemployment at 2.9% in both March and June 2026, but does not say whether those figures are seasonally adjusted.

### Claim 1 (source_fact)

> Resident employment growth slowed to 2,200 in 2Q 2026 from 5,400 in 1Q 2026 (persons, quarterly change in employment).

Cited evidence:

- `ff14cfc3440c8f63`: 'Alongside improved economic growth, Singapore’s labour market continued to expand in 2Q 2026. Total employment increased by 11,400, marking the nineteenth consecutive quarter of growth and an increase from 9,400 in 1Q 2026 and 10,400 in 2Q 2025. In 2Q 2026, resident employment growth (2,200) slowed from the previous quarter (5,400). Resident employment grew mainly in domestic-oriented sectors such as Transportation & Storage, Public Administration & Education and Health & Social Services, as well as outward-oriented sectors such as Professional Services, Financial Services and Information & Communications. Non-resident employment growth (9,200) was driven by Work Permit Holders in Constructi'

- [x] supported <!--g:10-M05:1:1-->
- [ ] not supported <!--g:10-M05:1:0-->

### Claim 2 (model_inference)

> Working: 5,400 - 2,200 = 3,200, so resident employment growth was 3,200 persons lower in 2Q 2026 than in 1Q 2026.

Cited evidence:

- `ff14cfc3440c8f63`: 'Alongside improved economic growth, Singapore’s labour market continued to expand in 2Q 2026. Total employment increased by 11,400, marking the nineteenth consecutive quarter of growth and an increase from 9,400 in 1Q 2026 and 10,400 in 2Q 2025. In 2Q 2026, resident employment growth (2,200) slowed from the previous quarter (5,400). Resident employment grew mainly in domestic-oriented sectors such as Transportation & Storage, Public Administration & Education and Health & Social Services, as well as outward-oriented sectors such as Professional Services, Financial Services and Information & Communications. Non-resident employment growth (9,200) was driven by Work Permit Holders in Constructi'

- [x] supported <!--g:10-M05:2:1-->
- [ ] not supported <!--g:10-M05:2:0-->

### Claim 3 (statistical_finding)

> Singapore resident unemployment rate (seasonally adjusted) was 2.9% in 2Q 2026.

Cited evidence:

- `8cffa20242d879f1`: 'Singapore resident unemployment rate (seasonally adjusted), 2Q 2026: 2.9% (Source: MOM via data.gov.sg, dataset d_d1d755e060dd6b01a8024ba60b21b831, retrieved 2026-10-27)'

- [x] supported <!--g:10-M05:3:1-->
- [ ] not supported <!--g:10-M05:3:0-->

### Claim 4 (source_fact)

> The advance release gives a resident unemployment rate of 2.9% in both June 2026 and March 2026, but does not state that it is seasonally adjusted.

Cited evidence:

- `c0170e72c80585f0`: '4 Unemployment rates remained low and stable in June 2026 (overall: 2.0%, resident: 2.9%, citizen: 3.0%), comparable to March 2026 (overall: 2.0%, resident: 2.9%, citizen: 3.1%).'

- [x] supported <!--g:10-M05:4:1-->
- [ ] not supported <!--g:10-M05:4:0-->

### Relevance of the whole answer (tick one)

- [ ] 1 <!--r:10-M05:1-->
- [ ] 2 <!--r:10-M05:2-->
- [ ] 3 <!--r:10-M05:3-->
- [x] 4 <!--r:10-M05:4-->
- [ ] 5 <!--r:10-M05:5-->


## Labelling record

Labelled on 2026-10-27, before reading stored judge verdicts or perturbation flags. This is an AI-to-AI agreement check, not independent human calibration. No test case definitions were changed.

The sheet truncates evidence at 700 characters. For C04, F06, F07, K05 and M01, the full cited chunks in `data/processed/chunks.jsonl` were consulted to resolve omitted support. Claims were judged against the cited source content, not whether a preliminary value is the latest figure. Statements that a difference is unexplained were accepted only as statements about the supplied evidence, not proof that no revision explanation exists elsewhere.

Responsiveness: M01 = 3 because it verifies only the second quarter; M04 = 3 because it supplies a preliminary employment figure but not compilation sources; M05 = 4 because it answers employment growth and supplies relevant unemployment figures but does not resolve the requested SA comparison. Other answers = 5 under the sheet's responsiveness-only rubric. Altered claims are evaluated separately from the original answer summaries.
