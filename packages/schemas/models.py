"""Strict versioned data contracts. Browser measurements are untrusted input."""
import math
import re
from typing import Literal, Annotated
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .constants import (DESIGN_ID, DESIGN_VERSION, PARAMS_SCHEMA_VERSION, FACE_MORPH_KEYS, HAIR_STYLES, HAIR_COLORS, SKIN_MATERIALS, CLOTHING_PALETTES, FACIAL_HAIR_STYLES, GLASSES_STYLES)

Name = Annotated[str, Field(max_length=12, pattern=r'^[A-Za-z -]*$')]
OpaqueID = Annotated[str, Field(pattern=r'^[0-9a-f]{32}$')]
Sha256 = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
Morph = Annotated[float, Field(ge=-1,le=1,allow_inf_nan=False)]
Normalized = Annotated[float, Field(ge=0,le=1,allow_inf_nan=False)]
HairStyle = Literal[*HAIR_STYLES]
HairColor = Literal[*HAIR_COLORS]
Skin = Literal[*SKIN_MATERIALS]
Outfit = Literal[*CLOTHING_PALETTES]
FacialHair = Literal[*FACIAL_HAIR_STYLES]
Glasses = Literal[*GLASSES_STYLES]

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)

class FaceMorphs(StrictModel):
    face_width: Morph=0.0
    face_height: Morph=0.0
    jaw_width: Morph=0.0
    chin_length: Morph=0.0
    cheek_fullness: Morph=0.0
    eye_spacing: Morph=0.0
    eye_size: Morph=0.0
    brow_thickness: Morph=0.0
    brow_arch: Morph=0.0
    nose_width: Morph=0.0
    nose_projection: Morph=0.0
    mouth_width: Morph=0.0
    smile: Morph=0.0

class Character(StrictModel):
    hair_style_asset_id: HairStyle='short'
    hair_color_id: HairColor='chestnut'
    facial_hair_id: FacialHair='none'
    glasses_asset_id: Glasses='none'
    skin_material_id: Skin='warm'
    outfit_palette_id: Outfit='cream'
    pants_palette_id: Outfit='blue'
    shoes_palette_id: Outfit='white'
    face_morphs: FaceMorphs=Field(default_factory=FaceMorphs)
    engraving_text: Name=''

class Characters(StrictModel):
    left: Character=Field(default_factory=lambda:Character(hair_style_asset_id='bun'))
    right: Character=Field(default_factory=lambda:Character(hair_color_id='black',outfit_palette_id='blue',pants_palette_id='brown'))

class Parameters(StrictModel):
    schema_version: Literal[PARAMS_SCHEMA_VERSION]=PARAMS_SCHEMA_VERSION
    characters: Characters=Field(default_factory=Characters)

class FaceMorphCorrections(StrictModel):
    face_width: Morph|None=None
    face_height: Morph|None=None
    jaw_width: Morph|None=None
    chin_length: Morph|None=None
    cheek_fullness: Morph|None=None
    eye_spacing: Morph|None=None
    eye_size: Morph|None=None
    brow_thickness: Morph|None=None
    brow_arch: Morph|None=None
    nose_width: Morph|None=None
    nose_projection: Morph|None=None
    mouth_width: Morph|None=None
    smile: Morph|None=None

class CharacterCorrection(StrictModel):
    hair_style_asset_id: HairStyle|None=None
    hair_color_id: HairColor|None=None
    facial_hair_id: FacialHair|None=None
    glasses_asset_id: Glasses|None=None
    skin_material_id: Skin|None=None
    outfit_palette_id: Outfit|None=None
    pants_palette_id: Outfit|None=None
    shoes_palette_id: Outfit|None=None
    face_morphs: FaceMorphCorrections|None=None
    engraving_text: Name|None=None

class CharacterCorrections(StrictModel):
    left: CharacterCorrection|None=None
    right: CharacterCorrection|None=None

class Corrections(StrictModel):
    characters: CharacterCorrections

class CreateSession(StrictModel):
    design_id: Literal[DESIGN_ID]=DESIGN_ID
    design_version: Literal[DESIGN_VERSION]=DESIGN_VERSION

class ConsentModel(StrictModel):
    consent: Literal[True]

    @field_validator('consent',mode='before')
    @classmethod
    def explicit_consent(cls,value):
        if value is not True:
            raise ValueError('Explicit consent must be true')
        return value

class Submit(ConsentModel):
    names: list[Name]=Field(default_factory=lambda:['',''],min_length=2,max_length=2)
    mode: Literal['photo','technical-fixture']='photo'
    appearance_profile_id: OpaqueID|None=None
    appearance_profile_sha256: Sha256|None=None

    @model_validator(mode='after')
    def required_photo_profile(self):
        if self.mode=='photo' and (not self.appearance_profile_id or not self.appearance_profile_sha256):
            raise ValueError('Analyze your photos, select both people, and review the appearance profile before generation')
        if self.mode=='technical-fixture' and (self.appearance_profile_id or self.appearance_profile_sha256):
            raise ValueError('Technical fixtures cannot claim a photo-derived appearance profile')
        return self

