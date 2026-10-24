"""Tombstone polymorphic references before ORM deletion or FK cascades reuse IDs."""
from sqlalchemy import event, select, update, or_
from . import models as m
from .projectarchive import ENTITIES


def tombstone(connection,kind,ids):
    connection.execute(update(m.WorldResource).where(m.WorldResource.entity_kind==kind,m.WorldResource.entity_id.in_(ids)).values(entity_id=-m.WorldResource.id))


def install():
    for kind,model in ENTITIES.items():
        def before_delete(mapper,connection,target,kind=kind):
            tombstone(connection,kind,[target.id])
            if kind=='character':
                tombstone(connection,'relation',select(m.Relation.id).where(or_(m.Relation.source_id==target.id,m.Relation.target_id==target.id)))
        event.listen(model,'before_delete',before_delete)

    @event.listens_for(m.World,'before_delete')
    def world_delete(mapper,connection,target):
        tombstone(connection,'entry',select(m.WorldEntry.id).where(m.WorldEntry.world_id==target.id))


def valid(row,target):
    # Conservative fallback for references created before tombstoning existed.
    return target is not None and target.created_at.replace(tzinfo=None)<=row.created_at.replace(tzinfo=None)
