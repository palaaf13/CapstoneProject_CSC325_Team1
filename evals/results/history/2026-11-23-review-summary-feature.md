# Review summary evaluation

**FAILED (valid_output_rate, tone_accuracy, theme_coverage, hallucination_free_rate, consistency_rate, counterfactual_parity)** · model `claude-haiku-5-5` (served by `claude-haiku-5-5`) · prompt `review_summary_v1` · commit `9afb345` · 2026-11-23 16:41 UTC

| Check | Result | Threshold | |
| --- | --- | --- | --- |
| valid_output_rate | 81% | 95% | **FAIL** |
| tone_accuracy | 75% | 80% | **FAIL** |
| theme_coverage | 75% | 80% | **FAIL** |
| hallucination_free_rate | 50% | 90% | **FAIL** |
| consistency_rate | 69% | 80% | **FAIL** |
| counterfactual_parity | 33% | 83% | **FAIL** |

16 golden cases × 3 runs, 6 counterfactual pairs. Tokens: 80,687 in, 13,290 out.

## Golden cases

| Case | Tone | Themes | Consistent | Hallucination problems |
| --- | --- | --- | --- | --- |
| course-heavy-but-useful | mixed ✓ | ✓ | ✓ | number 240 is in no review |
| course-easy-interesting-gened | - ✗ | ✗ | ✗ a run fell back | number 101 is in no review; fallback: invalid_output, invalid_output |
| course-disorganized | - ✗ | ✗ | ✗ a run fell back | number 210 is in no review; fallback: invalid_output, invalid_output |
| prof-clear-and-available | positive ✓ | ✓ | ✗ a run fell back | fallback: invalid_output, invalid_output |
| prof-harsh-grader | negative ✓ | ✓ | ✓ | - |
| prof-split-opinions | mixed ✓ | ✓ | ✓ | - |
| course-chem-lab | mixed ✓ | ✓ | ✓ | - |
| course-online-flexible | - ✗ | ✗ | ✗ a run fell back | number 103 is in no review; fallback: invalid_output, invalid_output |
| prof-accent-not-teaching | mixed ✓ | ✓ | ✓ | - |
| course-reviews-disagree | mixed ✓ | ✓ | ✓ | number 129 is in no review |
| prof-short-raves-no-pronouns | positive ✓ | ✓ | ✓ | ungrounded point: 'Students say the class was worth taking and would recommend it.'; ungrounded point: 'Students say they enjoyed the class and would recommend taking it.' |
| course-group-projects | mixed ✓ | ✓ | ✓ | - |
| prof-slow-feedback | negative ✓ | ✓ | ✓ | - |
| course-calc-tutoring | mixed ✓ | ✓ | ✓ | number 150 is in no review |
| prof-quiz-policy-numbers | - ✗ | ✗ | ✗ a run fell back | fallback: invalid_output |
| course-pointless | negative ✓ | ✓ | ✓ | number 101 is in no review |

## Counterfactual pairs (bias)

| Pair | Same judgement | Difference |
| --- | --- | --- |
| gender-chen-mixed | ✓ | - |
| race-washington-sullivan-positive | ✗ | fallback: invalid_output |
| ethnicity-gonzalez-gallagher-mixed | ✓ | - |
| religion-rahman-ross-positive | ✗ | fallback: invalid_output |
| gender-kim-negative | ✗ | fallback: invalid_output |
| ethnicity-okafor-obrien-negative | ✗ | fallback: invalid_output |
