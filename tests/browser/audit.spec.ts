import {test,expect,Page} from '../../frontend/node_modules/@playwright/test';

async function login(page:Page,role:string){await page.goto('/');await page.getByLabel('Email',{exact:true}).fill(role+'@pawcare.local');await page.getByLabel('Password',{exact:true}).fill('PawCare2026!');await page.getByRole('button',{name:'Sign in',exact:true}).click();await expect(page.getByRole('button',{name:'Sign out'})).toBeVisible();}
async function logout(page:Page){await page.getByRole('button',{name:'Sign out'}).click();await expect(page.getByRole('heading',{name:'Welcome back'})).toBeVisible();}
const future=()=>{const p=new Intl.DateTimeFormat('en-CA',{timeZone:'Australia/Sydney',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());const s=(k:string)=>p.find(p=>p.type===k)!.value;const d=new Date(`${s('year')}-${s('month')}-${s('day')}T12:00:00Z`);d.setUTCDate(d.getUTCDate()+3);return d.toISOString().slice(0,10)};

test('audit: cat bath and comb → confirmation → care → A$110 receipt',async({page})=>{
  await login(page,'customer');
  await page.getByRole('button',{name:'Book a visit',exact:true}).click();
  await page.getByLabel('Pet 1').selectOption({label:'Luna'});
  await expect(page.getByLabel('Care service').locator('option')).toHaveText(['Gentle cat bath · A$75.00 and up','Cat brushing · A$35.00 and up']);
  await expect(page.locator('.pc-summary-price')).toContainText('A$75.00');
  await page.getByRole('button',{name:'Add a service'}).click();
  await page.getByLabel('Pet 2').selectOption({label:'Luna'});
  await page.getByLabel('Care service').nth(1).selectOption('4');
  await expect(page.locator('.pc-summary-price')).toContainText('A$110.00');
  await page.getByLabel('Preferred date').fill(future());
  await page.getByLabel('Preferred time (Sydney)').fill('14:00');
  await page.setViewportSize({width:375,height:1000});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  await page.screenshot({path:'../test-results/audit-cat-booking-mobile.png',fullPage:true});
  await page.setViewportSize({width:1440,height:1050});
  const response=page.waitForResponse(r=>r.url().endsWith('/api/appointments')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Request booking'}).click();
  const booking=await (await response).json();const code=booking.booking_code;
  await expect(page.getByRole('row').filter({hasText:code})).toContainText('Cat brushing');
  await logout(page);await login(page,'frontdesk');
  await page.getByRole('button',{name:'Appointments',exact:true}).click();
  await page.getByRole('row').filter({hasText:code}).getByRole('button',{name:'Schedule',exact:true}).click();
  await page.getByRole('button',{name:'Schedule / reschedule'}).click();
  for(let n=0;n<2;n++){await page.getByRole('button',{name:'Find availability'}).nth(n).click();await expect(page.getByRole('button',{name:'Find availability'}).nth(n)).toBeEnabled();}
  await page.getByRole('button',{name:'Confirm schedule'}).click();
  await expect(page.locator('.money-summary').getByText('Amount due').locator('strong')).toHaveText('A$110.00');
  await page.getByRole('dialog').getByRole('button',{name:'Close',exact:true}).last().click();
  await logout(page);await login(page,'groomer');
  await page.getByLabel('Task date').fill(future());
  await page.locator('.pc-task').filter({hasText:'Luna · Gentle cat bath'}).getByRole('button',{name:'Review and start care'}).click();
  for(const service of ['Gentle cat bath','Cat brushing']){
    const item=page.getByRole('dialog').locator('.pc-task').filter({hasText:service});
    await item.getByRole('button',{name:'Start care',exact:true}).click();
    await item.getByRole('button',{name:'Complete care record'}).click();
    await page.getByLabel('Results and advice for the owner').fill(service+' full workflow test completed.');
    await page.getByRole('button',{name:'Complete care and record usage'}).click();
    await expect(item.getByText('Completed',{exact:true})).toBeVisible();
  }
  await page.getByRole('dialog').getByRole('button',{name:'Close',exact:true}).last().click();
  await logout(page);await login(page,'frontdesk');
  await page.getByRole('button',{name:'Payments',exact:true}).click();
  await page.getByRole('row').filter({hasText:code}).getByRole('button',{name:'View',exact:true}).click();
  await page.getByRole('button',{name:'Record payment',exact:true}).click();
  expect(Number(await page.getByLabel('Payment amount (AUD, partial payments accepted)').inputValue())).toBe(110);
  await page.getByRole('button',{name:'Confirm record',exact:true}).click();
  await expect(page.locator('.money-summary').getByText('Amount due').locator('strong')).toHaveText('A$0.00');
  await page.screenshot({path:'../test-results/audit-cat-paid.png',fullPage:true});
});

test('audit: homepage pet booking must retain the clicked cat',async({page})=>{
  await login(page,'customer');
  await page.locator('.pc-pet-row').filter({hasText:'Luna'}).getByRole('button',{name:'Book',exact:true}).click();
  await page.screenshot({path:'../test-results/audit-wrong-pet.png',fullPage:true});
  await expect(page.getByLabel('Pet 1')).toHaveValue('2',{timeout:1500});
});

test('audit: changing to finance must not preserve a hidden appointment status filter',async({page})=>{
  await login(page,'frontdesk');
  await page.getByRole('navigation').getByRole('button',{name:'Appointments',exact:true}).click();
  await page.getByRole('button',{name:'Confirmed',exact:true}).click();
  await page.getByRole('navigation').getByRole('button',{name:'Payments',exact:true}).click();
  await page.screenshot({path:'../test-results/audit-hidden-filter.png',fullPage:true});
  await expect(page.locator('.pc-filters').getByRole('button',{name:'All',exact:true})).toHaveAttribute('aria-pressed','true',{timeout:1500});
});

test('audit: all role pages at mobile width, keyboard dialog and literal HTML text',async({page})=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  const menus:Record<string,string[]>={customer:['Home','Book a visit','My pets','My bookings','My profile'],frontdesk:['Today','Appointments','Customers & pets','Payments'],groomer:['Today tasks','Care history','My shifts'],manager:['Overview','Appointments','Customers & pets','Services','Employees & shifts','User accounts','Workstations','Inventory','Payments & refunds']};
  await page.setViewportSize({width:375,height:1000});
  for(const [role,labels] of Object.entries(menus)){
    await login(page,role);
    for(const label of labels){
      await page.getByRole('navigation').getByRole('button',{name:label,exact:true}).click();
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`${role}: ${label}`).toBe(true);
      await expect(page.locator('.form-error')).toHaveCount(0);
      await expect(page.locator('body')).not.toContainText(/[\u3400-\u9fff]/);
    }
    if(role==='customer'){
      await page.getByRole('button',{name:'My pets',exact:true}).click();
      await page.getByRole('button',{name:'Add a pet',exact:true}).click();
      await page.keyboard.press('Escape');await expect(page.getByRole('dialog')).toHaveCount(0);
      await page.getByRole('button',{name:'Add a pet',exact:true}).click();
      await page.getByLabel('Pet name').fill('<img src=x onerror=alert(1)>');
      await page.getByRole('button',{name:'Save',exact:true}).click();
      await expect(page.getByRole('heading',{name:'<img src=x onerror=alert(1)>',exact:true})).toBeVisible();
      await expect(page.locator('img[src="x"]')).toHaveCount(0);
    }
    await logout(page);
  }
  expect(errors).toEqual([]);
});

