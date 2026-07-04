# TriageFlow — Emergency Department Patient Flow

TriageFlow coordinates patient flow in a hospital emergency department, from arrival through
triage, treatment, and discharge, across a limited set of rooms and clinicians.

## Requirements

- Arriving patients are triaged and assigned an acuity level; higher-acuity patients are seen before lower-acuity ones, regardless of arrival order.
- A patient can be moved into a treatment room only if the room is free and a clinician is available; each room and each clinician handles one patient at a time.
- Treatment may begin only after triage is complete, a bed is assigned, and consent is recorded.
- A diagnosis is formed by combining the results of multiple ordered tests, such as labs and imaging; it is not finalized until the required results are in.
- If a patient's condition changes while they are waiting, they are re-triaged and their priority is updated.
- If no clinician accepts a critical case within a short window, it is escalated to the attending physician.
- A patient who leaves without being seen releases their place in the queue and any resources held for them.
- Each patient encounter is tracked as a single record from arrival through discharge.
