# AegisWatch — Insider & Intrusion Detection

AegisWatch monitors an enterprise for external intruders and insider threats ("moles"). A
mesh of detection agents watches assets and access points, and a central analysis layer
correlates their signals into investigations, prioritizing effort by the value of the
assets at risk. Agents operate with partial information and may themselves go dark.

## Requirements

- Assets are inventoried and each is assigned a value and criticality; monitoring effort is prioritized toward the highest-value assets.
- Actors are associated with one or more roles, and each role implies a loose expected pattern of which assets it touches and how often; an actor may hold several roles at once.
- An actor's activity is judged against the combined expectation of all of their roles, not any single role in isolation.
- Detection agents are assigned monitoring tasks across assets and access points.
- Each agent draws on several signal sources of different types and applies multiple detection methods, fusing them into a single per-asset risk signal.
- An intrusion is flagged only when multiple independent signals corroborate it; a single weak indicator is not acted upon on its own.
- A trusted insider whose behavior deviates from their established baseline is flagged for review, even though their access is legitimate.
- The rate and value of an actor's access to high-value assets — their value-access velocity — is tracked; an actor whose access velocity or pattern departs from what their roles imply is flagged, even when each individual access is itself authorized.
- Alerts for the same underlying incident raised by different agents are correlated into a single case.
- When a compromise is confirmed, the affected account or network segment is isolated immediately, cutting off its access.
- A flagged case is escalated to an analyst; if it is not triaged within a set window, it escalates to the security lead.
- Under a flood of alerts, signals concerning low-value assets are shed so that high-value threats are not missed.
- A detection agent that stops reporting has its monitoring scope reassigned so that no asset is left uncovered.
- Each investigation is tracked as a single case from detection through resolution.
