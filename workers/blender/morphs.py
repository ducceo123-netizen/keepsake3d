"""Authored bounded geometry recipes. These operate on values, never executable input.

All distances are unscaled demo scene units. They are not physical measurements.
The five head keys are linear offsets stored in the immutable .blend master.
Other face controls drive known, bounded surface-anchored feature meshes.
"""
from __future__ import annotations
import math
from packages.schemas.constants import FACE_MORPH_KEYS

HEAD_KEYS=('face_width','face_height','jaw_width','chin_length','cheek_fullness')
HEAD_RADII=(.51,.46,.55)
HEAD_CENTER_Y=-.015
HEAD_CENTER_Z=1.99
# A conservative authored scene envelope; it does not assert manufacturing clearance.
FACE_ENVELOPE={'x_radius':.73,'y_min':-.79,'y_max':.72,'z_min':1.30,'z_max':3.17}

def neutral_morphs():
    return {key:0.0 for key in FACE_MORPH_KEYS}

def validate_morphs(value):
    if not isinstance(value,dict) or set(value)!=set(FACE_MORPH_KEYS):
        raise ValueError('face_morphs must contain exactly the thirteen authored keys')
    for key,amount in value.items():
        if isinstance(amount,bool) or not isinstance(amount,(int,float)) or not math.isfinite(amount) or not -1 <= amount <= 1:
            raise ValueError(f'{key} must be a finite number between -1 and 1')
    return value

def smooth_peak(value,center,width):
    distance=abs(value-center)/width
    return max(0.0,1.0-distance)**2

def deform_head_point(point,morphs):
    """Exact sum of the five authored shape-key offsets, including negative values."""
    x,y,z=point
    zn=z/HEAD_RADII[2]
    jaw=smooth_peak(zn,-.48,.62)
    cheek=smooth_peak(zn,.02,.48)
    chin=smooth_peak(zn,-.88,.43)
    px=x*(1+.12*morphs.get('face_width',0)+.18*jaw*morphs.get('jaw_width',0)+.08*cheek*morphs.get('cheek_fullness',0))
    # Head height expands upward from its fixed bottom attachment region.
    pz=z+.12*(z+HEAD_RADII[2])*morphs.get('face_height',0)-.055*chin*morphs.get('chin_length',0)
    py=y-.024*cheek*max(0,-y/HEAD_RADII[1])*morphs.get('cheek_fullness',0)
    return px,py,pz

def surface_point(slot_x,x_normalized,z_normalized,morphs,front_offset=0.0):
    """Place features on the actual deformed front hemisphere, with slight overlap."""
    if x_normalized*x_normalized+z_normalized*z_normalized>=.96:
        raise ValueError('Face attachment point exceeds authored surface envelope')
    local=(HEAD_RADII[0]*x_normalized,-HEAD_RADII[1]*math.sqrt(1-x_normalized*x_normalized-z_normalized*z_normalized),HEAD_RADII[2]*z_normalized)
    x,y,z=deform_head_point(local,morphs)
    return slot_x+x,HEAD_CENTER_Y+y-front_offset,HEAD_CENTER_Z+z

def srgb_to_linear_hex(value):
    channels=[int(value[i:i+2],16)/255 for i in (1,3,5)]
    return tuple(c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4 for c in channels)+(1.0,)
