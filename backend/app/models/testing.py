import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

def uid(): return uuid.uuid4()
def now(): return datetime.utcnow()

class DvpPlan(Base):
    __tablename__="dvp_plans"
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uid)
    change_request_id: Mapped[uuid.UUID]=mapped_column(ForeignKey("software_change_requests.id"),nullable=False,index=True)
    plan_no: Mapped[str]=mapped_column(String(50),unique=True,nullable=False)
    title: Mapped[str]=mapped_column(String(240),nullable=False)
    status: Mapped[str]=mapped_column(String(30),default="DRAFT")

class DvpItem(Base):
    __tablename__="dvp_items"
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uid)
    plan_id: Mapped[uuid.UUID]=mapped_column(ForeignKey("dvp_plans.id"),nullable=False,index=True)
    item_no: Mapped[str]=mapped_column(String(50),nullable=False)
    title: Mapped[str]=mapped_column(String(240),nullable=False)
    scope: Mapped[str]=mapped_column(String(30),nullable=False)
    status: Mapped[str]=mapped_column(String(30),default="NOT_STARTED")
    __table_args__=(UniqueConstraint("plan_id","item_no"),)

class ChangePointDvpItem(Base):
    __tablename__="change_point_dvp_items"
    change_point_id: Mapped[uuid.UUID]=mapped_column(ForeignKey("change_points.id"),primary_key=True)
    dvp_item_id: Mapped[uuid.UUID]=mapped_column(ForeignKey("dvp_items.id"),primary_key=True)
    relation_type: Mapped[str]=mapped_column(String(30),default="VERIFIES")

class IssueDvpItem(Base):
    __tablename__="issue_dvp_items"
    issue_id: Mapped[uuid.UUID]=mapped_column(ForeignKey("issues.id"),primary_key=True)
    dvp_item_id: Mapped[uuid.UUID]=mapped_column(ForeignKey("dvp_items.id"),primary_key=True)
    relation_type: Mapped[str]=mapped_column(String(30),default="VALIDATES_FIX")

class TestRelease(Base):
    __tablename__="test_releases"
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uid)
    test_release_no: Mapped[str]=mapped_column(String(50),unique=True,nullable=False)
    release_id: Mapped[uuid.UUID]=mapped_column(ForeignKey("releases.id"),nullable=False)
    snapshot_id: Mapped[uuid.UUID]=mapped_column(ForeignKey("release_snapshots.id"),nullable=False)
    purpose_scope: Mapped[str]=mapped_column(String(30),nullable=False)
    status: Mapped[str]=mapped_column(String(30),default="DRAFT")

class DvpExecution(Base):
    __tablename__="dvp_executions"
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uid)
    dvp_item_id: Mapped[uuid.UUID]=mapped_column(ForeignKey("dvp_items.id"),nullable=False,index=True)
    execution_no: Mapped[int]=mapped_column(nullable=False)
    release_id: Mapped[uuid.UUID]=mapped_column(ForeignKey("releases.id"),nullable=False)
    snapshot_id: Mapped[uuid.UUID]=mapped_column(ForeignKey("release_snapshots.id"),nullable=False)
    test_release_id: Mapped[uuid.UUID|None]=mapped_column(ForeignKey("test_releases.id"))
    result: Mapped[str]=mapped_column(String(30),nullable=False)
    actual_result: Mapped[str|None]=mapped_column(Text)
    executed_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    __table_args__=(UniqueConstraint("dvp_item_id","execution_no"),
        Index("ix_dvp_executions_release_snapshot_item", "release_id", "snapshot_id", "dvp_item_id", "execution_no"))