class FaceAssignment(StrictModel):
    photo_id: OpaqueID
    photo_sha256: Sha256
    face_index: int=Field(ge=0,le=9)
    face_count: int=Field(ge=1,le=10)
    box: list[Normalized]=Field(min_length=4,max_length=4)

    @model_validator(mode='after')
    def selected_face_and_bounds(self):
        if self.face_index>=self.face_count:
            raise ValueError('Select an existing detected face')
        x,y,width,height=self.box
        if width<=0 or height<=0 or x+width>1.000001 or y+height>1.000001:
            raise ValueError('Face bounds must fit inside the normalized photo')
        return self

class Assignments(StrictModel):
    left: FaceAssignment
    right: FaceAssignment

    @model_validator(mode='after')
    def distinct_faces(self):
        if (self.left.photo_id,self.left.face_index)==(self.right.photo_id,self.right.face_index):
            raise ValueError('Select a distinct face for each figurine; assignment is never inferred')
        if self.left.photo_id==self.right.photo_id and self.left.face_count!=self.right.face_count:
            raise ValueError('Face counts for the same photo must agree')
        return self

APPEARANCE_FIELDS=set(Character.model_fields)-{'face_morphs'} | {'face_morphs.'+key for key in FACE_MORPH_KEYS}

class Observations(StrictModel):
    measurements: dict[str,float]=Field(min_length=1,max_length=32)
    confidence: Literal['low','medium','high']|None=None
    confidence_basis: Literal['heuristic-quality-not-model-probability']='heuristic-quality-not-model-probability'
    observed_fields: list[str]=Field(min_length=1,max_length=32)
    defaulted_fields: list[str]=Field(default_factory=list,max_length=32)
    manual_fields: list[str]=Field(default_factory=list,max_length=32)
    warnings: list[Annotated[str,Field(max_length=160)]]=Field(default_factory=list,max_length=12)

    @field_validator('measurements')
    @classmethod
    def bounded_measurements(cls,value):
        if any(not re.fullmatch(r'[a-z][a-z0-9_]{0,39}',key) or not math.isfinite(number) or abs(number)>100_000_000 for key,number in value.items()):
            raise ValueError('Measurements must have bounded numeric values and simple field names')
        return value

    @field_validator('observed_fields','defaulted_fields','manual_fields')
    @classmethod
    def known_fields(cls,value):
        if len(value)!=len(set(value)) or not set(value).issubset(APPEARANCE_FIELDS):
            raise ValueError('Observed/defaulted/manual fields must be unique supported appearance fields')
        return value

    @model_validator(mode='after')
    def no_conflicting_claims(self):
        if set(self.observed_fields)&set(self.defaulted_fields):
            raise ValueError('An appearance field cannot be both observed and defaulted')
        return self

class CharacterObservations(StrictModel):
    left: Observations
    right: Observations

class AppearanceProfileInput(ConsentModel):
    source: Literal['browser-mediapipe-v1']
    analysis_version: Literal['1.0']='1.0'
    reviewed: Literal[True]
    assignments: Assignments
    parameters: Parameters
    observations: CharacterObservations
    manual_overrides: Corrections=Field(default_factory=lambda:Corrections(characters=CharacterCorrections()))

    @field_validator('parameters',mode='before')
    @classmethod
    def complete_reviewed_parameters(cls,value):
        if not isinstance(value,dict) or set(value)!={'schema_version','characters'}:
            raise ValueError('A reviewed photo profile must include the complete parameter object')
        characters=value.get('characters',{})
        if not isinstance(characters,dict) or set(characters)!={'left','right'}:
            raise ValueError('Both reviewed character slots are required')
        for character in characters.values():
            if not isinstance(character,dict) or set(character)!=set(Character.model_fields):
                raise ValueError('Every reviewed appearance field must be explicit; omitted fields are not silently defaulted')
            if not isinstance(character['face_morphs'],dict) or set(character['face_morphs'])!=set(FACE_MORPH_KEYS):
                raise ValueError('Every bounded face control must be explicit in the reviewed profile')
        return value

    @field_validator('reviewed',mode='before')
    @classmethod
    def explicit_review(cls,value):
        if value is not True:
            raise ValueError('Confirm the selected people and reviewed appearance before generation')
        return value

class Approval(StrictModel):
    model_revision: int=Field(ge=1)
    job_checksum: Sha256

