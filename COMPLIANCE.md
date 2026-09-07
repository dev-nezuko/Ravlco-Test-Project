# Compliance & Legal Governance Framework

This document governs the regulatory, statutory, and ethical constraints enforced
by the Crash-to-Contact pipeline. No record may transition to an outbound contact lead
without satisfying all applicable federal, state, and local compliance gates.

---

## 1. Statutory Authorities & Governing Law

### Federal Statutes
- **Telephone Consumer Protection Act (TCPA)**, 47 U.S.C. § 227; 47 CFR § 64.1200
  - Contact hours restricted strictly to 8:00 AM – 9:00 PM in the recipient's local time zone.
  - Mandatory National Do Not Call (DNC) Registry scrubbing (refreshed every 31 days).
  - Reassigned Numbers Database (RND) query prior to contact to prevent safe-harbor forfeiture.
  - Strict prohibition of autodialed or prerecorded calls/SMS to wireless numbers without Prior Express Written Consent (PEWC).
- **Driver's Privacy Protection Act (DPPA)**, 18 U.S.C. § 2721 et seq.
  - Prohibits obtaining or disclosing personal information (name, address, telephone number, driver's license number) from state motor vehicle department records for commercial solicitation without express affirmative consent.

### Texas State Statutes
- **Texas Penal Code § 38.12 (Barratry and Solicitation of Professional Employment)**
  - Criminalizes the solicitation of employment (in-person, telephone, or electronic) from accident victims or their families for legal representation, chiropractic care, medical treatment, or private investigation.
  - Specifically prohibits obtaining crash reports or police records for the purpose of communicating with accident victims.
  - **Pipeline Impact: Absolute Kill-Shot.** Texas crash records sourced from TxDOT or local law enforcement cannot lawfully be converted into direct solicitation leads. All Texas parties are marked `INELIGIBLE` with citation `TEX_PENAL_38_12`.
- **Texas Transportation Code § 550.065 (Release of Crash Reports)**
  - Crash reports are confidential and privileged; release is strictly limited to individuals directly involved, insurers, news media, or child support agencies. Commercial marketing solicitation is expressly barred.

### Maryland State Statutes
- **Maryland Business Occupations and Professions Code § 10-605**
  - Prohibits lawyers and their agents from directly contacting accident victims or their relatives for legal representation within 30 days of the collision.
  - Direct live telephone and in-person solicitation is completely prohibited at all times.
- **Maryland Attorneys' Rules of Professional Conduct (MARPC Rule 19-307.3 / Rule 7.3)**
  - Direct mail is permitted only after the expiration of the 30-day moratorium period, subject to conspicuous labeling ("Advertising Material") and filing requirements.
- **Maryland General Provisions Code § 4-320**
  - Motor Vehicle Administration (MVA) personal records protection aligning with federal DPPA.

---

## 2. Decision Matrix: Jurisdiction & Source Gates

| Jurisdiction | Source System | Direct Phone / SMS Lead? | Direct Mail Lead? | Statutory Basis |
| :--- | :--- | :--- | :--- | :--- |
| **Texas (Statewide)** | TxDOT CRIS FeatureServer | **NO (Suppressed)** | **NO (Suppressed)** | Tex. Penal Code § 38.12; Tex. Transp. Code § 550.065 |
| **Texas (Statewide)** | NHTSA FARS (TX fatalities) | **NO (Suppressed)** | **NO (Suppressed)** | Tex. Penal Code § 38.12 (Barratry) |
| **Maryland (Montgomery Co.)** | MoCo Police Reports (Incidents/Drivers) | **NO (Suppressed)** | **CONDITIONAL (Day 31+)** | Md. Bus. Occ. & Prof. § 10-605; MARPC Rule 19-307.3 |
| **National (FARS)** | NHTSA FARS | **NO (Suppressed)** | **NO (Suppressed)** | FARS contains fatal victims only; DPPA / Ethics & state barratry rules |

---

## 3. Contact Channel & Safe Harbor Requirements

For any communication permitted under state law (e.g. Day 31+ direct mail in Maryland):
1. **Timezone Evaluation:** Local time must be derived from coordinates using `timezonefinder` to guarantee 08:00–21:00 recipient window.
2. **DNC Scrub:** Scrubbed against the FTC National Do Not Call registry within the trailing 31 calendar days.
3. **RND Check:** Scrubbed against the FCC Reassigned Numbers Database.
4. **Wireless / Line Type:** If wireless number, requires verified PEWC on file; unconsented automated text or voice outreach is strictly blocked.
5. **Minor / Deceased Protection:** Fatalities (`injury_severity = 'K'`) and minors (<18 years old) are automatically suppressed from direct outreach out of strict ethical and privacy compliance.
