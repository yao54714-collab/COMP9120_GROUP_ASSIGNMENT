import {test,expect,Page} from '../../frontend/node_modules/@playwright/test';

async function login(page:Page,role:string){await page.goto('/');await page.getByLabel('Email',{exact:true}).fill(role+'@pawcare.local');await page.getByLabel('Password',{exact:true}).fill('PawCare2026!');await page.getByRole('button',{name:'Sign in',exact:true}).click();await expect(page.getByRole('button',{name:'Sign out'})).toBeVisible();}
async function logout(page:Page){await page.getByRole('button',{name:'Sign out'}).click();await expect(page.getByRole('heading',{name:'Welcome back'})).toBeVisible();}
const tomorrow=()=>{const p=new Intl.DateTimeFormat('en-CA',{timeZone:'Australia/Sydney',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());const s=(k:string)=>p.find(p=>p.type===k)!.value;const d=new Date(`${s('year')}-${s('month')}-${s('day')}T12:00:00Z`);d.setUTCDate(d.getUTCDate()+1);return d.toISOString().slice(0,10)};

test('customer booking → frontdesk allocation → groomer completion → frontdesk receipt',async({page})=>{
  await login(page,'customer');
  await page.getByRole('button',{name:'My pets',exact:true}).click();
  await page.getByRole('button',{name:'Add a pet',exact:true}).click();
  await page.getByLabel('Pet name').fill('Miso browser test');
  await page.getByLabel('Breed',{exact:true}).fill('Bichon Frise');
  await page.getByLabel('Weight (kg)',{exact:true}).fill('4.5');
  await page.getByRole('button',{name:'Save',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Miso browser test'})).toBeVisible();
  await page.getByRole('button',{name:'Book a visit',exact:true}).click();
  await page.getByLabel('Pet 1').selectOption({label:'Miso browser test'});
  await page.getByLabel('Preferred date').fill(tomorrow());
  await page.getByLabel('Preferred time (Sydney)').fill('10:00');
  await page.getByLabel('Anything we should know?').fill('Please handle gently.');
  await page.getByRole('button',{name:'Request booking',exact:true}).click();
  await expect(page.getByRole('row').filter({hasText:'Miso browser test'})).toContainText('Requested');
  await logout(page);
  await login(page,'frontdesk');
  await page.getByRole('button',{name:'Appointments',exact:true}).click();
  await page.getByRole('row').filter({hasText:'Miso browser test'}).getByRole('button',{name:'Schedule',exact:true}).click();
  await page.getByRole('button',{name:'Schedule / reschedule'}).click();
  await page.getByRole('button',{name:'Find availability'}).click();
  await page.getByRole('button',{name:'Confirm schedule'}).click();
  await expect(page.getByRole('dialog').getByText('Confirmed',{exact:true})).toBeVisible();
  await page.getByRole('dialog').getByRole('button',{name:'Close',exact:true}).last().click();
  await logout(page);
  await login(page,'groomer');
  await page.getByLabel('Task date').fill(tomorrow());
  await page.locator('.pc-task').filter({hasText:'Miso browser test'}).getByRole('button',{name:'Review and start care'}).click();
  await page.getByRole('button',{name:'Start care',exact:true}).click();
  await page.getByRole('dialog').getByRole('button',{name:'Complete care record',exact:true}).click();
  await page.getByLabel('Results and advice for the owner').fill('Bathing and brushing completed. Gentle weekly brushing is recommended.');
  await page.getByLabel('Care observations',{exact:true}).fill('Skin is in good condition.');
  await page.getByRole('button',{name:'Complete care and record usage'}).click();
  await expect(page.getByRole('dialog').getByText('Completed',{exact:true}).first()).toBeVisible();
  await page.getByRole('dialog').getByRole('button',{name:'Close',exact:true}).last().click();
  await logout(page);
  await login(page,'frontdesk');
  await page.getByRole('button',{name:'Payments',exact:true}).click();
  await page.getByRole('row').filter({hasText:'Miso browser test'}).getByRole('button',{name:'View',exact:true}).click();
  await page.getByRole('button',{name:'Record payment',exact:true}).click();
  await page.getByRole('button',{name:'Confirm record',exact:true}).click();
  await expect(page.locator('.money-summary').getByText('Amount due').locator('strong')).toHaveText('A$0.00');
  await page.screenshot({path:'../test-results/completed-workflow.png',fullPage:true});
});

test('all roles and all menu pages load; desktop screenshots and mobile layout',async({page})=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  const menus:Record<string,string[]>={customer:['Home','Book a visit','My pets','My bookings','My profile'],frontdesk:['Today','Appointments','Customers & pets','Payments'],groomer:['Today tasks','Care history','My shifts'],manager:['Overview','Appointments','Customers & pets','Services','Employees & shifts','User accounts','Workstations','Inventory','Payments & refunds']};
  for(const role of Object.keys(menus)){
    await login(page,role);
    for(const label of menus[role]){await page.getByRole('navigation').getByRole('button',{name:label,exact:true}).click();await expect(page.locator('#main-content')).toBeVisible();await expect(page.locator('.form-error')).toHaveCount(0);}
    await page.getByRole('navigation').getByRole('button',{name:menus[role][0],exact:true}).click();
    if(role==='manager')await expect(page.getByText('Payments received',{exact:true})).toBeVisible();
    await page.screenshot({path:`../test-results/${role}-desktop.png`,fullPage:true});
    await page.setViewportSize({width:375,height:1600});
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth+1);
    expect(overflow).toBe(false);
    await page.screenshot({path:`../test-results/${role}-mobile.png`,fullPage:true});
    await page.setViewportSize({width:1440,height:1050});
    await logout(page);
  }
  expect(errors).toEqual([]);
});

test('manager can record a replenishment and edit a service recipe',async({page})=>{
  await login(page,'manager');
  await page.getByRole('button',{name:'Inventory',exact:true}).click();
  await page.getByRole('row').filter({hasText:'Gentle shampoo'}).getByRole('button',{name:'Record movement'}).click();
  await page.getByLabel('Quantity change (mL)',{exact:true}).fill('150');
  await page.getByLabel('Reason',{exact:true}).fill('Browser test: replenishment');
  await page.getByRole('button',{name:'Confirm record',exact:true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.getByRole('button',{name:'Stock movements',exact:true}).click();
  await expect(page.getByRole('row').filter({hasText:'Browser test: replenishment'})).toContainText('+150');
  await page.getByRole('navigation').getByRole('button',{name:'Services',exact:true}).click();
  await page.getByRole('row').filter({hasText:'Dog bath'}).getByRole('button',{name:'Default consumables'}).click();
  await page.getByLabel('Quantity (mL)',{exact:true}).first().fill('28');
  await page.getByRole('button',{name:'Save default quantities'}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
});
