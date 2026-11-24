"""Strict, versioned public and worker contracts. AI can only supply values."""
from typing import Literal, Annotated
from pydantic import BaseModel, ConfigDict, Field, field_validator

Name = Annotated[str, Field(max_length=12, pattern=r'^[A-Za-z -]*$')]
HairStyle = Literal['short', 'long', 'bun']
HairColor = Literal['chestnut', 'black', 'blonde', 'silver']
Skin = Literal['warm', 'light', 'deep']
Outfit = Literal['cream', 'blue', 'rose', 'sage']

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

class Character(StrictModel):
    hair_style_asset_id: HairStyle = 'short'
    hair_color_id: HairColor = 'chestnut'
    facial_hair_id: Literal['none', 'beard'] = 'none'
    glasses_asset_id: Literal['none', 'round'] = 'none'
    skin_material_id: Skin = 'warm'
    outfit_palette_id: Outfit = 'cream'
    face_morphs: dict = Field(default_factory=dict)
    engraving_text: Name = ''

    @field_validator('face_morphs')
    @classmethod
    def no_unauthored_morphs(cls, value):
        if value:
            raise ValueError('This demo master has no authored face morphs')
        return value

class Characters(StrictModel):
    left: Character = Field(default_factory=lambda: Character(hair_style_asset_id='bun'))
    right: Character = Field(default_factory=lambda: Character(hair_color_id='black', outfit_palette_id='blue'))

class Parameters(StrictModel):
    schema_version: Literal['1.0'] = '1.0'
    characters: Characters = Field(default_factory=Characters)

class CharacterCorrection(StrictModel):
    hair_style_asset_id: HairStyle | None = None
    hair_color_id: HairColor | None = None
    facial_hair_id: Literal['none', 'beard'] | None = None
    glasses_asset_id: Literal['none', 'round'] | None = None
    skin_material_id: Skin | None = None
    outfit_palette_id: Outfit | None = None
    engraving_text: Name | None = None

class CharacterCorrections(StrictModel):
    left: CharacterCorrection | None = None
    right: CharacterCorrection | None = None

class Corrections(StrictModel):
    characters: CharacterCorrections

class CreateSession(StrictModel):
    design_id: Literal['better-together'] = 'better-together'
    design_version: Literal['0.1.0-demo'] = '0.1.0-demo'

class Submit(StrictModel):
    consent: Literal[True]
    names: list[Name] = Field(default_factory=lambda: ['', ''], min_length=2, max_length=2)

    @field_validator('consent', mode='before')
    @classmethod
    def explicit_consent(cls, value):
        if value is not True:
            raise ValueError('Explicit consent must be true')
        return value

class Approval(StrictModel):
    model_revision: int = Field(ge=1)
    job_checksum: str = Field(pattern=r'^[0-9a-f]{64}$')

STATES = {
    'CREATED': {'PHOTO_UPLOADED', 'CANCELLED', 'EXPIRED'},
    'PHOTO_UPLOADED': {'PHOTO_VALIDATING', 'CREATED', 'CANCELLED', 'EXPIRED'},
    'PHOTO_VALIDATING': {'AI_ANALYZING', 'FAILED', 'CANCELLED', 'EXPIRED'},
    'AI_ANALYZING': {'PARAMETERS_READY', 'MANUAL_REVIEW_REQUIRED', 'FAILED', 'CANCELLED', 'EXPIRED'},
    'PARAMETERS_READY': {'MODEL_BUILDING', 'FAILED', 'CANCELLED', 'EXPIRED'},
    'MODEL_BUILDING': {'MODEL_RENDERING', 'FAILED', 'CANCELLED', 'EXPIRED'},
    'MODEL_RENDERING': {'QA_RUNNING', 'FAILED', 'CANCELLED', 'EXPIRED'},
    'QA_RUNNING': {'PREVIEW_READY', 'MANUAL_REVIEW_REQUIRED', 'FAILED', 'CANCELLED', 'EXPIRED'},
    'PREVIEW_READY': {'CUSTOMER_APPROVED', 'PARAMETERS_READY', 'CANCELLED', 'EXPIRED'},
    'CUSTOMER_APPROVED': {'PARAMETERS_READY', 'CANCELLED', 'EXPIRED'},
    'FAILED': {'PHOTO_VALIDATING', 'PARAMETERS_READY', 'CANCELLED', 'EXPIRED'},
    'MANUAL_REVIEW_REQUIRED': {'PARAMETERS_READY', 'CANCELLED', 'EXPIRED'},
    'CANCELLED': set(), 'EXPIRED': set(),
}

