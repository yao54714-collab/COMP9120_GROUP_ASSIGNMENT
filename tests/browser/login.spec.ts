import {test,expect} from '../../frontend/node_modules/@playwright/test';

test('English sign-in opens without an auth warning and still reports wrong credentials',async({page})=>{
  const response=await page.goto('/');
  expect(response?.headers()['cache-control']).toBe('no-store');
  await expect(page.getByRole('heading',{name:'Welcome back'})).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
  await expect(page.locator('body')).not.toContainText(/[\u3400-\u9fff]/);
  await page.screenshot({path:'../test-results/english-login.png',fullPage:true});
  await page.reload();
  await expect(page.getByRole('heading',{name:'Welcome back'})).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
  await page.getByLabel('Email',{exact:true}).fill('customer@pawcare.local');
  await page.getByLabel('Password',{exact:true}).fill('IncorrectPassword');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await expect(page.getByRole('alert')).toHaveText('Incorrect email or password.');
  await page.getByLabel('Password',{exact:true}).fill('PawCare2026!');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await page.getByRole('button',{name:'Sign out',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Welcome back'})).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('An invalid or expired session returns to sign-in without a red banner',async({page,context,baseURL})=>{
  await context.addCookies([{name:'pawcare_session',value:'expired-test-session',url:baseURL!}]);
  const auth=page.waitForResponse(r=>r.url().endsWith('/api/auth/me'));
  await page.goto('/');
  expect((await auth).status()).toBe(401);
  await expect(page.getByRole('heading',{name:'Welcome back'})).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('A genuine startup error is cleared after successful sign-in and sign-out',async({page})=>{
  await page.route('**/api/auth/me',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Database unavailable. Check the local database service.'})}));
  await page.goto('/');
  await expect(page.getByRole('alert')).toHaveText('Database unavailable. Check the local database service.');
  await page.getByLabel('Email',{exact:true}).fill('customer@pawcare.local');
  await page.getByLabel('Password',{exact:true}).fill('PawCare2026!');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await page.getByRole('button',{name:'Sign out',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Welcome back'})).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
});
