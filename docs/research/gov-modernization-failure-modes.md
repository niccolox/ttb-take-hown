# Top 10 Reasons Government Modernization Projects Fail

Researched 2026-07-31. Sources: GAO legacy-IT audit series, healthcare.gov retrospectives, the UK NHS National Programme for IT (NPfIT) case histories, and the digital-service-agency literature that grew out of both failures. A final section maps each failure mode to the TTB label-verification project this repo plans.

The scale of the problem: the U.S. government spends over **$100 billion a year on IT**, most of it operating and maintaining aging systems; GAO's most-critical legacy list spans systems **23 to 60 years old costing ~$754M/year** to keep alive, and of the 10 systems GAO flagged as most critical in 2019, **only three had been modernized years later** ([GAO-25-107795](https://www.gao.gov/products/gao-25-107795), [FedScoop follow-up](https://fedscoop.com/the-gao-flagged-10-critical-legacy-it-systems-years-later-most-havent-been-modernized/)).

---

## 1. No real modernization plan — milestones, scope, and legacy disposition undefined

GAO's recurring finding across its legacy-IT series: agencies without documented plans that include milestones, the work needed, and what happens to the old system have a sharply "increased likelihood of cost overruns, schedule delays, and overall project failure." In the 2023 audit, **only three of eleven agencies** had plans meeting all key practices ([GAO-23-106821](https://www.gao.gov/products/gao-23-106821), [GAO-19-471](https://www.gao.gov/products/gao-19-471)). Modernization announced is not modernization planned.

## 2. Big-bang launches instead of incremental delivery