test('audit: displayed consumables must match submitted IDs after a recipe ingredient is disabled',async({page})=>{
  await login(page,'manager');
  await page.getByRole('navigation').getByRole('button',{name:'Inventory',exact:true}).click();
  await page.getByRole('button',{name:'Consumable catalogue',exact:true}).click();
  await page.getByRole('row').filter({hasText:'Gentle shampoo'}).getByRole('button',{name:'Edit',exact:true}).click();
  await page.getByLabel('Active profile').uncheck();
  await page.getByRole('button',{name:'Save',exact:true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await logout(page);await login(page,'mia');
  await page.locator('.pc-task').filter({hasText:'Nori'}).getByRole('button',{name:'Complete care record'}).click();
  await page.getByRole('dialog').getByRole('button',{name:'Complete care record'}).click();
  await page.getByLabel('Results and advice for the owner').fill('QA: verify displayed and submitted consumables after deactivation.');
  await expect(page.locator('.use-row select').first()).toHaveValue('1');
  await expect(page.locator('.use-row select').first().locator('option:checked')).toContainText('inactive');
  await expect(page.getByRole('button',{name:'Complete care and record usage'})).toBeDisabled();
  await expect(page.getByText('A default consumable is inactive or unavailable. Replace or remove it to continue.')).toBeVisible();
  await page.screenshot({path:'../test-results/fixed-disabled-consumable-warning.png',fullPage:true});
  await page.locator('.use-row select').first().selectOption('3');
  await page.getByLabel('Quantity (units)').fill('2');
  await expect(page.getByRole('button',{name:'Complete care and record usage'})).toBeEnabled();
  const displayed=await page.locator('.use-row select').evaluateAll(nodes=>nodes.map(n=>Number((n as HTMLSelectElement).value)));
  const responsePromise=page.waitForResponse(r=>r.url().endsWith('/items/10/complete')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Complete care and record usage'}).click();
  const response=await responsePromise;
  const submitted=response.request().postDataJSON().consumptions.map((c:{consumable_id:number})=>c.consumable_id);
  await page.screenshot({path:'../test-results/audit-disabled-consumable.png',fullPage:true});
  expect(submitted,`Displayed IDs ${JSON.stringify(displayed)}; submitted ${JSON.stringify(submitted)}; response ${response.status()}: ${await response.text()}`).toEqual(displayed);
  expect(response.status()).toBe(200);
  await expect(page.getByRole('dialog').getByText('Completed',{exact:true}).first()).toBeVisible();
});

test('regression: clearing a shift date shows a field error and recovers',async({page})=>{
  await login(page,'groomer');
  await page.getByRole('navigation').getByRole('button',{name:'My shifts',exact:true}).click();
  const previous=await page.getByLabel('Shift start date').inputValue();
  await page.getByLabel('Shift start date').fill('');
  await expect(page.getByRole('alert')).toHaveText('Choose both dates for the shift range.');
  await expect(page.getByText('Database unavailable',{exact:false})).toHaveCount(0);
  await page.getByLabel('Shift start date').fill(previous);
  await expect(page.getByRole('alert')).toHaveCount(0);
  await expect(page.getByRole('cell',{name:'Emma',exact:true}).first()).toBeVisible();
});

test('regression: legacy receptionist skills never become a default care assignment',async({page})=>{
  await login(page,'manager');
  await page.getByRole('navigation').getByRole('button',{name:'Employees & shifts',exact:true}).click();
  await expect(page.getByRole('row').filter({hasText:'frontdesk@pawcare.local'}).getByRole('button',{name:'Qualifications'})).toBeDisabled();
  const boot=await (await page.request.get('/api/bootstrap')).json();
  const employee=boot.employees.find((e:any)=>e.employee_id===2);
  const body=Object.fromEntries(['employee_code','display_name','staff_role','email','is_active'].map(k=>[k,employee[k]]));
  const headers={'X-PawCare-Client':'web'};
  const service=await page.request.post('/api/catalog/services',{headers,data:{service_code:'QA-LEGACY-CAT',service_name:'Cat qualification regression care',species:'cat',workstation_type:'wash',base_price:45,default_duration_minutes:30}});
  expect(service.status()).toBe(200);const sid=(await service.json()).service_id;
  expect((await page.request.put('/api/employees/2',{headers,data:{...body,staff_role:'manager'}})).status()).toBe(200);
  try{
    expect((await page.request.put('/api/employees/2/skills',{headers,data:{service_ids:[sid]}})).status()).toBe(200);
  }finally{
    expect((await page.request.put('/api/employees/2',{headers,data:body})).status()).toBe(200);
  }
  const miaSkills=boot.skills.filter((s:any)=>s.employee_id===4).map((s:any)=>s.service_id);
  expect((await page.request.put('/api/employees/4/skills',{headers,data:{service_ids:[...miaSkills,sid]}})).status()).toBe(200);
  await logout(page);await login(page,'customer');
  await page.locator('.pc-pet-row').filter({hasText:'Luna'}).getByRole('button',{name:'Book',exact:true}).click();
  await page.getByLabel('Care service').selectOption(String(sid));
  await page.getByLabel('Preferred date').fill(future());
  await page.getByLabel('Preferred time (Sydney)').fill('16:00');
  const created=page.waitForResponse(r=>r.url().endsWith('/api/appointments')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Request booking'}).click();
  const code=(await (await created).json()).booking_code;
  await expect(page.getByRole('row').filter({hasText:code})).toBeVisible();
  await logout(page);await login(page,'frontdesk');
  await page.getByRole('navigation').getByRole('button',{name:'Appointments',exact:true}).click();
  await page.getByRole('row').filter({hasText:code}).getByRole('button',{name:'Schedule',exact:true}).click();
  await page.getByRole('button',{name:'Schedule / reschedule'}).click();
  const groomer=page.getByRole('combobox',{name:'Groomer',exact:true});
  await expect(groomer).toHaveValue('4');
  await expect(groomer.locator('option[value="2"]')).toHaveCount(0);
  await page.getByRole('button',{name:'Confirm schedule'}).click();
  await expect(page.getByRole('dialog').getByText('Confirmed',{exact:true})).toBeVisible();
});
