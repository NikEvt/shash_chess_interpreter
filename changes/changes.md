Here is list of changes that need to be added to the ShashChimera project.

More theory to BM-25:
1/ Opening book matched with opening theory
2/ Anomaly check via parsing eval
3/ Endgame pieces matching with ending theory

Tech dept:
4/ parse Alexander eval
5/ Change prompt to fit with new eval of Alexander
6/ Add color of the move in the prompt

Introduce ablation studies to measure the contribution of each design decision independently:
7/ Testing pipeline with deepeval -- to say exactly how much score each feature brings to metrics
8/ Add more some diagrams, visualizations, and statistical analysis to strengthen presentation

https://deepeval.com/docs/introduction

9
Tags as Index-Only Field
Rich tags (eval vocab, Shashin zones, phase) included in tokenized index text but stripped before SLM prompt — amplifies BM25 matching without touching context window
Index build (build_index_text()) vs prompt.py

10
Move Quality Label Enrichment
_move_quality_label() already maps centipawn delta → "blunder"/"inaccuracy"/etc. — ensure these labels also feed BM25 query (e.g. "blunder" → adds "mistake alternative better" tokens)
prompt.py → _build_query()

11
Strip Numbers from BM25 Query
Centipawn scores, WDL percentages, square coordinates (e4, c6) are low-value BM25 tokens — filter them from query construction
_build_query() token filter