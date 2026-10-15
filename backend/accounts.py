"""Manager-only account administration. Preserve all business history."""
from fastapi import APIRouter, Depends, HTTPException
from .auth import get_user
from .common import require, check, found
from .db import transaction, one, all_rows, schedule_lock
from .models import AccountStatusInput, PasswordResetInput
from .security import password_hash

router = APIRouter(prefix='/api/accounts')

ACCOUNT_QUERY = '''SELECT u.account_id,u.email,u.is_active,u.created_at,
 COALESCE(e.display_name,c.display_name) AS display_name,
 CASE WHEN e.employee_id IS NOT NULL THEN e.staff_role ELSE 'customer' END AS role,
 e.employee_id,c.customer_id,COALESCE(e.is_active,c.is_active,false) AS profile_active
 FROM user_account u LEFT JOIN employee e USING(account_id)
 LEFT JOIN customer_account ca USING(account_id) LEFT JOIN customer c USING(customer_id)'''


def manager_lock(c, user):
    schedule_lock(c)
    # Recheck after the lock in case another manager changed this account.
    if not one(c, '''SELECT 1 FROM user_account u JOIN employee e USING(account_id)
        WHERE u.account_id=%s AND u.is_active AND e.is_active AND e.staff_role='manager' ''', (user['account_id'],)):
        raise HTTPException(403, 'An active manager account is required.')


@router.get('')
def accounts(user=Depends(get_user)):
    require(user, 'manager')
    with transaction() as c:
        return all_rows(c, ACCOUNT_QUERY + ' ORDER BY u.account_id DESC')


@router.put('/{account_id}/status')
def set_status(account_id: int, data: AccountStatusInput, user=Depends(get_user)):
    require(user, 'manager')
    check(account_id != user['account_id'], 'You cannot change the status of your own account.')
    with transaction() as c:
        manager_lock(c, user)
        target = found(one(c, ACCOUNT_QUERY + ' WHERE u.account_id=%s', (account_id,)))
        if target['employee_id']:
            if not data.is_active:
                check(not one(c, "SELECT 1 FROM appointment_item WHERE employee_id=%s AND state IN ('scheduled','in_progress')", (target['employee_id'],)),
                      'This employee has unfinished care tasks. Finish or reassign them before deactivating access.')
                if target['role'] == 'manager':
                    count = one(c, "SELECT count(*) AS n FROM employee e JOIN user_account u USING(account_id) WHERE e.staff_role='manager' AND e.is_active AND u.is_active")['n']
                    check(not target['is_active'] or not target['profile_active'] or count > 1, 'At least one active manager must remain.')
            # Staff access and scheduling eligibility must change together.
            c.execute('UPDATE employee SET is_active=%s WHERE employee_id=%s', (data.is_active, target['employee_id']))
        elif data.is_active:
            check(target['customer_id'] is not None and target['profile_active'], 'Reactivate the customer profile in Customers & pets first.')
        c.execute('UPDATE user_account SET is_active=%s WHERE account_id=%s', (data.is_active, account_id))
        c.execute('DELETE FROM auth_session WHERE account_id=%s', (account_id,))
    return {'ok': True}


@router.put('/{account_id}/password')
def reset_password(account_id: int, data: PasswordResetInput, user=Depends(get_user)):
    require(user, 'manager')
    check(account_id != user['account_id'], 'Use another manager account to reset your password.')
    with transaction() as c:
        manager_lock(c, user)
        found(one(c, 'SELECT account_id FROM user_account WHERE account_id=%s FOR UPDATE', (account_id,)))
        c.execute('UPDATE user_account SET password_hash=%s WHERE account_id=%s', (password_hash(data.password), account_id))
        c.execute('DELETE FROM auth_session WHERE account_id=%s', (account_id,))
    return {'ok': True}
