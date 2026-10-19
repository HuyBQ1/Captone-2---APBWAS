from sqlalchemy import select, update
from fastapi import HTTPException
from .models import Approval, ApprovalDecision, Inventory, Workflow, WorkflowStep, ToolExecution, SystemSetting, User, now
from .permissions import require
from .audit import audit
from .auth import utc
from .usage import configuration
from .workflows import emit

def decide(db,user,approval_id,body):
    require(db,user,'approvals.decide')
    if user.role not in configuration(db)['approver_roles']:
        raise HTTPException(403,'Vai trò không thuộc quy tắc phê duyệt hiện tại.')
    item=db.scalar(select(Approval).where(Approval.id==approval_id).with_for_update())
    if not item:
        raise HTTPException(404,'Không tìm thấy phê duyệt.')
    if item.status!='pending' or item.revision!=body.revision:
        raise HTTPException(409,'Phê duyệt đã thay đổi hoặc đã được xử lý. Hãy tải lại.')
    wf=db.scalar(select(Workflow).where(Workflow.id==item.workflow_id).with_for_update())
    if utc(item.expires_at)<=now():
        item.status='expired'
        wf.status='failed'
        wf.error='Phê duyệt hết hạn.'
        audit(db,user,'approval.expired',item.id,correlation=wf.id)
        emit(db,wf,'failed',{'message':wf.error})
        db.commit()
        raise HTTPException(409,'Phê duyệt đã hết hạn.')
    if wf.status!='waiting_approval' or wf.cancel_requested:
        raise HTTPException(409,'Workflow không còn chờ phê duyệt.')
    inv=db.get(Inventory,item.arguments['product_id'])
    previous_arguments=dict(item.arguments)
    if body.decision=='revision':
        if body.quantity is None:
            raise HTTPException(422,'Cần số lượng mới.')
        item.arguments={**item.arguments,'quantity':body.quantity,'before':inv.quantity,'version':inv.version}
        item.revision+=1
        item.approved_revision=None
    elif body.decision=='rejected':
        if not body.reason.strip():
            raise HTTPException(422,'Cần lý do từ chối.')
        item.status='rejected'
        wf.status='failed'
        wf.error='Phê duyệt bị từ chối: '+body.reason
        emit(db,wf,'failed',{'message':wf.error})
    else:
        requester=db.get(User,item.user_id)
        require(db,requester,'inventory.propose')
        toggles=db.get(SystemSetting,'tools')
        if toggles and not toggles.value.get(item.tool,True):
            raise HTTPException(409,'Công cụ áp dụng tồn kho đã bị tắt.')
        # Atomic optimistic lock: inventory and approval commit together, exactly once.
        changed=db.execute(update(Inventory).where(Inventory.product_id==inv.product_id,Inventory.version==item.arguments['version'])
                           .values(quantity=item.arguments['quantity'],version=Inventory.version+1))
        if changed.rowcount!=1:
            raise HTTPException(409,'Tồn kho đã thay đổi. Sửa tham số để tạo revision mới trước khi duyệt.')
        item.status='approved'
        item.approved_revision=item.revision
        wf.status='completed'
        wf.result={**wf.result,'summary':'Đã cập nhật tồn kho đúng một lần sau phê duyệt hợp lệ.','applied_revision':item.revision}
        db.add(ToolExecution(workflow_id=wf.id,position=len(wf.plan),tool='apply_approved_inventory_adjustment',arguments=item.arguments,output=wf.result,duration_ms=0))
        audit(db,user,'tool.completed',wf.id,{'tool':'apply_approved_inventory_adjustment','revision':item.revision,'arguments':item.arguments})
        emit(db,wf,'completed',wf.result)
    db.add(ApprovalDecision(approval_id=item.id,user_id=user.id,revision=body.revision,decision=body.decision,reason=body.reason,
                            arguments={'before':previous_arguments,'after':item.arguments}))
    audit(db,user,'approval.'+body.decision,item.id,{'revision':body.revision,'reason':body.reason,'arguments':item.arguments},wf.id)
    db.commit()
    return item
