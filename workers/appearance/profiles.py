"""Browser analysis provenance and safe merging; no photo inference is fabricated here."""
import copy
import hashlib
import json
from packages.schemas.models import APPEARANCE_FIELDS, Parameters


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True)


def sha(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def merge_parameters(parameters,corrections):
    merged=copy.deepcopy(parameters)
    for slot,changes in corrections.get('characters',{}).items():
        if not changes:
            continue
        for key,value in changes.items():
            if key=='face_morphs':
                merged['characters'][slot]['face_morphs'].update(value)
            else:
                merged['characters'][slot][key]=value
    return Parameters.model_validate(merged).model_dump()


def merge_overrides(previous,changes):
    merged=copy.deepcopy(previous or {'characters':{}})
    merged.setdefault('characters',{})
    for slot,fields in changes.get('characters',{}).items():
        if not fields:
            continue
        target=merged['characters'].setdefault(slot,{})
        for key,value in fields.items():
            if key=='face_morphs':
                target.setdefault('face_morphs',{}).update(value)
            else:
                target[key]=value
    return merged


def changed_overrides(parameters,changes):
    """Attribute a correction only to fields whose reviewed values actually changed."""
    result={'characters':{}}
    for slot,fields in changes.get('characters',{}).items():
        changed={}
        for key,value in (fields or {}).items():
            previous=parameters['characters'][slot][key]
            if key=='face_morphs':
                different={name:number for name,number in value.items() if previous[name]!=number}
                if different:
                    changed[key]=different
            elif previous!=value:
                changed[key]=value
        if changed:
            result['characters'][slot]=changed
    return result


def describe_fields(payload):
    """Store all unobserved/unreviewed fields as defaults rather than measured claims."""
    payload=copy.deepcopy(payload)
    for slot,observation in payload.get('observations',{}).items():
        overrides=payload.get('manual_overrides',{}).get('characters',{}).get(slot,{}) or {}
        manual=set(observation.get('manual_fields',[]))
        for field,value in overrides.items():
            if field=='face_morphs':
                manual.update('face_morphs.'+key for key in value)
            else:
                manual.add(field)
        observed=set(observation.get('observed_fields',[]))
        observation['manual_fields']=sorted(manual)
        observation['defaulted_fields']=sorted(APPEARANCE_FIELDS-observed-manual)
    return payload


def provenance_metadata(profile):
    assignments=profile.get('assignments',{})
    return {
        'profile_id':profile['id'],
        'profile_revision':profile['revision'],
        'profile_sha256':profile['sha256'],
        'source':profile['source'],
        'analysis_version':profile.get('analysis_version','1.0'),
        'photo_sha256':sorted({a['photo_sha256'] for a in assignments.values()}),
        'manual_overrides_sha256':sha(profile.get('manual_overrides',{})),
        'observations_sha256':sha(profile.get('observations',{})),
        'assignments_sha256':sha(assignments),
        'consent_policy':profile['consent_policy'],
        'reviewed':profile['reviewed'],
        'external_transfer':False,
    }


def public_summary(profile):
    metadata=provenance_metadata(profile)
    return {
        **metadata,
        'provider':profile['source'],
        'is_mock':profile['source']=='technical-fixture',
        'source_description':'Appearance was measured in your browser and reviewed by you. The server validates bounded inputs; it does not independently verify image inference.' if profile['source']=='browser-mediapipe-v1' else 'Explicit technical fixture; no photo appearance extraction.',
        'observations':profile.get('observations',{}),
        'assignments':profile.get('assignments',{}),
        'manual_overrides':profile.get('manual_overrides',{}),
    }
