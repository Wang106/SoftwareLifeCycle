import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

def uid(): return uuid.uuid4()
def now(): return datetime.utcnow()

class SoftwareChangeRequest(Base):
    __tablename__="software_change_requests"
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uid)
    request_no: Mapped[str]=mapped_column(String(50),unique=True,nullable=False)
    title: Mapped[str]=mapped_column(String(240),nullable=False)
    source: Mapped[str]=mapped_column(String(30),nullable=False)
    scope: Mapped[str]=mapped_column(String(20),nullable=False)
    change_type: Mapped[str]=mapped_column(String(40),nullable=False)
    software_id: Mapped[uuid.UUID]=mapped_column(ForeignKey("software_products.id"),nullable=False)
    customer_id: Mapped[uuid.UUID|None]=mapped_column(ForeignKey("customers.id"))
    project_id: Mapped[uuid.UUID|None]=mapped_column(ForeignKey("projects.id"))
    status: Mapped[str]=mapped_column(String(40),default="DRAFT")
    background: Mapped[str|None]=mapped_column(Text)
    requirement: Mapped[str|None]=mapped_column(Text)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class AcceptanceCriterion(Base):
    __tablename__="acceptance_criteria"
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uid)
    change_request_id: Mapped[uuid.UUID]=mapped_column(ForeignKey("software_change_requests.id"),nullable=False,index=True)
    criterion_no: Mapped[str]=mapped_column(String(50),nullable=False)
    description: Mapped[str]=mapped_column(Text,nullable=False)

class ChangePoint(Base):
    __tablename__="change_points"
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uid)
    change_request_id: Mapped[uuid.UUID]=mapped_column(ForeignKey("software_change_requests.id"),nullable=False,index=True)
    change_no: Mapped[str]=mapped_column(String(50),nullable=False)
    title: Mapped[str]=mapped_column(String(240),nullable=False)
    description: Mapped[str|None]=mapped_column(Text)
    status: Mapped[str]=mapped_column(String(30),default="OPEN")

class Issue(Base):
    __tablename__="issues"
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uid)
    issue_no: Mapped[str]=mapped_column(String(50),unique=True,nullable=False)
    title: Mapped[str]=mapped_column(String(240),nullable=False)
    scope: Mapped[str]=mapped_column(String(30),nullable=False)
    severity: Mapped[str]=mapped_column(String(20),nullable=False)
    status: Mapped[str]=mapped_column(String(40),default="OPEN")
    description: Mapped[str|None]=mapped_column(Text)

class IssueChangeRequestRelation(Base):
    __tablename__="issue_change_request_relations"
    __table_args__=(UniqueConstraint("issue_id","change_request_id","relation_type"),)
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uid)
    issue_id: Mapped[uuid.UUID]=mapped_column(ForeignKey("issues.id"),nullable=False)
    change_request_id: Mapped[uuid.UUID]=mapped_column(ForeignKey("software_change_requests.id"),nullable=False)
    relation_type: Mapped[str]=mapped_column(String(40),nullable=False)
