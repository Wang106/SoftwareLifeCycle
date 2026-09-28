import hashlib
from app.core.db import SessionLocal
from app.models.core import *

def h(name): return hashlib.sha256(name.encode()).hexdigest()
def run():
    db=SessionLocal()
    if db.query(Supplier).count(): return
    supplier=Supplier(code='SUP-001',name='Supplier A',country='DE',status='ACTIVE'); customer=Customer(code='CUS-001',name='Customer A',status='ACTIVE'); db.add_all([supplier,customer]); db.flush()
    project=Project(customer_id=customer.id,project_code='PRJ-X',name='Project X',vehicle_platform='EV Platform X',status='ACTIVE'); software=SoftwareProduct(supplier_id=supplier.id,code='SW-BMS-001',name='BMS Standard',software_type='BMS',status='ACTIVE'); db.add_all([project,software]); db.flush()
    ssr=Release(software_id=software.id,release_type='STANDARD',version='5.1.12',status='RELEASED'); asr=Release(software_id=software.id,release_type='APPLICATION',version='2.3.4',status='READY'); db.add_all([ssr,asr]); db.flush(); db.add(StandardReleaseDetail(release_id=ssr.id,git_branch='main',git_commit='demo512')); db.add(ApplicationReleaseDetail(release_id=asr.id,customer_id=customer.id,project_id=project.id,standard_base_release_id=ssr.id))
    main=ComponentDefinition(code='MAIN_APPLICATION',name='Main Application'); cal=ComponentDefinition(code='CALIBRATION',name='Calibration'); db.add_all([main,cal]); db.flush()
    c1=ReleaseComponent(release_id=asr.id,component_definition_id=main.id,version='2.3.4',delta_type='MODIFIED'); c2=ReleaseComponent(release_id=asr.id,component_definition_id=cal.id,version='CAL-32',delta_type='MODIFIED'); db.add_all([c1,c2]); db.flush()
    db.add_all([Artifact(release_component_id=c1.id,artifact_type='HEX',filename='CustomerA_BMS.hex',storage_reference='managed://CustomerA_BMS.hex',sha256=h('hex'),controlled=True,classification='CONFIDENTIAL',distribution_level='EXTERNAL',ai_access_policy='DENY'),Artifact(release_component_id=c1.id,artifact_type='ELF',filename='BMS.elf',storage_reference='managed://BMS.elf',sha256=h('elf'),controlled=True,classification='STRICTLY_CONFIDENTIAL',distribution_level='INTERNAL_ONLY',ai_access_policy='LOCAL_ONLY'),Artifact(release_component_id=c2.id,artifact_type='A2L',filename='CustomerA_BMS.a2l',storage_reference='managed://CustomerA_BMS.a2l',sha256=h('a2l'),controlled=True,classification='CONFIDENTIAL',distribution_level='CONTROLLED_EXTERNAL',ai_access_policy='LOCAL_ONLY')]); db.commit()
if __name__=='__main__': run()
