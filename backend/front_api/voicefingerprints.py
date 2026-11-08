"""Synthesis-only identity, retaining immutable legacy render audit snapshots."""
import hashlib
import json
from . import models as m, versions as v


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def synthesis(snapshot, profile=None, model=None, provider=None):
    """Only effective synthesis inputs, never preferences or audit version IDs.

    The profile sample is an audition, not a cloning reference. Actual reference
    synthesis needs its own validated, rights-bound input in a future adapter.
    Model paths/endpoints stay in local version history; only config hashes enter
    the portable synthesis frame. No weights are opened or services contacted.
    """
    recipe=snapshot.get('recipe') or {}
    frame={'schema':2,'segment_uid':snapshot['segment_uid'],'text':snapshot['text'],
           'language':recipe.get('language') or (profile or {}).get('language',''),
           'speed':float(recipe.get('speed',1)),
           'parameters':{k:value for k,value in recipe.items() if k not in ('profile','language','speed')}}
    if profile:
        frame['profile']={'uid':profile['uid'],'voice_key':profile.get('voice_key','')}
    if model:
        frame['model']={'uid':model['uid'],'config':digest({k:model.get(k) for k in ('file_path','model_version')})}
    if provider:
        frame['provider']={'uid':provider['uid'],'config':digest({k:provider.get(k) for k in ('engine','endpoint','credential_id')})}
    return frame


def historical(session,kind,ref):
    if not isinstance(ref,dict) or not all(ref.get(k) for k in ('id','uid','version')):
        return None
    head=v.head(session.connection(),kind,ref['id'])
    version=session.get(m.EntityVersion,ref['version'])
    if not head or not head['present'] or not version or version.generation!=head['generation']:
        return None
    blob=session.get(m.VersionBlob,version.blob_sha)
    if not blob or digest(blob.payload)!=version.blob_sha or blob.payload.get('uid')!=ref['uid']:
        return None
    return blob.payload


def is_current(session,render,current):
    if current is None:
        return False
    if render.fingerprint==current:
        return True
    snapshot=render.snapshot
    if not isinstance(snapshot,dict) or 'synthesis' in snapshot:
        return False
    # Validate the original v1 fingerprint before deriving semantics from the
    # exact historical versions. Missing history is stale, never guessed current.
    keys=('segment_uid','text','speaker','recipe','profile','model','provider')
    old={k:snapshot[k] for k in keys if k in snapshot}
    if not all(k in old for k in keys[:4]) or digest(old)!=render.fingerprint:
        return False
    try:
        profile=historical(session,'voice_profile',old['profile']) if 'profile' in old else None
        model=historical(session,'voice_model',old['model']) if 'model' in old else None
        provider=historical(session,'voice_provider',old['provider']) if 'provider' in old else None
        if any(k in old and value is None for k,value in (('profile',profile),('model',model),('provider',provider))):
            return False
        ref=(old['recipe'].get('profile') or {})
        if bool(ref)!=bool(profile) or (profile and (profile['uid']!=ref.get('uid') or old['profile']['id']!=ref.get('id'))):
            return False
        if profile and (profile.get('model_id') or None)!=(old.get('model') or {}).get('id'):
            return False
        if model and (model.get('provider_id') or None)!=(old.get('provider') or {}).get('id'):
            return False
        return digest(synthesis(old,profile,model,provider))==current
    except (KeyError,TypeError,ValueError):
        return False
