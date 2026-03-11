from src.archetype_openness import Archetype, ArchetypeConfig


def _make_card(name, ata):
    """Helper to create a minimal card dict for testing."""
    return {
        "name": name,
        "deck_colors": {
            "All Decks": {"ata": ata, "ngp": 100},
        },
    }


SIMPLE_CONFIG = ArchetypeConfig(
    set_code="TST",
    scoring_method="simple",
    pack_weights=[1.0, 1.0, 1.0],
    archetypes=[
        Archetype(
            name="BG Elves",
            color_pair="BG",
            auto_weights=False,
            cards={
                "Elf Lord": 0.9,
                "Llanowar Elves": 0.5,
                "Murder": 0.2,
            },
        ),
        Archetype(
            name="UB Control",
            color_pair="UB",
            auto_weights=False,
            cards={
                "Murder": 0.7,
                "Counterspell": 0.8,
            },
        ),
    ],
)


BAYESIAN_CONFIG = ArchetypeConfig(
    set_code="TST",
    scoring_method="bayesian_beta",
    bayesian_prior=1.0,
    pack_weights=[1.0, 1.0, 1.0],
    archetypes=[
        Archetype(
            name="BG Elves",
            color_pair="BG",
            auto_weights=False,
            cards={
                "Elf Lord": 0.9,
                "Llanowar Elves": 0.5,
                "Murder": 0.2,
            },
        ),
        Archetype(
            name="UB Control",
            color_pair="UB",
            auto_weights=False,
            cards={
                "Murder": 0.7,
                "Counterspell": 0.8,
            },
        ),
    ],
)
