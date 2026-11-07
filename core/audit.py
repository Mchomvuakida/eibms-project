import threading
from django.apps import apps
from django.db import transaction
from django.db.models.signals import pre_save, post_save, post_delete
from django.utils import timezone

_local = threading.local()

TRACKED = ['Sale', 'Expense', 'Product', 'Customer', 'BankDeposit',
           'Payment', 'Production', 'Truck', 'User',
           'Supplier', 'SupplierBill', 'SupplierPayment', 'SpendingRequest', 'Target', 'OpeningCash']
LOG_CREATES = {'Expense', 'Product', 'Customer', 'BankDeposit',
               'Payment', 'Production', 'Truck', 'User',
               'Supplier', 'SupplierBill', 'SupplierPayment', 'SpendingRequest', 'Target', 'OpeningCash'}
IGNORE_FIELDS = {'last_login', 'password', 'created_at'}


def current_user():
    user = getattr(_local, 'user', None)
    return user if user is not None and getattr(user, 'is_authenticated', False) else None


class AuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _local.user = getattr(request, 'user', None)
        try:
            return self.get_response(request)
        finally:
            _local.user = None


def _write(action, instance, changes=None):
    try:
        from .models import AuditLog
        try:
            branch = getattr(instance, 'branch', None)
        except Exception:
            branch = None
        with transaction.atomic():
            AuditLog.objects.create(
                user=current_user(),
                action=action,
                model_name=instance.__class__.__name__,
                object_id=str(instance.pk),
                object_repr=str(instance)[:255],
                changes=changes or {},
                branch=branch if getattr(branch, 'pk', None) else None,
            )
    except Exception:
        pass  # auditing must never break real work


def _before_save(sender, instance, **kwargs):
    instance._audit_old = None
    if instance.pk:
        instance._audit_old = sender._base_manager.filter(pk=instance.pk).first()


def _after_save(sender, instance, created, **kwargs):
    name = sender.__name__
    if created:
        if name in LOG_CREATES:
            _write('created', instance)
        return
    old = getattr(instance, '_audit_old', None)
    if old is None:
        return
    if name == 'Sale':
        created_at = getattr(instance, 'created_at', None)
        if created_at and (timezone.now() - created_at).total_seconds() < 60:
            return  # saves that happen while the sale is still being entered
    changes = {}
    for field in sender._meta.concrete_fields:
        if field.name in IGNORE_FIELDS:
            continue
        before, after = getattr(old, field.attname), getattr(instance, field.attname)
        if before != after:
            changes[field.name] = [str(before), str(after)]
    if changes:
        _write('updated', instance, changes)


def _after_delete(sender, instance, **kwargs):
    _write('deleted', instance)


def connect():
    for name in TRACKED:
        model = apps.get_model('core', name)
        pre_save.connect(_before_save, sender=model, dispatch_uid=f'audit_pre_{name}')
        post_save.connect(_after_save, sender=model, dispatch_uid=f'audit_post_{name}')
        post_delete.connect(_after_delete, sender=model, dispatch_uid=f'audit_del_{name}')