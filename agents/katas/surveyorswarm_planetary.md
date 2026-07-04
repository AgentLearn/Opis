# SurveyorSwarm — Autonomous Planetary Survey

SurveyorSwarm coordinates a swarm of autonomous drones surveying an unmapped planet. Each
drone covers assigned sectors, detecting resource deposits and navigation landmarks, and an
orbiting station assembles their observations into a single combined map. Drones operate
autonomously and may fail mid-survey.

## Requirements

- The survey area is divided into sectors and assigned across the currently available drones.
- No two drones are assigned overlapping sectors at the same time, and their flight paths are deconflicted so that drones do not collide.
- Each drone autonomously maps its assigned sectors, detecting resource deposits and navigation landmarks, and streams its observations back toward the station.
- Each drone carries several sensors of different types and applies multiple detection methods; it integrates these heterogeneous readings into a single fused observation before reporting.
- The station combines observations from the drones into one planetary map; it proceeds to assemble a result once a sufficient fraction of sectors have reported, rather than waiting for every drone.
- When two or more drones report the same landmark from overlapping coverage, the duplicate sightings are reconciled into a single confirmed landmark.
- A drone that stops transmitting for a set period is presumed lost, and its unmapped sectors are reassigned to nearby drones.
- A drone that flies out of communication range buffers its observations locally and synchronizes them once it re-establishes contact.
- Resource deposits are ranked by confidence, combining independent sightings of the same deposit from multiple drones.
- Navigation landmarks are cross-checked for consistency before being committed to the shared map; conflicting position fixes are flagged for re-survey.
- As the combined map reveals resource-rich or anomalous areas, drones are re-tasked to survey those areas more closely, adjusting the sector assignments in flight.
- The combined map is transmitted to the orbiting station only once it meets a minimum coverage and confidence threshold.
