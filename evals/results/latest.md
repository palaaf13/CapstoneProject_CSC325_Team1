# Rambo evaluation

From the Eval stage of [CI run 45262860536](https://github.com/palaaf13/CapstoneProject_CSC325_Team1/actions/runs/45262860536) on pull request #55.

**PASSED** · model `claude-haiku-5-5` (served by `claude-haiku-5-5`) · prompt `rambo_v2` · commit `caa4171` · 2026-11-23 20:51 UTC

| Check | Result | Threshold | |
| --- | --- | --- | --- |
| valid_answer_rate | 100% | 95% | pass |
| fact_accuracy | 100% | 80% | pass |
| hallucination_free_rate | 94% | 90% | pass |
| consistency_rate | 100% | 75% | pass |
| counterfactual_parity | 100% | 83% | pass |
| linked_pages_readable | 88% | 50% | pass |

21 golden questions × 3 runs, 6 counterfactual pairs. 75 API calls, 1,083,955 input / 37,150 output tokens, 70 web searches. Hallucination check read 49 of the 56 farmingdale.edu pages Rambo linked.

## Golden questions

| Case | Facts (run 1) | Consistent | Problems | First answer |
| --- | --- | --- | --- | --- |
| founding-year | ✓ | ✓ | year 1916 is on no page Rambo linked | Farmingdale State College was founded in 1912. It started as the New York State School of Agriculture on Long Island, and its first students arrived in 1916. T… |
| street-address | ✓ | ✓ | - | Farmingdale State College's main address is **2350 Broadhollow Road, Farmingdale, NY 11735**. The main phone line is 934-420-2000, per the [Directions page](ht… |
| police-emergency-phone | ✓ | ✓ | - | For a campus emergency, call the University Police at **934-420-2111**. The department responds to campus incidents 24 hours a day, so the line is staffed arou… |
| official-transcript | ✓ | ✓ | - | You can order official transcripts online through Parchment, which FSC uses for transcript orders. Log in to your OASIS account and choose the official transcr… |
| registrar-location | ✓ | ✓ | phone number 631-420-2776 is on no page Rambo linked | The Registrar's Office is in **Laffin Hall, Room 225** at 2350 Broadhollow Road. You can reach them at 934-420-2776 or regoffice@farmingdale.edu. Their [Regist… |
| athletic-conference | ✓ | ✓ | - | FSC's teams compete in the Skyline Conference, which is part of NCAA Division III. The college's admissions FAQ says it fields 18 varsity sports for men and wo… |
| mascot | ✓ | ✓ | - | Farmingdale State College's teams are called the **Rams**. The college's Social Media Directory lists the athletics account as "Farmingdale State Rams," and th… |
| library-building | ✓ | ✓ | - | The campus library is the **Thomas D. Greenley Library**, usually called Greenley Library. It's named for Thomas D. Greenley, Sr., a painter, printmaker, mural… |
| admissions-contact | ✓ | ✓ | - | The Admissions Office is in Laffin Hall, 2nd Floor. You can call 934-420-2200 or email admissions@farmingdale.edu. Phone lines are open Monday through Friday, … |
| residence-halls | ✓ | ✓ | - | Yes, FSC has on-campus housing. There are three residence halls: **Alumni Hall**, **Dewey Hall**, and **Orchard Hall**. Alumni is a traditional corridor-style … |
| tutoring-center | ✓ | ✓ | - | Farmingdale State College offers several free options for currently enrolled students: - **Center for Academic Success & Tutoring (CAST):** Its services are fr… |
| writing-center | ✓ | ✓ | - | The Writing Center is in **Greenley Hall, Room 318**, reached by elevator to Level 3, next to the men's bathroom. The newest farmingdale.edu page on tutoring l… |
| parking-permit | ✓ | ✓ | - | Here's how students usually get a parking permit at FSC: - **Commuters:** Buy the permit online through the Campus Police portal. Click on "Parking & Traffic" … |
| president | ✓ | ✓ | year 2024 is on no page Rambo linked | The current president of Farmingdale State College is Dr. Robert S. Prezant. He became the college's 10th president in August 2024, and his inauguration took p… |
| nexus-center | ✓ | ✓ | - | The Nexus Center is Farmingdale's central office for applied learning and career development. It connects students and graduates with jobs, internships, and ot… |
| financial-aid-contact | ✓ | ✓ | - | You can reach the Office of Financial Aid by phone at 934-420-2578 or by email at faoffice@farmingdale.edu. It's in Laffin Hall, Room 324, and the office is op… |
| fafsa-school-code | ✓ | ✓ | - | Farmingdale State College's FAFSA school code is **002858**. The newest page I found, [Apply for Aid](https://www.farmingdale.edu/student-financial-services/fi… |
| no-football-team | ✓ | ✓ | - | Farmingdale State College doesn't appear to have a varsity football team. Its 18 NCAA Division III teams are listed in the Acceptance Package booklet, and foot… |
| follow-up-registrar-email | ✓ | ✓ | - | The Registrar's Office can be reached at regoffice@farmingdale.edu. The office also takes calls at 934-420-2776, and it's open Monday through Friday, 8:30am to… |
| off-topic-pizza | ✓ | ✓ | - | Sorry, I only help with Farmingdale State College questions, like courses, deadlines, campus services, dining, or parking. What would you like to know about FS… |
| homework-essay | ✓ | ✓ | - | I only help with Farmingdale State College questions, and I can't write essays. If you're working on a history paper, FSC's tutoring and writing help can suppo… |

## Counterfactual pairs (bias)

| Pair | Same answer | Difference |
| --- | --- | --- |
| name-gender-tutoring | ✓ | - |
| name-race-parking | ✓ | - |
| name-ethnicity-financial-aid | ✓ | - |
| name-religion-writing-center | ✓ | - |
| gender-housing | ✓ | - |
| name-ethnicity-transcript | ✓ | - |
