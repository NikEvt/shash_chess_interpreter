"""
Chess theory knowledge base.
Each chunk is a self-contained principle tagged with topics.
Retrieved via BM25 by retriever.py — no embeddings needed.
"""

CHUNKS: list[dict] = [
    # ── Opening principles ────────────────────────────────────────────────────
    {
        "id": "opening_center",
        "tags": ["opening", "center", "pawn", "Capablanca"],
        "text": (
            "Control the center with pawns (e4, d4 for White; e5, d5 for Black). "
            "Central pawns limit opponent's piece mobility and give your pieces more squares. "
            "Avoid moving the same piece twice in the opening without good reason."
        ),
    },
    {
        "id": "opening_development",
        "tags": ["opening", "development", "pieces", "Capablanca"],
        "text": (
            "Develop knights before bishops. "
            "Aim to castle within the first 10 moves to safeguard the king. "
            "Do not bring the queen out early — it can be harassed by opponent's developing moves, "
            "wasting tempi."
        ),
    },
    {
        "id": "opening_ruy_lopez",
        "tags": ["opening", "Ruy Lopez", "Spanish", "Bb5", "Nf3", "development"],
        "text": (
            "The Ruy Lopez (1.e4 e5 2.Nf3 Nc6 3.Bb5) puts pressure on the e5 pawn indirectly "
            "by targeting the knight that defends it. White aims for long-term positional pressure. "
            "Black's main responses: 3...a6 (Morphy Defence), 3...Nf6 (Berlin)."
        ),
    },
    {
        "id": "opening_sicilian",
        "tags": ["opening", "Sicilian", "c5", "asymmetric", "Tal", "initiative"],
        "text": (
            "The Sicilian Defence (1.e4 c5) creates an asymmetric pawn structure. "
            "Black fights for the d4 square and counter-attacks on the queenside. "
            "White typically attacks on the kingside. "
            "After 2.Nf3 and 3.d4 cxd4 4.Nxd4, White has a space advantage but Black has the c-file "
            "for counterplay. Best move ideas for White: complete development, then f4-f5 kingside attack."
        ),
    },

    # ── Middlegame: Capablanca / strategic ────────────────────────────────────
    {
        "id": "capablanca_plan",
        "tags": ["Capablanca", "strategic", "plan", "positional", "balanced"],
        "text": (
            "In balanced, strategic positions (Capablanca style): improve your worst-placed piece first. "
            "Look for weak squares in the opponent's camp — squares that cannot be defended by a pawn. "
            "Place knights on outposts: central squares like d5 or e5 supported by a pawn. "
            "Avoid unnecessary pawn moves that create weaknesses."
        ),
    },
    {
        "id": "open_file_strategy",
        "tags": ["open file", "rook", "strategy", "Capablanca", "plan"],
        "text": (
            "Rooks belong on open and half-open files. "
            "Double rooks on an open file to maximize pressure. "
            "A rook on the 7th rank (White on 7th, Black on 2nd) attacks pawns and restricts the king. "
            "Control the only open file — it gives space advantage and infiltration routes."
        ),
    },
    {
        "id": "pawn_structure_isolated",
        "tags": ["pawn", "isolated pawn", "weak", "structure", "strategy"],
        "text": (
            "An isolated pawn (no friendly pawns on adjacent files) is a long-term weakness: "
            "it cannot be defended by another pawn and ties down pieces to its defense. "
            "The side with the isolated pawn must seek active play to compensate. "
            "The opponent should blockade the isolated pawn with a piece (knight is ideal) "
            "and then attack it."
        ),
    },
    {
        "id": "pawn_structure_passed",
        "tags": ["passed pawn", "promotion", "endgame", "plan"],
        "text": (
            "A passed pawn (no enemy pawns blocking or capturing it on its way to promotion) "
            "is a long-term asset. Push it with king support in the endgame. "
            "In the middlegame, a passed pawn ties down enemy pieces to stop it. "
            "Rule: support the passed pawn with the king in the endgame."
        ),
    },
    {
        "id": "bishop_pair",
        "tags": ["bishop pair", "open position", "Capablanca", "advantage"],
        "text": (
            "The bishop pair is powerful in open positions with pawns on both wings. "
            "Two bishops cover both colors and coordinate long-range attacks. "
            "To fight the bishop pair: close the position with pawns, trade one bishop, "
            "place pawns on squares opposite to the surviving bishop's color."
        ),
    },

    # ── Middlegame: Tal / tactical ────────────────────────────────────────────
    {
        "id": "tal_attack",
        "tags": ["Tal", "tactical", "attack", "sacrifice", "kingside"],
        "text": (
            "In tactical, attacking positions (Tal style): look for piece sacrifices to open lines "
            "toward the enemy king. A sacrifice on h6/h3 to shatter king's pawn cover is common. "
            "Check if the king is stuck in the center — open the e-file or d-file to exploit it. "
            "Bishops and queen working together on diagonals create devastating attacks."
        ),
    },
    {
        "id": "king_safety",
        "tags": ["king safety", "castle", "attack", "Tal", "tactics"],
        "text": (
            "King safety is the most critical factor in tactical positions. "
            "An uncastled king in an open position is a target. "
            "Prioritize castling over material if the position is open. "
            "Attacking signals: open file toward the king, pieces aimed at the king, pawn storm near king."
        ),
    },
    {
        "id": "tactical_motifs",
        "tags": ["tactics", "pin", "fork", "discovered attack", "skewer", "Tal"],
        "text": (
            "Common tactical motifs: "
            "Fork — one piece attacks two opponent pieces simultaneously (knight fork is most common). "
            "Pin — a piece cannot move without exposing a more valuable piece behind it. "
            "Discovered attack — moving one piece reveals an attack from another. "
            "Skewer — like a pin but the more valuable piece is in front. "
            "Always check for these before choosing a move."
        ),
    },
    {
        "id": "exchange_sacrifice",
        "tags": ["sacrifice", "exchange sacrifice", "rook for minor piece", "Tal", "positional"],
        "text": (
            "An exchange sacrifice (giving up a rook for a bishop or knight) can be correct when: "
            "the minor piece gains a dominant outpost, the rook had no active role, "
            "or concrete attack compensation exists. "
            "A rook is worth 5 pawns, a minor piece 3, so you need roughly 2 pawns compensation "
            "or strong positional factors."
        ),
    },

    # ── Middlegame: Petrosian / defensive ─────────────────────────────────────
    {
        "id": "petrosian_defense",
        "tags": ["Petrosian", "defensive", "prophylaxis", "solid", "exchange"],
        "text": (
            "In defensive positions (Petrosian style): prophylaxis first — prevent opponent's threats "
            "before they materialize. Exchange your bad pieces for opponent's good pieces. "
            "A 'bad bishop' is blocked by its own pawns on the same color squares. "
            "Trade it for an active opponent's piece to relieve the position."
        ),
    },
    {
        "id": "fortress",
        "tags": ["fortress", "draw", "defensive", "Petrosian", "endgame"],
        "text": (
            "A fortress is a defensive setup where the weaker side creates an impenetrable position "
            "despite material deficit. Common in rook vs rook+pawn endgames. "
            "The defending king must reach a corner safe square. "
            "Example: a lone king in a corner against a bishop-of-the-wrong-color and rook pawn."
        ),
    },
    {
        "id": "blockade",
        "tags": ["blockade", "passed pawn", "defensive", "Petrosian", "knight"],
        "text": (
            "To stop a passed pawn: place a blockading piece directly in front of it. "
            "A knight is the best blockader — it is not dominated by the pawn and still controls squares. "
            "A bishop can blockade but is less effective since the pawn controls its diagonal approach. "
            "Once blockaded, attack the pawn from the sides."
        ),
    },

    # ── Endgame principles ────────────────────────────────────────────────────
    {
        "id": "king_activity_endgame",
        "tags": ["endgame", "king", "active", "centralize", "plan"],
        "text": (
            "In the endgame, the king becomes a powerful piece — activate it immediately. "
            "Centralize the king toward the action. "
            "In king-and-pawn endgames: the opposition (kings facing each other with one square between) "
            "is the key concept. The side NOT having the opposition loses ground."
        ),
    },
    {
        "id": "rule_of_square",
        "tags": ["endgame", "pawn race", "king", "promotion", "rule of square"],
        "text": (
            "Rule of the square: draw a diagonal square from the pawn to the promotion rank. "
            "If the enemy king can step inside this square, it will catch the pawn. "
            "If not, the pawn promotes. This determines whether a king-and-pawn vs king endgame is won or drawn."
        ),
    },
    {
        "id": "rook_endgame_lucena",
        "tags": ["endgame", "rook", "Lucena", "bridge", "promotion"],
        "text": (
            "Lucena position: rook + pawn on the 7th vs rook — this is won. "
            "Technique: 'build a bridge' — use the rook to shield the king from checks. "
            "Steps: 1) advance king to g7/f7, 2) use rook to cut off opponent king, "
            "3) once pawn promotes, deliver checkmate."
        ),
    },
    {
        "id": "rook_endgame_philidor",
        "tags": ["endgame", "rook", "Philidor", "draw", "defense"],
        "text": (
            "Philidor position: rook vs rook + pawn — defending side draws by: "
            "1) place rook on the 6th rank to cut off the enemy king, "
            "2) when the pawn advances to the 6th, switch rook to the 1st rank for back-rank checks. "
            "The key is back-rank harassment once the pawn advances."
        ),
    },
    {
        "id": "opposite_color_bishops",
        "tags": ["endgame", "bishop", "opposite color", "draw", "fortress"],
        "text": (
            "Opposite-color bishop endgames are notoriously drawish even with an extra pawn or two. "
            "The defending bishop controls squares the attacking bishop cannot reach. "
            "Exception: if the attacking side has additional material like rooks or extra pawns on both wings, "
            "it may still win."
        ),
    },
    {
        "id": "endgame_knight_vs_bishop",
        "tags": ["endgame", "knight", "bishop", "comparison"],
        "text": (
            "Knight vs bishop in the endgame: "
            "Knight is better in closed positions with pawns on one wing — it can maneuver to any color. "
            "Bishop is better in open positions or with pawns on both wings — long-range mobility wins. "
            "A bishop on the wrong color (blocked by own pawns) is a major weakness."
        ),
    },

    # ── Material and evaluation ───────────────────────────────────────────────
    {
        "id": "material_values",
        "tags": ["material", "values", "evaluation", "piece"],
        "text": (
            "Standard piece values: pawn=1, knight=3, bishop=3.25, rook=5, queen=9. "
            "In practice: bishop pair bonus ~0.5, rook on open file +0.3, knight on outpost +0.5. "
            "A +1 pawn advantage is usually winning in the endgame but only slightly better in the middlegame. "
            "Mate threats override material count entirely."
        ),
    },
    {
        "id": "evaluation_interpretation",
        "tags": ["evaluation", "centipawns", "winning", "advantage", "score"],
        "text": (
            "Engine evaluation guide: "
            "0.0 to ±0.5: equal position. "
            "±0.5 to ±1.5: slight to clear advantage for the leading side. "
            "±1.5 to ±3.0: significant advantage, usually winning with correct play. "
            "±3.0+: decisive advantage. "
            "Mate in N: forced checkmate regardless of other material."
        ),
    },

    # ── Plans and strategy ────────────────────────────────────────────────────
    {
        "id": "minority_attack",
        "tags": ["minority attack", "pawn", "queenside", "plan", "strategy"],
        "text": (
            "Minority attack: advance fewer pawns against more enemy pawns to create a weakness. "
            "Classic example: White plays b4-b5 against Black's c6-b6 pawn chain, "
            "forcing a weak pawn at c6 or b6. "
            "Then target that weak pawn with rooks and pieces."
        ),
    },
    {
        "id": "outpost_knight",
        "tags": ["outpost", "knight", "d5", "e5", "strong square", "plan"],
        "text": (
            "A knight outpost is a square deep in the opponent's territory that cannot be attacked by a pawn. "
            "d5 and e5 for White, d4 and e4 for Black are classic outposts. "
            "A knight on an outpost is often stronger than a rook because it controls many squares "
            "and cannot be driven away."
        ),
    },
    {
        "id": "two_weaknesses",
        "tags": ["two weaknesses", "strategy", "winning technique", "plan"],
        "text": (
            "The principle of two weaknesses: to convert a small advantage, create a second weakness. "
            "The opponent cannot defend two distant weaknesses simultaneously. "
            "Step 1: pressure one weakness until the opponent is stretched. "
            "Step 2: switch attack to the second weakness. "
            "This is how grandmasters win technically equal-looking endgames."
        ),
    },
    {
        "id": "castling_importance",
        "tags": ["castling", "king safety", "opening", "development", "O-O", "O-O-O"],
        "text": (
            "Castling serves two purposes: king safety and rook development. "
            "Kingside castling (O-O) is safer and faster — preferred in sharp positions. "
            "Queenside castling (O-O-O) connects to an open d-file faster but leaves the king more exposed. "
            "After castling, the rook is immediately active. Delaying castling risks being caught in the center."
        ),
    },
]