STATES={
    'CREATED':{'PHOTO_UPLOADED','CANCELLED','EXPIRED'},
    'PHOTO_UPLOADED':{'PHOTO_VALIDATING','PARAMETERS_READY','CREATED','CANCELLED','EXPIRED'},
    'PHOTO_VALIDATING':{'AI_ANALYZING','PARAMETERS_READY','FAILED','CANCELLED','EXPIRED'},
    'AI_ANALYZING':{'PARAMETERS_READY','MANUAL_REVIEW_REQUIRED','FAILED','CANCELLED','EXPIRED'},
    'PARAMETERS_READY':{'MODEL_BUILDING','FAILED','CANCELLED','EXPIRED'},
    'MODEL_BUILDING':{'MODEL_RENDERING','FAILED','CANCELLED','EXPIRED'},
    'MODEL_RENDERING':{'QA_RUNNING','FAILED','CANCELLED','EXPIRED'},
    'QA_RUNNING':{'PREVIEW_READY','MANUAL_REVIEW_REQUIRED','FAILED','CANCELLED','EXPIRED'},
    'PREVIEW_READY':{'CUSTOMER_APPROVED','PARAMETERS_READY','CANCELLED','EXPIRED'},
    'CUSTOMER_APPROVED':{'PARAMETERS_READY','CANCELLED','EXPIRED'},
    'FAILED':{'PHOTO_VALIDATING','PARAMETERS_READY','CANCELLED','EXPIRED'},
    'MANUAL_REVIEW_REQUIRED':{'PARAMETERS_READY','CANCELLED','EXPIRED'},
    'CANCELLED':set(),'EXPIRED':set(),
}

def assert_transition(current:str,target:str):
    if target not in STATES.get(current,set()):
        raise ValueError(f'Invalid state transition: {current} -> {target}')

class EngravingConstraints(StrictModel):
    max_characters: Literal[12]
    pattern: Literal['^[A-Za-z -]{0,12}$']
    max_width_scene_units: float=Field(gt=0)
    mode: Literal['raised_demo_label']
    manufacturing_relief_validated: Literal[False]

class ValidationRules(StrictModel):
    locked_geometry_tolerance: Literal[0]
    require_finite_vertices: Literal[True]
    require_closed_component_edges: Literal[True]
    join_clearance_validated: Literal[False]
    intersections_validated: Literal[False]
    # Optional additional demo envelope checks are declared by the model author.
    require_feature_envelopes: bool=True
    require_unchanged_anchors: bool=True

class AssetSlots(StrictModel):
    hair_style_asset_id: list[HairStyle]=Field(min_length=1)
    facial_hair_id: list[FacialHair]=Field(min_length=1)
    glasses_asset_id: list[Glasses]=Field(min_length=1)

class Materials(StrictModel):
    hair_color_id: list[HairColor]=Field(min_length=1)
    skin_material_id: list[Skin]=Field(min_length=1)
    outfit_palette_id: list[Outfit]=Field(min_length=1)
    pants_palette_id: list[Outfit]=Field(min_length=1)
    shoes_palette_id: list[Outfit]=Field(min_length=1)

class Anchors(StrictModel):
    left: Literal['ANCHOR_LEFT']
    right: Literal['ANCHOR_RIGHT']

class MorphBounds(StrictModel):
    min: Literal[-1.0]
    max: Literal[1.0]
    default: Literal[0.0]

class DemoManifest(StrictModel):
    design_id: Literal[DESIGN_ID]
    version: Literal[DESIGN_VERSION]
    status: Literal['DEMO_NOT_PRINT_APPROVED']
    master_blend_asset: Literal[f'assets/designs/{DESIGN_ID}/{DESIGN_VERSION}/master.blend']
    master_sha256: Sha256
    character_slots: list[Literal['left','right']]=Field(min_length=2,max_length=2)
    geometry_lock_objects: list[str]=Field(min_length=8)
    allowed_asset_slots: AssetSlots
    allowed_shape_keys: dict[str,MorphBounds]=Field(min_length=13,max_length=13)
    allowed_materials: Materials
    engraving_constraints: EngravingConstraints
    attachment_anchors: Anchors
    assembly_part_ids: list[Literal['ASSEMBLY_LEFT','ASSEMBLY_RIGHT']]=Field(min_length=2,max_length=2)
    preview_cameras: list[Literal['three_quarter','front','side','back']]=Field(min_length=1)
    export_units: Literal['DEMO_SCENE_UNITS_NOT_MANUFACTURING_SCALE']
    print_profiles: list=Field(max_length=0)
    validation_rules: ValidationRules
    print_approved: Literal[False]

    @field_validator('allowed_shape_keys')
    @classmethod
    def authored_keys_only(cls,value):
        if set(value)!=set(FACE_MORPH_KEYS):
            raise ValueError('Manifest must define every supported bounded face control')
        return value

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
