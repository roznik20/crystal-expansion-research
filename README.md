# Investigation of the thermal expansion coefficient of Thiourea  

This repository contains the data, analysis code, figures, and report for a McGill PHYS 258 Experimental Methods II final project on measuring the thermal expansion coefficient of thiourea using temperature-dependent capacitance changes.

## Overview

The goal of this project was to estimate the thermal expansion coefficient of thiourea by monitoring how the capacitance of a custom parallel-plate capacitor changed with temperature. The capacitor was incorporated into a series RLC circuit, and the capacitance was inferred from resonance measurements.

A thiourea sample was attached to one capacitor plate so that thermal dilation produced a small change in plate separation, leading to a measurable change in capacitance. Resonant frequency measurements were performed using Moku hardware and related analysis tools, and the resulting data was processed in Python.

## Repository Structure

```text
.
├── data/ # All collected data: thermocouple, resonance, calibration, and all usable runs
├── notebooks/            # Jupyter notebooks for analysis and exploration
├── scripts/              # Instrument / acquisition / helper scripts
├── results/
│   └── output_plots/     # Visual outputs
├── report/               # Final LaTeX source, bibliography, template, PDFs, logbook
├── LICENSE
└── README.md

```
## Encountered difficulties

In the process of the construction of the custom capacitors, there were many obstacles along the way. 
Perhaps the one that most signficantly impacted the data collection and validity of the results was when the epoxy glue set, it displaced the entire plate setup in a way that the plates were no longer parallel and the capacitor area had significantly changed. Given that we didn't have access to another sample, we had to saw off the capacitor PLA setup and reglue it. In the process, the thiourea sample broke in half and parts were lost. What we did is simply apply glue in between the pieces and reassemble the setup. We had to carry on with the experiment. 

## Note on the use of AI assistance

Portions of the code were written with AI assistance for scaffolding and refactoring. AI assistance was also called upon to accelerate the processes of debugging, documentation consultation and brainstorming. All AI outputs were reviewed, tested, and adapted as needed by us. 

## Authors 
Bogdan-Vladimir Damian, Ethan Hall, Christopher Li, Martin Labartette and Nikita Rozanov

