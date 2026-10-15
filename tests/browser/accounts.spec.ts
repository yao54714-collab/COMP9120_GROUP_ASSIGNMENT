import {test,expect,Page} from '../../frontend/node_modules/@playwright/test';

async function signIn(page:Page,email:string,password:string){
  await page.goto('/');
  await page.getByLabel('Email',{exact:true}).fill(email);
  await page.getByLabel('Password',{exact:true}).fill(password);
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
}

test('manager manages a registered customer account without losing the profile',async({page,browser,baseURL})=>{
  const email=`account-ui-${Date.now()}@example.com`;
  await page.goto('/');
  await page.getByRole('button',{name:'New here? Create a customer account'}).click();
  await page.getByLabel('Email',{exact:true}).fill(email);
  await page.getByLabel('Password',{exact:true}).fill('Original2026!');
  await page.getByLabel('Name',{exact:true}).fill('Jamie Account');
  await page.getByLabel('Phone number',{exact:true}).fill('0400123456');
  await page.getByRole('button',{name:'Create account',exact:true}).click();
  await expect(page.getByRole('button',{name:'Sign out'})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Tell us about your pet'})).toBeVisible();
  const staff=await browser.newPage({baseURL});
  try{
    await signIn(staff,'manager@pawcare.local','PawCare2026!');
    await staff.getByRole('navigation').getByRole('button',{name:'User accounts',exact:true}).click();
    await staff.getByLabel('Search accounts').fill(email);
    const row=staff.getByRole('row').filter({hasText:email});
    await expect(row).toContainText('Jamie Account');
    await expect(row).toContainText('Customer');
    staff.on('dialog',dialog=>dialog.accept());
    await row.getByRole('button',{name:'Deactivate',exact:true}).click();
    await expect(row.getByRole('button',{name:'Activate',exact:true})).toBeVisible();
    await page.reload();await expect(page.getByRole('heading',{name:'Welcome back'})).toBeVisible();
    await signIn(page,email,'Original2026!');
    await expect(page.getByRole('alert')).toContainText('Incorrect email or password.');
    await staff.getByLabel('Login status').selectOption('inactive');
    await expect(row).toBeVisible();
    await staff.getByLabel('Login status').selectOption('all');
    await row.getByRole('button',{name:'Activate',exact:true}).click();
    await expect(row.getByRole('button',{name:'Deactivate',exact:true})).toBeVisible();
    await signIn(page,email,'Original2026!');
    await expect(page.getByRole('button',{name:'Sign out'})).toBeVisible();
    await row.getByRole('button',{name:'Reset password'}).click();
    await staff.getByLabel('New password',{exact:true}).fill('Changed2026!');
    await staff.getByLabel('Confirm new password',{exact:true}).fill('Mismatch2026!');
    await staff.getByRole('button',{name:'Save new password'}).click();
    await expect(staff.getByRole('alert')).toHaveText('Passwords do not match.');
    await staff.getByLabel('Confirm new password',{exact:true}).fill('Changed2026!');
    await staff.getByRole('button',{name:'Save new password'}).click();
    await expect(staff.getByRole('dialog')).toHaveCount(0);
    await page.reload();await expect(page.getByRole('heading',{name:'Welcome back'})).toBeVisible();
    await signIn(page,email,'Original2026!');
    await expect(page.getByRole('alert')).toContainText('Incorrect email or password.');
    await signIn(page,email,'Changed2026!');
    await expect(page.getByRole('button',{name:'Sign out'})).toBeVisible();
    await page.getByRole('navigation').getByRole('button',{name:'My profile'}).click();
    await expect(page.getByRole('heading',{name:'Jamie Account'})).toBeVisible();
    await staff.screenshot({path:'../test-results/english-user-accounts.png',fullPage:true});
  }finally{await staff.close()}
});