def assert_transition(current: str, target: str):
    if target not in STATES.get(current, set()):
        raise ValueError(f'Invalid state transition: {current} -> {target}')

class EngravingConstraints(StrictModel):
    max_characters: Literal[12]
    pattern: Literal['^[A-Za-z -]{0,12}$']
    max_width_scene_units: float = Field(gt=0)
    mode: Literal['raised_demo_label']
    manufacturing_relief_validated: Literal[False]

class ValidationRules(StrictModel):
    locked_geometry_tolerance: Literal[0]
    require_finite_vertices: Literal[True]
    require_closed_component_edges: Literal[True]
    join_clearance_validated: Literal[False]
    intersections_validated: Literal[False]

class AssetSlots(StrictModel):
    hair_style_asset_id: list[HairStyle] = Field(min_length=1)
    facial_hair_id: list[Literal['none','beard']] = Field(min_length=1)
    glasses_asset_id: list[Literal['none','round']] = Field(min_length=1)

class Materials(StrictModel):
    hair_color_id: list[HairColor] = Field(min_length=1)
    skin_material_id: list[Skin] = Field(min_length=1)
    outfit_palette_id: list[Outfit] = Field(min_length=1)

class Anchors(StrictModel):
    left: Literal['ANCHOR_LEFT']
    right: Literal['ANCHOR_RIGHT']

class DemoManifest(StrictModel):
    design_id: Literal['better-together']
    version: Literal['0.1.0-demo']
    status: Literal['DEMO_NOT_PRINT_APPROVED']
    master_blend_asset: Literal['assets/designs/better-together/0.1.0-demo/master.blend']
    master_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    character_slots: list[Literal['left','right']] = Field(min_length=2,max_length=2)
    geometry_lock_objects: list[str] = Field(min_length=8)
    allowed_asset_slots: AssetSlots
    allowed_shape_keys: dict = Field(max_length=0)
    allowed_materials: Materials
    engraving_constraints: EngravingConstraints
    attachment_anchors: Anchors
    assembly_part_ids: list[Literal['ASSEMBLY_LEFT','ASSEMBLY_RIGHT']] = Field(min_length=2,max_length=2)
    preview_cameras: list[Literal['three_quarter','front','side','back']] = Field(min_length=1)
    export_units: Literal['DEMO_SCENE_UNITS_NOT_MANUFACTURING_SCALE']
    print_profiles: list = Field(max_length=0)
    validation_rules: ValidationRules
    print_approved: Literal[False]

    @field_validator('character_slots','assembly_part_ids')
    @classmethod
    def no_duplicate_slots(cls,value):
        if len(set(value))!=2:
            raise ValueError('Both distinct assembly slots are required')
        return value

    @field_validator('geometry_lock_objects')
    @classmethod
    def require_locked_geometry(cls,value):
        required={'HEART_BASE_LEFT','HEART_BASE_RIGHT','BODY_LEFT','BODY_RIGHT','ANCHOR_LEFT','ANCHOR_RIGHT','HAND_left_0','HAND_right_0'}
        if not required.issubset(value) or len(value)!=len(set(value)):
            raise ValueError('Required locked base, body, hands, and anchor objects must appear exactly once')
        return value