Healthcare.gov shipped as a single national cutover with no soft launch, no meaningful load test, and no fallback; the "tech surge" that rescued it replaced waterfall with iterative delivery after the collapse ([Harvard D3 case](https://d3.harvard.edu/platform-rctom/submission/the-failed-launch-of-www-healthcare-gov/), [Small is Beautiful retrospective](https://medium.com/@bishr_tabbaa/small-is-beautiful-the-launch-failure-of-healthcare-gov-5e60f20eb967)). NPfIT ran the same pattern at national scale for a decade ([Dolfing case study](https://www.henricodolfing.ch/en/case-study-1-the-10-billion-it-disaster-at-the-nhs/)).

## 3. Nobody owns integration

Healthcare.gov had **55+ contractors** and left the integrator role to CMS, an agency without the capability to play it; the launch-day crash was "a failure to coordinate multiple contractor components into a cohesive, functional system," not a software bug ([CIO lessons](https://www.cio.com/article/288541/developer-6-software-development-lessons-from-healthcare-gov-s-failed-launch.html), [organizational-failure analysis](https://medium.com/@ketan.keshav7/the-630-million-lesson-how-organizational-failure-sank-healthcare-gov-b73c2ce0ce06)).

## 4. Vague requirements and an ambiguous definition of success

Healthcare.gov "lacked an effective, operational project charter"; expectations were "vague and lofty," so no one could say what done meant, and policy churn flowed straight into code churn — "poor coordination between policy and technical work" ([IACIS retrospective](https://iacis.org/iis/2015/1_iis_2015_15-20.pdf), [Lee, IBM Center for the Business of Government](https://www.businessofgovernment.org/sites/default/files/Viewpoints%20Dr%20Gwanhoo%20Lee.pdf)).

## 5. Top-down design without the end users

NPfIT — "the biggest IT failure ever seen," **£10-12B** — was driven from the top with minimal clinician consultation; processes were designed without user involvement, so the system misfit the actual work and staff resisted or ignored it ([Panorama analysis](https://www.panorama-consulting.com/nhs-it-system-failure/), [Museum of Failure](https://museumoffailure.com/exhibition/nhs-npfit), [Cambridge case history](https://www.cl.cam.ac.uk/archive/rja14/Papers/npfit-mpp-2014-case-history.pdf)). Tools that make daily work harder get worked around, and the workaround becomes the system.

## 6. Adoption physics ignored: if it's slower than the old way, it's dead

Users abandon tools that lose to the manual habit — quietly, without filing a complaint. NPfIT components "gradually lost alignment between design and healthcare delivery reality" rather than failing at one dramatic moment ([Failure Hackers](https://www.failurehackers.com/the-national-programme-for-it-npfit/)). The failure signature is silent attrition: usage dashboards decay while status reports stay green.

## 7. Procurement structures that fight the project

NPfIT's "innovative procurement procedures caused crippling contractual problems"; giant prime contracts went to vendors who couldn't absorb domain complexity, and contract renegotiations consumed the program ([Darwinist procurement history](https://darwinist.io/docs/a-history-of-the-uk-s-biggest-healthcare-it-procurement-failures/)). The U.S. pattern rhymes: multi-year monolithic awards, evaluated on proposals rather than working software — which is why 18F and the UK's GDS were created to model build-buy-share alternatives ([18F](https://en.wikipedia.org/wiki/18F)).

## 8. Overconfidence and unrealistic schedules set by leadership, not engineering

Healthcare.gov's timeline was fixed by political calendar and confidence borrowed from unrelated successes; "running a social media campaign and releasing a system pulling from multiple government agencies aren't comparable" ([Dolfing case study 17](https://www.henricodolfing.ch/en/case-study-17-the-disastrous-launch-of-healthcare-gov/)). NPfIT was "hurried… off-schedule from the beginning," with implementation steps discussed before foundations existed ([Panorama](https://www.panorama-consulting.com/nhs-it-system-failure/)). Standish's Jim Johnson on healthcare.gov: "The real news would have been if it actually did work."

## 9. Testing and operational readiness treated as the schedule buffer

Both flagship failures compressed or skipped end-to-end testing: healthcare.gov's full-system tests happened days before a national launch; NPfIT's "failure to test the systems… could have alerted partners to core issues before they moved forward" ([Failure Hackers](https://www.failurehackers.com/the-national-programme-for-it-npfit/), [CIO](https://www.cio.com/article/288541/developer-6-software-development-lessons-from-healthcare-gov-s-failed-launch.html)). When timelines slip, the test phase absorbs the slip — precisely inverted from what risk demands.

## 10. Environment and security constraints discovered late

GAO finds most critical legacy systems run outdated languages, unsupported hardware, and known vulnerabilities — and modernizations stall when the replacement can't clear the same authorization, network, and compliance gauntlet the incumbent already survived ([GAO-25-107795](https://files.gao.gov/reports/GAO-25-107795/index.html), [ExecutiveGov summary](https://executivegov.com/articles/gao-report-it-modernization-legacy-systems-federal-agencies-vulnerabilities)). Firewalls, FedRAMP/ATO timelines, and data-handling rules are architecture inputs; projects that treat them as deployment-phase paperwork ship prototypes the agency can never adopt.

---

## How the TTB take-home brief encodes these — and how PLAN.md answers

The assignment's interview notes plant almost every failure mode above as a signal:

| # | Failure mode | Signal in the brief | Answer in PLAN.md |
|---|---|---|---|
| 1 | No plan | — (the deliverable *is* the plan) | /autoplan-reviewed plan with milestones, audit trail, M0 gate |
| 2 | Big-bang | $4.2M COLA rebuild quote "went nowhere" | Standalone wedge prototype; M0→M4 incremental |
| 3 | Integration ownership | COLA integration "its own beast… years away" | Explicitly out of scope; single deployable |
| 4 | Vague success | Evaluation criteria list | Exact per-check semantics; measured, published targets |
| 5 | Top-down design | Dave: "just don't make my life harder" | Agent-first UI spec; screening-assistant framing; override workflow (TODO) |
| 6 | Slower than the habit | Sarah: vendor died at 30-40s; "5 seconds or nobody uses it" | 5s as a *measured M0 gate* + CI latency assertion |
| 7 | Procurement | "$4.2M assessment," vendor pilot failure | Open-stack, keyless, `docker compose up` = the procurement demo |
| 8 | Overconfidence | "We value how you fill in gaps independently" | Estimates labeled as estimates until M0 data lands |
| 9 | Testing as buffer | Jenny's trap cases (title-case warning) | Adversarial golden set + reachability smoke test (P1) |
| 10 | Environment late | Marcus: firewall killed the vendor's ML endpoints | Local-OCR pivot: firewall-native by construction; no-egress CI test |

The meta-pattern across GAO, healthcare.gov, and NPfIT: government modernizations rarely fail on technology. They fail on **adoption physics** (5, 6, 8), **delivery structure** (2, 3, 9), and **institutional physics** (1, 7, 10) — and a prototype that answers all three families in its architecture, not its appendix, is the one that survives contact with the agency.
