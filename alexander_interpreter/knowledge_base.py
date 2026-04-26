"""
Chess theory knowledge base for Alexander interpreter.

Extended vs the original: covers all 14 Shashin zones and
Alexander-specific concepts (WDL interpretation, PV reading, eval components).
"""

CHUNKS: list[dict] = [
    # ── Opening principles ─────────────────────────────────────────────────────
    {
        "id": "opening_center",
        "tags": ["opening", "general"],
        "text": (
            "In the opening, controlling the center with pawns (e4, d4, e5, d5) "
            "gives your pieces maximum scope. Develop knights before bishops, "
            "and castle early to protect your king. Avoid moving the same piece twice "
            "unless there is a concrete tactical reason."
        ),
    },
    {
        "id": "opening_development",
        "tags": ["opening", "general"],
        "text": (
            "Rapid piece development is more important than material gains in the opening. "
            "Each tempo lost in development allows the opponent to seize the initiative. "
            "The Ruy Lopez (1.e4 e5 2.Nf3 Nc6 3.Bb5) is a classic example: "
            "White pressures the e5 pawn while developing and preparing to castle."
        ),
    },
    {
        "id": "opening_ruy_lopez",
        "tags": ["opening", "ruy-lopez", "Capablanca"],
        "text": (
            "The Ruy Lopez leads to rich strategic battles. White's plan is to "
            "maintain central pressure with d4, fight for the e5 square, and "
            "use space advantage. Black typically counters with ...d6 or ...d5 "
            "to free the position. The Berlin Defence (3...Nf6) exchanges queens "
            "and leads to equal endgames."
        ),
    },
    {
        "id": "opening_sicilian",
        "tags": ["opening", "sicilian", "Tal", "Capablanca"],
        "text": (
            "The Sicilian Defence (1.e4 c5) is Black's most combative reply. "
            "It creates asymmetry: White gets a space advantage and kingside attacking chances, "
            "Black gets queenside counterplay with the half-open c-file. "
            "In sharp lines (Najdorf, Dragon), piece activity and calculation dominate over pawn structure."
        ),
    },

    # ── Shashin zone theory ────────────────────────────────────────────────────
    {
        "id": "zone_high_tal_tactics",
        "tags": ["middlegame", "Tal", "tactics", "HIGH_TAL", "MIDDLE_HIGH_TAL"],
        "text": (
            "In a decisive advantage (win probability > 89%), the priority is to find "
            "the fastest forcing sequence. Look for king attacks, back-rank mates, "
            "piece sacrifices that open files toward the king, and combinations "
            "that win material while maintaining the attack. Do not simplify unless "
            "the resulting endgame is technically won."
        ),
    },
    {
        "id": "zone_middle_tal_attack",
        "tags": ["middlegame", "Tal", "attack", "MIDDLE_TAL", "MIDDLE_LOW_TAL"],
        "text": (
            "With a large advantage (win probability 79–89%), aggressive piece coordination "
            "is key. Bring all pieces into the attack before launching. "
            "The principle of accumulation (Karpov's method): each small improvement "
            "adds up to a decisive advantage. A rook on the seventh rank, "
            "a passed pawn, a weak king — combine these for a winning plan."
        ),
    },
    {
        "id": "zone_low_tal_convert",
        "tags": ["middlegame", "endgame", "Tal", "LOW_TAL", "CAPABLANCA_TAL"],
        "text": (
            "With a clear advantage (win probability 50–79%), the technique of "
            "conversion matters. Identify the opponent's weakest point and apply "
            "systematic pressure. Passed pawns advance with rook support. "
            "Rook endgames are technically won when you have a passed pawn + active rook. "
            "The Lucena position is the key winning technique."
        ),
    },
    {
        "id": "zone_capablanca_strategy",
        "tags": ["middlegame", "Capablanca", "CAPABLANCA", "CAPABLANCA_TAL", "CAPABLANCA_PETROSIAN"],
        "text": (
            "In equal or near-equal positions (win probability 24–75%), strategic "
            "planning decides. Key elements: weak squares (especially d5 for White, d4 for Black), "
            "open files for rooks, the two bishops vs knight, "
            "pawn majority on one flank. Improve the worst piece first (Silman's principle). "
            "Prophylaxis (anticipating and preventing opponent's plans) is essential."
        ),
    },
    {
        "id": "zone_petrosian_defense",
        "tags": ["middlegame", "Petrosian", "defense", "LOW_PETROSIAN", "MIDDLE_LOW_PETROSIAN"],
        "text": (
            "When defending a slightly inferior position (win probability 15–25%), "
            "active defense is better than passive waiting. Create counterplay on "
            "the opposite wing, complicate the position with piece sacrifices, "
            "and exchange pieces that strengthen the attack. "
            "The side with fewer threats should seek activity."
        ),
    },
    {
        "id": "zone_deep_petrosian_fortress",
        "tags": ["endgame", "Petrosian", "fortress", "HIGH_PETROSIAN", "MIDDLE_PETROSIAN"],
        "text": (
            "In a difficult or near-lost position (win probability 0–15%), "
            "the defender must seek a fortress. A fortress is a structure where "
            "the superior side cannot make progress despite the material advantage. "
            "Key techniques: eliminate the attacking pieces through exchanges, "
            "reach a position where checkmate is impossible, and create stalemate chances. "
            "Opposite-colored bishops dramatically increase drawing chances."
        ),
    },

    # ── Middlegame strategy ────────────────────────────────────────────────────
    {
        "id": "middlegame_open_file",
        "tags": ["middlegame", "Capablanca", "rook"],
        "text": (
            "Open files are highways for rooks. Seize the only open file with your rooks "
            "and double them. A rook on the 7th rank (or 2nd rank for Black) ties down "
            "the opponent's king and threatens pawns. "
            "The rook behind a passed pawn — either pushing it or stopping it — "
            "follows the Tarrasch rule."
        ),
    },
    {
        "id": "middlegame_weak_square",
        "tags": ["middlegame", "Capablanca", "strategic"],
        "text": (
            "Weak squares are squares that cannot be defended by pawns. "
            "The classic weakness is d5 for Black in the Ruy Lopez after ...c5xd4. "
            "A knight entrenched on a weak square with no pawn that can attack it "
            "is a long-term strategic advantage. "
            "Force the opponent to create weak squares by exchanging the defender."
        ),
    },
    {
        "id": "middlegame_two_bishops",
        "tags": ["middlegame", "Capablanca", "bishops"],
        "text": (
            "The two bishops in an open position are a significant advantage. "
            "They control both colors and dominate knights in open positions. "
            "The player with two bishops should open the position with pawn breaks. "
            "When fighting against two bishops: close the position with pawns, "
            "exchange one bishop, or create a fortress with pawns on same color."
        ),
    },
    {
        "id": "middlegame_king_attack",
        "tags": ["middlegame", "Tal", "king", "attack"],
        "text": (
            "A king attack requires: open lines toward the king, "
            "a pawn shelter weakness (h3-g4 or f3-g3 break), "
            "and piece coordination (queen + rook + bishop/knight). "
            "The sacrifice h4-h5xg6 opens the h-file. The Greek gift (Bxh7+) "
            "works when Ng5+ Qh5 follows. Always verify the king cannot escape before sacrificing."
        ),
    },
    {
        "id": "middlegame_prophylaxis",
        "tags": ["middlegame", "Petrosian", "prophylaxis", "defense"],
        "text": (
            "Prophylaxis means preventing the opponent's plan before it begins. "
            "Ask: what does my opponent want to do next? Then stop it. "
            "The move Re1 may prevent ...Nd4; a2-a4 stops ...b5. "
            "Petrosian's method: anticipate threats 2-3 moves ahead and neutralize them. "
            "In defensive positions, prophylaxis is more valuable than direct counterplay."
        ),
    },

    # ── PV and engine evaluation interpretation ────────────────────────────────
    {
        "id": "pv_reading",
        "tags": ["evaluation", "general"],
        "text": (
            "The engine's principal variation (PV) shows the best continuation for both sides. "
            "It reveals the strategic purpose of the best move: if the PV involves a knight "
            "reaching d5, the best move likely prepares or enables that outpost. "
            "If the PV includes ...Rxa2, the engine values counterplay. "
            "Reading the PV helps explain WHY a move is best, not just that it is."
        ),
    },
    {
        "id": "wdl_interpretation",
        "tags": ["evaluation", "general"],
        "text": (
            "The WDL (Win-Draw-Loss) probability is more informative than centipawn score alone. "
            "A centipawn advantage of +0.5 with WDL 60/30/10 is a real advantage; "
            "the same +0.5 with WDL 40/55/5 is mostly equal. "
            "WDL depends on position type: a pawn up in a rook endgame is often winning "
            "while the same advantage with opposite-colored bishops is usually drawn."
        ),
    },
    {
        "id": "multipv_alternatives",
        "tags": ["evaluation", "general"],
        "text": (
            "When an engine shows multiple top moves (MultiPV), the gap between them matters. "
            "A large gap (>50 centipawns between 1st and 2nd best) means there is only one "
            "correct move — the position is forcing. A small gap (< 20cp) means "
            "several moves are nearly equivalent and the choice is about style or long-term plans. "
            "Compare the WDL of the moves played with the top engine suggestion."
        ),
    },

    # ── Endgame principles ─────────────────────────────────────────────────────
    {
        "id": "endgame_king_active",
        "tags": ["endgame", "Capablanca"],
        "text": (
            "In the endgame, the king becomes a powerful attacking piece. "
            "Centralize the king immediately when queens are off the board. "
            "The rule of the square: if the king can reach the square of a passed pawn "
            "before it promotes, it can stop it. In king-pawn endgames, opposition is key."
        ),
    },
    {
        "id": "endgame_rook",
        "tags": ["endgame", "rook", "Capablanca"],
        "text": (
            "Rook endgames are the most common and most technical. "
            "The Lucena position (rook + pawn vs rook, king in front) is a win with "
            "the 'bridge building' technique. "
            "The Philidor position (rook defends from the third rank, then checks from behind) "
            "is the main drawing technique for the defender."
        ),
    },
    {
        "id": "endgame_passed_pawn",
        "tags": ["endgame", "pawn", "Capablanca", "Tal"],
        "text": (
            "A passed pawn is a potential queen. Support it with the rook from behind, "
            "use the king to escort it, and avoid exchanging rooks unless "
            "the resulting king-pawn endgame is won. "
            "A connected passed pawn pair is almost always winning. "
            "Blockade a passed pawn with your king or a knight (not a rook, which wastes activity)."
        ),
    },
    {
        "id": "endgame_opposite_bishops",
        "tags": ["endgame", "draw", "Petrosian", "bishops"],
        "text": (
            "Opposite-colored bishop endgames are notoriously drawish. "
            "Even with two extra pawns, the defending side can often hold "
            "by placing pawns on the same color as the opponent's bishop. "
            "The exception: if the attacking side can create passed pawns on BOTH wings, "
            "the defending bishop cannot cover both queening squares."
        ),
    },

    # ── Tactics ───────────────────────────────────────────────────────────────
    {
        "id": "tactics_pin",
        "tags": ["tactics", "Tal"],
        "text": (
            "A pin immobilizes a piece because moving it would expose a more valuable piece. "
            "An absolute pin (against the king) means the pinned piece legally cannot move. "
            "Exploit pins by attacking the pinned piece with pawns or knights. "
            "Break a pin by interposing a piece, moving the pinned piece's king, "
            "or counterattacking the pinning piece."
        ),
    },
    {
        "id": "tactics_fork",
        "tags": ["tactics", "Tal"],
        "text": (
            "A fork attacks two or more pieces simultaneously. "
            "Knight forks are most dangerous because knights jump over other pieces. "
            "Look for knight forks on e5, d5, c6, f6 in typical positions. "
            "Pawn forks (e.g., d5 forking a c6 knight and e6 pawn) are common in middlegames. "
            "Always check if a pawn advance creates fork threats."
        ),
    },
    {
        "id": "tactics_sacrifice",
        "tags": ["tactics", "Tal", "king"],
        "text": (
            "A piece sacrifice is justified when it gives lasting compensation: "
            "a king exposed to attack, a material deficit compensated by a passed pawn, "
            "or control of a key square. Exchange sacrifices (rook for minor piece) "
            "often give long-term positional pressure. "
            "Always calculate 3-4 moves deep before sacrificing; the opponent "
            "may have a defensive resource you missed."
        ),
    },
    {
        "id": "tactics_back_rank",
        "tags": ["tactics", "Tal", "Petrosian"],
        "text": (
            "Back-rank checkmate (checkmate on the first or eighth rank by a rook or queen) "
            "is one of the most common tactical motifs. It occurs when the king "
            "has no escape squares behind the pawn structure. "
            "Prevent it by advancing a pawn (h3 or g3) or moving the king to a safer square. "
            "Create it by eliminating the king's escape squares, then delivering the decisive check."
        ),
    },

    # ── Move quality interpretation ────────────────────────────────────────────
    {
        "id": "move_quality_blunder",
        "tags": ["evaluation", "general"],
        "text": (
            "A blunder (> 200 centipawn loss) typically allows a winning tactic or "
            "gives up a piece without compensation. When the engine recommends a different move, "
            "compare the resulting positions: does the played move allow a fork, pin, skewer, "
            "or back-rank mate? Identify the specific tactical or strategic failing. "
            "The best move either wins material, creates a decisive attack, or avoids a catastrophic weakness."
        ),
    },
    {
        "id": "move_quality_inaccuracy",
        "tags": ["evaluation", "general"],
        "text": (
            "An inaccuracy (50–100 centipawn loss) often means a missed opportunity rather than "
            "a direct losing mistake. The engine's suggestion may exploit a weak square, "
            "improve piece activity, or maintain tension that the played move released. "
            "In the Capablanca zone (equal positions), inaccuracies are particularly costly "
            "because small advantages compound into winning endgames."
        ),
    },
]
