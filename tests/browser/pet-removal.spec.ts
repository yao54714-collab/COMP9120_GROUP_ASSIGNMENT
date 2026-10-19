import {test,expect,Page} from '../../frontend/node_modules/@playwright/test';

async function login(page:Page,role:string){
  await page.goto('/');
  await page.getByLabel('Email',{exact:true}).fill(role+'@pawcare.local');
  await page.getByLabel('Password',{exact:true}).fill('PawCare2026!');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await expect(page.getByRole('button',{name:'Sign out'})).toBeVisible();
}
async function myPets(page:Page){await page.getByRole('navigation').getByRole('button',{name:'My pets',exact:true}).click();}
async function addPet(page:Page,name:string,species:string){
  await page.getByRole('button',{name:'Add a pet',exact:true}).click();
  await page.getByLabel('Pet name',{exact:true}).fill(name);
  await page.getByRole('combobox',{name:'Species',exact:true}).selectOption(species);
  const response=page.waitForResponse(r=>r.url().endsWith('/api/catalog/pets')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Save',exact:true}).click();
  const pet=await (await response).json();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  return pet;
}
const headers={'X-PawCare-Client':'web'};
const tomorrow=()=>{const date=new Intl.DateTimeFormat('en-CA',{timeZone:'Australia/Sydney'}).format(new Date());const d=new Date(date+'T12:00:00Z');d.setUTCDate(d.getUTCDate()+1);return d.toISOString().slice(0,10)+'T15:00:00';};

test('customer can cancel or confirm deletion of new dog and cat profiles',async({page})=>{
  await login(page,'customer');await myPets(page);
  for(const species of ['dog','cat']){
    const name='Remove '+species+' browser';
    await addPet(page,name,species);
    await page.getByRole('button',{name:'Delete '+name,exact:true}).click();
    await expect(page.getByRole('dialog')).toContainText('This cannot be undone.');
    await page.getByRole('dialog').getByRole('button',{name:'Cancel',exact:true}).click();
    await expect(page.getByRole('heading',{name,exact:true})).toBeVisible();
    await page.getByRole('button',{name:'Delete '+name,exact:true}).click();
    if(species==='cat'){
      await page.setViewportSize({width:375,height:900});
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
      await page.screenshot({path:'../test-results/pet-delete-confirm-mobile.png',fullPage:true});
    }
    await page.getByRole('dialog').getByRole('button',{name:'Delete pet',exact:true}).click();
    await expect(page.getByRole('heading',{name,exact:true})).toHaveCount(0);
    await page.reload();await myPets(page);
    await expect(page.getByRole('heading',{name,exact:true})).toHaveCount(0);
    await page.getByRole('button',{name:'Book a visit',exact:true}).click();
    await expect(page.getByLabel('Pet 1').locator('option').filter({hasText:name})).toHaveCount(0);
    await myPets(page);
  }
  await page.screenshot({path:'../test-results/pet-actions-mobile.png',fullPage:true});
});

for(const role of ['frontdesk','manager']){
  test(role+' can delete a walk-in customer pet from the staff list',async({page})=>{
    await login(page,role);
    await page.getByRole('navigation').getByRole('button',{name:'Customers & pets',exact:true}).click();
    const row=page.getByRole('row').filter({hasText:'Chen Xiao'});
    await row.getByRole('button',{name:'Add a pet',exact:true}).click();
    const name='Staff removal '+role;
    await page.getByLabel('Pet name',{exact:true}).fill(name);
    await page.getByRole('button',{name:'Save',exact:true}).click();
    await row.getByRole('button',{name:'Delete '+name,exact:true}).click();
    if(role==='manager')await page.screenshot({path:'../test-results/pet-delete-staff.png',fullPage:true});
    await page.getByRole('dialog').getByRole('button',{name:'Delete pet',exact:true}).click();
    await expect(row.getByRole('button',{name,exact:true})).toHaveCount(0);
    await expect(row).toContainText('Cookie');
    await page.reload();
    await page.getByRole('navigation').getByRole('button',{name:'Customers & pets',exact:true}).click();
    await expect(page.getByRole('button',{name,exact:true})).toHaveCount(0);
    // A completed profile is hidden by default, while its real care records remain accessible.
    const history=await (await page.request.get('/api/care-history/6')).json();
    expect(history.length).toBeGreaterThan(0);
    expect((await page.request.post('/api/catalog/pets/6/deactivate',{headers})).ok()).toBeTruthy();
    await page.reload();
    await page.getByRole('navigation').getByRole('button',{name:'Customers & pets',exact:true}).click();
    await expect(page.getByRole('button',{name:'Max (inactive)',exact:true})).toHaveCount(0);
    await page.getByRole('button',{name:/^View inactive pets/}).click();
    const inactiveRow=page.getByRole('row').filter({hasText:'Li An'});
    await expect(inactiveRow.getByRole('button',{name:'Max (inactive)',exact:true})).toBeVisible();
    await inactiveRow.getByRole('button',{name:'Records',exact:true}).click();
    await expect(page.getByRole('dialog').locator('.history-entry')).toHaveCount(history.length);
    await expect(page.getByRole('dialog')).toContainText(history[0].result_notes);
    await page.getByRole('dialog').getByRole('button',{name:'Close',exact:true}).click();
    if(role==='manager')await page.screenshot({path:'../test-results/inactive-pets-staff.png',fullPage:true});
    await inactiveRow.getByRole('button',{name:'Max (inactive)',exact:true}).click();
    await page.getByLabel('Active profile',{exact:true}).check();
    await page.getByRole('button',{name:'Save',exact:true}).click();
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(page.getByRole('button',{name:'Max (inactive)',exact:true})).toHaveCount(0);
    await page.getByRole('button',{name:/^Active pets/}).click();
    await expect(page.getByRole('button',{name:'Max',exact:true})).toBeVisible();
    expect(await (await page.request.get('/api/care-history/6')).json()).toEqual(history);
  });
}

test('stale delete cannot remove a booked pet; deactivation is blocked until cancellation and can be reversed',async({page})=>{
  await login(page,'customer');await myPets(page);
  const name='History removal browser',pet=await addPet(page,name,'cat');
  const bookingResponse=await page.request.post('/api/appointments',{headers,data:{requested_start_at:tomorrow(),items:[{pet_id:pet.pet_id,service_id:3}]}});
  expect(bookingResponse.ok()).toBeTruthy();
  const booking=await bookingResponse.json();
  // The page still thinks this pet has no history. The backend must reject deletion.
  await page.getByRole('button',{name:'Delete '+name,exact:true}).click();
  await page.getByRole('dialog').getByRole('button',{name:'Delete pet',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('has booking history and cannot be deleted');
  await page.getByRole('dialog').getByRole('button',{name:'Cancel',exact:true}).click();
  await page.reload();await myPets(page);
  await page.getByRole('button',{name:'Deactivate '+name,exact:true}).click();
  await expect(page.getByRole('dialog')).toContainText('Finish or cancel them');
  await expect(page.getByRole('dialog').getByRole('button',{name:'Deactivate pet',exact:true})).toBeDisabled();
  await page.getByRole('dialog').getByRole('button',{name:'Cancel',exact:true}).click();
  const detail=await (await page.request.get('/api/appointments/'+booking.appointment_id)).json();
  expect((await page.request.post('/api/items/'+detail.items[0].appointment_item_id+'/cancel',{headers})).ok()).toBeTruthy();
  await page.reload();await myPets(page);
  await page.getByRole('button',{name:'Deactivate '+name,exact:true}).click();
  await page.getByRole('dialog').getByRole('button',{name:'Deactivate pet',exact:true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByRole('heading',{name:name+' Inactive',exact:true})).toHaveCount(0);
  await page.reload();await myPets(page);
  await expect(page.getByRole('heading',{name:name+' Inactive',exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:/^Active pets/})).toHaveAttribute('aria-pressed','true');
  await page.getByRole('button',{name:/^View inactive pets/}).click();
  const card=page.locator('.pc-visit').filter({has:page.getByRole('heading',{name:name+' Inactive',exact:true})});
  await expect(card).toBeVisible();
  await expect(card.getByRole('button',{name:'Care history'})).toBeVisible();
  await card.getByRole('button',{name:'Care history'}).click();
  await expect(page.getByRole('dialog')).toContainText('No completed care records yet');
  await page.getByRole('dialog').getByRole('button',{name:'Close',exact:true}).click();
  await page.setViewportSize({width:375,height:900});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  await page.screenshot({path:'../test-results/inactive-pets-customer-mobile.png',fullPage:true});
  await page.setViewportSize({width:1440,height:1050});
  await page.getByRole('button',{name:'My bookings',exact:true}).click();
  await expect(page.getByRole('row').filter({hasText:booking.booking_code})).toContainText(name);
  await page.getByRole('button',{name:'Book a visit',exact:true}).click();
  await expect(page.getByLabel('Pet 1').locator('option').filter({hasText:name})).toHaveCount(0);
  await myPets(page);
  await page.getByRole('button',{name:/^View inactive pets/}).click();
  await card.getByRole('button',{name:'Edit profile',exact:true}).click();
  await page.getByLabel('Active profile',{exact:true}).check();
  await page.getByRole('button',{name:'Save',exact:true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(card).toHaveCount(0);
  await page.getByRole('button',{name:/^Active pets/}).click();
  await expect(page.getByRole('heading',{name,exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Book a visit',exact:true}).click();
  await expect(page.getByLabel('Pet 1').locator('option').filter({hasText:name})).toHaveCount(1);
});
