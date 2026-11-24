"""Deliberately does not infer appearance from a photo or identify people."""
from packages.schemas.models import Parameters

def extract(names: list[str]) -> tuple[Parameters, dict]:
    params = Parameters()
    params.characters.left.engraving_text = names[0].strip()
    params.characters.right.engraving_text = names[1].strip()
    return params, {
        'provider': 'mock-defaults-v1',
        'is_mock': True,
        'extraction_confidence': {'left': 0.0, 'right': 0.0},
        'source': 'Explicit demo defaults; photos are not analyzed or sent to any provider.',
        'role_mapping': 'left/right refer to mannequin positions, not inferred photo identities',
    }
