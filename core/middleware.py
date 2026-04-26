# core/middleware.py
from threading import local

_thread_locals = local()


def set_current_branch(branch_id):
    """Store current branch in thread-local storage"""
    _thread_locals.branch_id = branch_id


def get_current_branch():
    """Get current branch from thread-local"""
    return getattr(_thread_locals, 'branch_id', None)


class BranchIsolationMiddleware:
    """
    Filters querysets to only include objects from the user's branch
    unless user is admin/owner (full access).
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip for unauthenticated or admin/owner
        if not request.user.is_authenticated:
            response = self.get_response(request)
            return response

        if request.user.role in ['admin', 'owner']:
            # Full access - no filtering
            response = self.get_response(request)
            return response

        # For branch-specific users: set thread-local branch
        if request.user.branch_id:
            set_current_branch(request.user.branch_id)
        else:
            # If no branch assigned → treat as no access (or log warning)
            set_current_branch(None)

        response = self.get_response(request)

        # Clean up thread-local after request
        if hasattr(_thread_locals, 'branch_id'):
            del _thread_locals.branch_id

        return response